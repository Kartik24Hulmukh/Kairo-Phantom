"""
Legal Redline Tools — Contract Intelligence for Kairo Phantom.
==============================================================
Provides a deterministic CUAD keyword/regex parser and redline
generation for legal documents.

Key capabilities:
  - CUAD clause detection (41 standard contract risk categories)
  - Deterministic CUAD keyword/regex parser
  - Rule-based suggested redlines
  - Risk summary generation

All functions return Kairo sidecar JSON envelopes:
    {"ok": bool, "data": {...}, "error": str | None}
"""

from __future__ import annotations

import logging
import re
import traceback

from sidecar.observability.opik_tracer import track

log = logging.getLogger("kairo-sidecar.legal_redline")

# ---------------------------------------------------------------------------
# CUAD Clause Definitions (41 categories condensed to the 20 highest-risk)
# ---------------------------------------------------------------------------

CUAD_HIGH_RISK_CLAUSES: list[dict] = [
    {
        "id": "termination_for_convenience",
        "label": "Termination for Convenience",
        "keywords": ["terminate", "termination", "convenience", "without cause", "at any time"],
        "risk_level": "HIGH",
        "description": "Party can end contract without reason",
    },
    {
        "id": "auto_renewal",
        "label": "Auto-Renewal",
        "keywords": ["automatically renew", "auto-renew", "renewed automatically", "unless notice"],
        "risk_level": "MEDIUM",
        "description": "Contract auto-renews unless notice given",
    },
    {
        "id": "non_compete",
        "label": "Non-Compete / Non-Solicitation",
        "keywords": [
            "non-compete",
            "non compete",
            "non-solicitation",
            "not solicit",
            "competitive activities",
            "not to solicit",
            "solicit",
        ],
        "risk_level": "HIGH",
        "description": "Restricts competitive activities after termination",
    },
    {
        "id": "liability_cap",
        "label": "Limitation of Liability",
        "keywords": [
            "liability shall not exceed",
            "cap on liability",
            "limitation of liability",
            "aggregate liability",
            "limited to fees paid",
            "maximum liability",
            "liability is limited",
            "limited to the contract value",
        ],
        "risk_level": "HIGH",
        "description": "Caps total liability exposure",
    },
    {
        "id": "indemnification",
        "label": "Indemnification",
        "keywords": ["indemnify", "indemnification", "hold harmless", "defend"],
        "risk_level": "HIGH",
        "description": "One party must compensate other for losses",
    },
    {
        "id": "ip_ownership",
        "label": "Intellectual Property Ownership",
        "keywords": [
            "intellectual property",
            "work for hire",
            "assigns all",
            "solely owned",
            "all right title and interest",
            "all right, title, and interest",
            "vest exclusively",
        ],
        "risk_level": "HIGH",
        "description": "Who owns IP created under the contract",
    },
    {
        "id": "liquidated_damages",
        "label": "Liquidated Damages",
        "keywords": ["liquidated damages", "penalty", "agreed damages"],
        "risk_level": "HIGH",
        "description": "Pre-agreed penalty amounts for breach",
    },
    {
        "id": "governing_law",
        "label": "Governing Law & Jurisdiction",
        "keywords": ["governed by", "laws of", "jurisdiction", "venue", "courts of"],
        "risk_level": "MEDIUM",
        "description": "Which state/country law applies",
    },
    {
        "id": "force_majeure",
        "label": "Force Majeure",
        "keywords": ["force majeure", "act of god", "circumstances beyond", "unforeseeable"],
        "risk_level": "MEDIUM",
        "description": "Excuses non-performance for extraordinary events",
    },
    {
        "id": "audit_rights",
        "label": "Audit Rights",
        "keywords": ["audit", "right to audit", "inspect records", "accounting records"],
        "risk_level": "MEDIUM",
        "description": "Party's right to audit books/records",
    },
    {
        "id": "exclusivity",
        "label": "Exclusivity",
        "keywords": ["exclusive", "exclusivity", "sole and exclusive", "only provider"],
        "risk_level": "HIGH",
        "description": "Contract grants exclusive rights",
    },
    {
        "id": "assignment",
        "label": "Assignment",
        "keywords": ["assign", "assignment", "transfer this agreement", "successor"],
        "risk_level": "MEDIUM",
        "description": "Can either party assign contract rights",
    },
    {
        "id": "warranty",
        "label": "Warranty / Representations",
        "keywords": ["warrant", "warranty", "represent", "representations", "as-is"],
        "risk_level": "HIGH",
        "description": "Contractual guarantees made by parties",
    },
    {
        "id": "confidentiality",
        "label": "Confidentiality / NDA",
        "keywords": [
            "confidential",
            "confidentiality",
            "non-disclosure",
            "proprietary information",
        ],
        "risk_level": "MEDIUM",
        "description": "Restrictions on sharing information",
    },
    {
        "id": "change_of_control",
        "label": "Change of Control",
        "keywords": ["change of control", "acquisition", "merger", "acquired by"],
        "risk_level": "HIGH",
        "description": "What happens if ownership changes",
    },
    {
        "id": "minimum_commitment",
        "label": "Minimum Commitment / Purchase",
        "keywords": ["minimum purchase", "minimum commitment", "take-or-pay", "minimum order"],
        "risk_level": "HIGH",
        "description": "Required minimum volume/spend",
    },
    {
        "id": "arbitration",
        "label": "Arbitration",
        "keywords": ["arbitration", "arbitrate", "binding arbitration", "american arbitration"],
        "risk_level": "MEDIUM",
        "description": "Disputes resolved by arbitrator, not courts",
    },
    {
        "id": "insurance",
        "label": "Insurance Requirements",
        "keywords": [
            "insurance",
            "maintain insurance",
            "certificate of insurance",
            "general liability insurance",
        ],
        "risk_level": "MEDIUM",
        "description": "Required insurance coverage types",
    },
    {
        "id": "payment_terms",
        "label": "Payment Terms",
        "keywords": [
            "net 30",
            "net 60",
            "payment due",
            "invoice",
            "late payment",
            "interest on late",
        ],
        "risk_level": "MEDIUM",
        "description": "When and how payment is made",
    },
    {
        "id": "renewal_notice",
        "label": "Renewal Notice Period",
        "keywords": ["days prior", "written notice", "notice period", "days before expiration"],
        "risk_level": "MEDIUM",
        "description": "Required advance notice to prevent auto-renewal",
    },
]


# ---------------------------------------------------------------------------
# Core: CUAD Clause Detection
# ---------------------------------------------------------------------------


def detect_cuad_clauses(
    document_text: str,
    paragraphs: list[dict] | None = None,
) -> dict:
    """
    Identify CUAD clause categories present in document text.

    Returns:
        {
            "ok": True,
            "data": {
                "detected_clauses": [
                    {
                        "id": "termination_for_convenience",
                        "label": "Termination for Convenience",
                        "risk_level": "HIGH",
                        "description": "...",
                        "matched_text": "...",         # excerpt from doc
                        "paragraph_index": 42,         # if paragraphs provided
                        "confidence": 0.92,
                    }, ...
                ],
                "risk_summary": {
                    "HIGH": 5,
                    "MEDIUM": 3,
                    "LOW": 0,
                    "total_flagged": 8,
                },
                "missing_standard_clauses": ["force_majeure", ...]
            }
        }
    """
    if not document_text.strip():
        return _error("document_text is empty")

    text_lower = document_text.lower()
    detected: list[dict] = []
    detected_ids: set[str] = set()

    # --- Keyword scan
    for clause in CUAD_HIGH_RISK_CLAUSES:
        matched_keywords = [kw for kw in clause["keywords"] if kw.lower() in text_lower]
        if matched_keywords:
            # Find excerpt around first match
            first_kw = matched_keywords[0]
            idx = text_lower.find(first_kw.lower())
            excerpt = document_text[max(0, idx - 80) : idx + 120].strip()

            # Find paragraph index if paragraphs provided
            para_idx = None
            if paragraphs:
                for p in paragraphs:
                    if any(kw.lower() in p.get("text", "").lower() for kw in matched_keywords):
                        para_idx = p.get("index")
                        break

            # Confidence based on number of matching keywords
            confidence = min(0.99, 0.60 + 0.08 * len(matched_keywords))

            detected.append(
                {
                    "id": clause["id"],
                    "label": clause["label"],
                    "risk_level": clause["risk_level"],
                    "description": clause["description"],
                    "matched_text": excerpt,
                    "paragraph_index": para_idx,
                    "matched_keywords": matched_keywords,
                    "confidence": round(confidence, 2),
                }
            )
            detected_ids.add(clause["id"])

    # --- Risk summary
    risk_counts: dict[str, int] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for d in detected:
        lvl = d["risk_level"]
        risk_counts[lvl] = risk_counts.get(lvl, 0) + 1

    # --- Missing standard clauses (should be present in most contracts)
    standard_required = {
        "governing_law",
        "confidentiality",
        "termination_for_convenience",
        "liability_cap",
        "indemnification",
    }
    missing = list(standard_required - detected_ids)

    log.info(
        "detect_cuad_clauses: %d clauses detected (HIGH=%d, MEDIUM=%d)",
        len(detected),
        risk_counts["HIGH"],
        risk_counts["MEDIUM"],
    )

    return {
        "ok": True,
        "data": {
            "detected_clauses": sorted(
                detected,
                key=lambda x: ("HIGH", "MEDIUM", "LOW").index(x["risk_level"]),
            ),
            "risk_summary": {
                **risk_counts,
                "total_flagged": len(detected),
            },
            "missing_standard_clauses": missing,
        },
    }


# ---------------------------------------------------------------------------
# Core: Generate AI Redlines
# ---------------------------------------------------------------------------


def generate_redlines_for_clause(
    clause_text: str,
    clause_id: str,
    negotiation_stance: str = "balanced",
    party: str = "client",
) -> dict:
    """
    Generate a suggested redline (revision) for a detected risky clause.

    negotiation_stance: "aggressive" | "balanced" | "conservative"
    party: "client" | "vendor" | "employer" | "employee"

    Returns:
        {
            "ok": True,
            "data": {
                "original_text": str,
                "suggested_text": str,
                "rationale": str,
                "risk_reduction": str,  # "High → Low" etc.
            }
        }
    """
    if not clause_text.strip():
        return _error("clause_text is empty")

    # Build instruction based on stance
    stance_instructions = {
        "aggressive": (
            f"You are a {party}-side contract lawyer. AGGRESSIVELY protect the {party}'s "
            f"interests. Minimize {party}'s obligations, maximize protections."
        ),
        "balanced": (
            "You are a neutral contract lawyer. Propose a BALANCED revision that protects "
            "both parties fairly and is commercially reasonable."
        ),
        "conservative": (
            f"You are a {party}-side contract lawyer. Propose a CONSERVATIVE, market-standard "
            f"revision that makes minor improvements without renegotiating fundamental terms."
        ),
    }

    stance_instructions.get(negotiation_stance, stance_instructions["balanced"])

    # Redline instruction templates per clause type
    clause_instructions: dict[str, str] = {
        "termination_for_convenience": (
            "Add a minimum notice period (30 days) and require payment for work in progress. "
            "Add: 'with at least 30 days written notice, and upon termination Company shall "
            "pay for all work performed through the termination date.'"
        ),
        "liability_cap": (
            "Carve out gross negligence, willful misconduct, and IP infringement from the cap. "
            "Add standard exceptions: 'excluding (a) gross negligence or willful misconduct, "
            "(b) fraud, (c) indemnification obligations, (d) IP infringement.'"
        ),
        "auto_renewal": (
            "Extend the notice period to at least 60 days and require written notice. "
            "Change 'days prior notice' to 'sixty (60) days prior written notice.'"
        ),
        "non_compete": (
            "Narrow scope by limiting geography, duration (max 12 months), and activities. "
            "Replace 'any competitive activities' with 'directly competitive products or services "
            "in the specific field of [PRODUCT_FIELD].'"
        ),
        "indemnification": (
            "Make indemnification mutual. Add: 'Each party shall indemnify the other party from "
            "claims arising from that party's own breach, negligence, or willful misconduct.'"
        ),
        "ip_ownership": (
            "Retain pre-existing IP and tools. Add: 'Provider retains all rights in pre-existing "
            "IP and general tools and methodologies. Client owns deliverables specifically created "
            "under this Agreement.'"
        ),
    }

    clause_specific = clause_instructions.get(clause_id, "")

    # Return structured response without calling LLM (LLM integration via llm_caller is separate)
    # We provide a rule-based redline that the caller can optionally enhance via LLM
    suggested_text = _apply_rule_based_redline(clause_text, clause_id)

    return {
        "ok": True,
        "data": {
            "original_text": clause_text,
            "suggested_text": suggested_text,
            "rationale": clause_specific
            or f"Standard {negotiation_stance} revision for {clause_id}",
            "stance": negotiation_stance,
            "party": party,
            "clause_id": clause_id,
            "risk_reduction": _estimate_risk_reduction(clause_id, negotiation_stance),
        },
    }


def generate_contract_summary(
    document_text: str,
    detected_clauses: list[dict] | None = None,
) -> dict:
    """
    Generate a plain-English executive summary of contract risks.

    Returns a structured risk report suitable for display in Kairo's overlay.
    """
    if not document_text.strip():
        return _error("document_text is empty")

    # Run clause detection if not provided
    if detected_clauses is None:
        detection = detect_cuad_clauses(document_text)
        if not detection["ok"]:
            return detection
        detected_clauses = detection["data"]["detected_clauses"]
        risk_summary = detection["data"]["risk_summary"]
        missing = detection["data"]["missing_standard_clauses"]
    else:
        risk_counts: dict[str, int] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for d in detected_clauses:
            lvl = d.get("risk_level", "LOW")
            risk_counts[lvl] = risk_counts.get(lvl, 0) + 1
        risk_summary = {**risk_counts, "total_flagged": len(detected_clauses)}
        missing = []

    # Build executive summary text
    high_risk = [c for c in detected_clauses if c["risk_level"] == "HIGH"]
    medium_risk = [c for c in detected_clauses if c["risk_level"] == "MEDIUM"]

    summary_lines = [
        f"KAIRO CONTRACT REVIEW — {risk_summary['total_flagged']} clause(s) flagged",
        "",
        f"⚠️  HIGH RISK ({len(high_risk)} clauses):",
    ]
    for c in high_risk:
        summary_lines.append(f"  • {c['label']}: {c['description']}")

    if medium_risk:
        summary_lines.append(f"\n⚡ MEDIUM RISK ({len(medium_risk)} clauses):")
        for c in medium_risk:
            summary_lines.append(f"  • {c['label']}: {c['description']}")

    if missing:
        summary_lines.append("\n❌ MISSING STANDARD CLAUSES:")
        for clause_id in missing:
            # Find label
            label = next(
                (c["label"] for c in CUAD_HIGH_RISK_CLAUSES if c["id"] == clause_id),
                clause_id,
            )
            summary_lines.append(f"  • {label}")

    summary_text = "\n".join(summary_lines)

    # Build per-clause action items
    action_items: list[dict] = []
    for clause in high_risk:
        action_items.append(
            {
                "priority": "URGENT",
                "clause": clause["label"],
                "action": f"Negotiate or remove {clause['label']} — {clause['description']}",
                "paragraph_index": clause.get("paragraph_index"),
            }
        )

    return {
        "ok": True,
        "data": {
            "summary_text": summary_text,
            "risk_summary": risk_summary,
            "high_risk_clauses": high_risk,
            "medium_risk_clauses": medium_risk,
            "missing_standard_clauses": missing,
            "action_items": action_items,
            "total_clauses_detected": len(detected_clauses),
        },
    }


@track("legal", "analyze_contract")
def analyze_contract(file_text: str, paragraphs: list[dict] | None = None) -> dict:
    """
    Full contract analysis pipeline:
    1. Detect CUAD clauses
    2. Generate executive summary
    3. Return redline suggestions for HIGH-risk clauses

    This is the primary entry point for the `analyze_contract` sidecar action.
    """
    if not file_text.strip():
        return _error("file_text is empty")

    try:
        # Step 1: Detect
        detection = detect_cuad_clauses(file_text, paragraphs)
        if not detection["ok"]:
            return detection

        detected = detection["data"]["detected_clauses"]
        risk_summary = detection["data"]["risk_summary"]
        missing = detection["data"]["missing_standard_clauses"]

        # Step 2: Summary
        summary_data = generate_contract_summary(file_text, detected)
        if not summary_data["ok"]:
            return summary_data

        # Step 3: Redlines for HIGH-risk clauses (max 5 to avoid overload)
        redlines: list[dict] = []
        for clause in [c for c in detected if c["risk_level"] == "HIGH"][:5]:
            matched_text = clause.get("matched_text", "")
            if matched_text:
                redline_result = generate_redlines_for_clause(
                    matched_text,
                    clause["id"],
                    negotiation_stance="balanced",
                )
                if redline_result["ok"]:
                    redlines.append(
                        {
                            "clause_id": clause["id"],
                            "clause_label": clause["label"],
                            **redline_result["data"],
                        }
                    )

        log.info(
            "analyze_contract: %d clauses, %d redlines generated",
            len(detected),
            len(redlines),
        )

        return {
            "ok": True,
            "data": {
                "detected_clauses": detected,
                "risk_summary": risk_summary,
                "missing_standard_clauses": missing,
                "summary_text": summary_data["data"]["summary_text"],
                "action_items": summary_data["data"]["action_items"],
                "suggested_redlines": redlines,
                "total_clauses_detected": len(detected),
            },
        }

    except Exception:
        return _error(traceback.format_exc())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _apply_rule_based_redline(clause_text: str, clause_id: str) -> str:
    """
    Apply deterministic rule-based text transformations as a baseline redline.
    These are additive suggestions, not destructive replacements.
    """
    text = clause_text

    rules: dict[str, list[tuple[str, str]]] = {
        "auto_renewal": [
            (
                r"\b(\d+)\s*days?\s*(?:prior|advance|written)?\s*notice",
                "60 days prior written notice",
            ),
            (r"\bnotice\b", "written notice"),
        ],
        "termination_for_convenience": [
            (r"\bat any time\b", "upon thirty (30) days prior written notice"),
            (r"\bimmediate(?:ly)?\b", "after thirty (30) days"),
        ],
        "liability_cap": [
            (
                r"\bshall not exceed\b",
                "shall not exceed (excluding gross negligence, willful misconduct, and IP infringement)",
            ),
        ],
        "non_compete": [
            (r"\bany\s+(?:competitive|business)\b", "directly competitive"),
            (r"\b(one|two|three|1|2|3)\s+year", "twelve (12) month"),
        ],
    }

    patterns = rules.get(clause_id, [])
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE, count=1)

    return text


def _estimate_risk_reduction(clause_id: str, stance: str) -> str:
    """Return a risk reduction label for the given clause + stance."""
    reductions: dict[str, dict[str, str]] = {
        "aggressive": {
            "liability_cap": "HIGH → LOW",
            "non_compete": "HIGH → LOW",
            "termination_for_convenience": "HIGH → LOW",
            "default": "MEDIUM → LOW",
        },
        "balanced": {
            "liability_cap": "HIGH → MEDIUM",
            "non_compete": "HIGH → MEDIUM",
            "termination_for_convenience": "HIGH → MEDIUM",
            "default": "MEDIUM → LOW",
        },
        "conservative": {
            "default": "HIGH → MEDIUM",
        },
    }
    stance_map = reductions.get(stance, reductions["balanced"])
    return stance_map.get(clause_id, stance_map.get("default", "REDUCED"))


# ---------------------------------------------------------------------------
# Clause-by-Clause Redline Comparison (Domain 5 enhancement)
# ---------------------------------------------------------------------------


def compare_contracts(
    original_text: str,
    revised_text: str,
) -> dict:
    """
    Compare two contract versions clause-by-clause using the CUAD extractor.

    Instead of character-by-character diffing, this:
    1. Extracts all CUAD clauses from both versions (real pattern matching).
    2. Matches clauses by type across versions.
    3. Categorizes each as: added, removed, or modified.
    4. Every redline entry has: source paragraph ref, clause type, confidence.

    Returns:
        {
            "ok": True,
            "data": {
                "added_clauses": [...],
                "removed_clauses": [...],
                "modified_clauses": [...],
                "unchanged_clauses": [...],
                "summary": {"added": N, "removed": N, "modified": N, "unchanged": N},
            }
        }
    """
    from sidecar.parsers.cuad_clause_extractor import CUADExtractor

    extractor = CUADExtractor()
    orig_clauses = extractor.extract_from_text(original_text)
    rev_clauses = extractor.extract_from_text(revised_text)

    # Index by clause type — there may be multiple clauses of the same type
    orig_by_type: dict[str, list] = {}
    for c in orig_clauses:
        orig_by_type.setdefault(c.type, []).append(c)

    rev_by_type: dict[str, list] = {}
    for c in rev_clauses:
        rev_by_type.setdefault(c.type, []).append(c)

    all_types = set(orig_by_type.keys()) | set(rev_by_type.keys())

    added: list[dict] = []
    removed: list[dict] = []
    modified: list[dict] = []
    unchanged: list[dict] = []

    for clause_type in sorted(all_types):
        orig_list = orig_by_type.get(clause_type, [])
        rev_list = rev_by_type.get(clause_type, [])

        if not orig_list and rev_list:
            # Clauses added in revised version
            for c in rev_list:
                added.append(
                    {
                        "clause_type": c.type,
                        "text": c.text,
                        "paragraph_ref": c.paragraph_ref,
                        "confidence": c.confidence,
                        "version": "revised",
                    }
                )

        elif orig_list and not rev_list:
            # Clauses removed in revised version
            for c in orig_list:
                removed.append(
                    {
                        "clause_type": c.type,
                        "text": c.text,
                        "paragraph_ref": c.paragraph_ref,
                        "confidence": c.confidence,
                        "version": "original",
                    }
                )

        else:
            # Both have clauses of this type — compare text
            # Match by best text similarity
            import difflib

            used_rev: set[int] = set()
            for oc in orig_list:
                best_ratio = 0.0
                best_idx = -1
                for i, rc in enumerate(rev_list):
                    if i in used_rev:
                        continue
                    ratio = difflib.SequenceMatcher(None, oc.text, rc.text).ratio()
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_idx = i

                if best_idx >= 0:
                    used_rev.add(best_idx)
                    rc = rev_list[best_idx]
                    if best_ratio < 0.95:
                        modified.append(
                            {
                                "clause_type": clause_type,
                                "original_text": oc.text,
                                "original_paragraph_ref": oc.paragraph_ref,
                                "revised_text": rc.text,
                                "revised_paragraph_ref": rc.paragraph_ref,
                                "confidence": min(oc.confidence, rc.confidence),
                                "similarity": round(best_ratio, 3),
                            }
                        )
                    else:
                        unchanged.append(
                            {
                                "clause_type": clause_type,
                                "text": oc.text,
                                "paragraph_ref": oc.paragraph_ref,
                                "confidence": oc.confidence,
                                "similarity": round(best_ratio, 3),
                            }
                        )

            # Any unmatched revised clauses are additions
            for i, rc in enumerate(rev_list):
                if i not in used_rev:
                    added.append(
                        {
                            "clause_type": rc.type,
                            "text": rc.text,
                            "paragraph_ref": rc.paragraph_ref,
                            "confidence": rc.confidence,
                            "version": "revised",
                        }
                    )

    summary = {
        "added": len(added),
        "removed": len(removed),
        "modified": len(modified),
        "unchanged": len(unchanged),
    }

    log.info(
        "compare_contracts: added=%d, removed=%d, modified=%d, unchanged=%d",
        summary["added"],
        summary["removed"],
        summary["modified"],
        summary["unchanged"],
    )

    return {
        "ok": True,
        "data": {
            "added_clauses": added,
            "removed_clauses": removed,
            "modified_clauses": modified,
            "unchanged_clauses": unchanged,
            "summary": summary,
        },
    }


def _error(msg: str) -> dict:
    log.error("LegalRedline error: %s", msg)
    return {"ok": False, "data": None, "error": msg}
