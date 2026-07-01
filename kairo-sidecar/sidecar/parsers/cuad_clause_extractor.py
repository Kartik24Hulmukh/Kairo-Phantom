"""
CUAD Clause Extractor — Real pattern-based extraction for 41 CUAD clause types.

The CUAD (Contract Understanding Atticus Dataset) taxonomy defines 41 clause
categories that cover the vast majority of contractual risk in commercial
agreements.  This module performs **deterministic** regex + keyword extraction
— no LLM is required for the primary path.  An optional LLM enhancement hook
is provided (traced by Opik) but the base extraction is always real.

Each extracted clause carries:
  - type:           one of the 41 CUAD labels
  - text:           the matched clause text (full paragraph)
  - paragraph_ref:  0-based index into the source paragraph list
  - confidence:     0.0–1.0 based on keyword density and regex specificity

Usage
-----
    from sidecar.parsers.cuad_clause_extractor import CUADExtractor

    extractor = CUADExtractor()
    clauses   = extractor.extract_from_text(contract_text)
    # or
    clauses   = extractor.extract_from_docx("contract.docx")
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, asdict

log = logging.getLogger("kairo-sidecar.cuad_extractor")

# ---------------------------------------------------------------------------
# Clause data model
# ---------------------------------------------------------------------------


@dataclass
class Clause:
    """A single extracted clause with provenance."""

    type: str  # CUAD label, e.g. "Limitation of Liability"
    text: str  # full paragraph text where the clause was found
    paragraph_ref: int  # 0-based index into the source paragraph list
    confidence: float  # 0.0–1.0
    matched_keywords: list[str] = field(default_factory=list)
    matched_patterns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# CUAD 41 clause taxonomy — real patterns for every category
# ---------------------------------------------------------------------------

# Each entry: (label, [keywords], [regex_patterns])
# Keywords are case-insensitive substring matches.
# Regex patterns are compiled with re.IGNORECASE | re.MULTILINE.

CUAD_CLAUSE_TAXONOMY: list[tuple[str, list[str], list[str]]] = [
    # 1
    (
        "Acceptable Use Policy",
        ["acceptable use", "acceptable usage", "permitted use policy", "usage policy"],
        [r"(?:acceptable|permitted)\s+use\s+(?:policy|guidelines?)"],
    ),
    # 2
    (
        "Acknowledgement",
        ["acknowledge", "acknowledgement", "acknowledged", "hereby acknowledges"],
        [r"\backnowledge(?:d|ment|s)?\b"],
    ),
    # 3
    (
        "Affiliated Licensee",
        ["affiliated licensee", "affiliate", "affiliates of", "subsidiary licensee"],
        [r"\baffiliat(?:e[ds]?|ion)\b.*\blicensee?\b", r"\baffiliate\b.*\b(?:grant|permit)\b"],
    ),
    # 4
    (
        "Agreement Date",
        ["agreement date", "dated as of", "entered into as of", "effective as of"],
        [r"\bagreement\s+date\b", r"\bdated\s+as\s+of\b", r"\bentered\s+into\s+as\s+of\b"],
    ),
    # 5
    (
        "Agreement Name",
        [
            "this agreement",
            "master agreement",
            "service agreement",
            "license agreement",
            "non-disclosure agreement",
            "nda",
            "employment agreement",
            "purchase agreement",
        ],
        [
            r"\b(?:this|master|service|license|non-disclosure|employment|purchase)\s+agreement\b",
            r"\bNDA\b",
        ],
    ),
    # 6
    (
        "Agreement Term",
        [
            "term of this agreement",
            "initial term",
            "term shall be",
            "duration of this agreement",
            "agreement term",
        ],
        [
            r"\b(?:initial\s+)?term\s+(?:of|shall\s+be|is)\b",
            r"\bduration\s+of\s+(?:this\s+)?agreement\b",
        ],
    ),
    # 7
    (
        "Agreement Type",
        [
            "service agreement",
            "license agreement",
            "non-disclosure agreement",
            "employment agreement",
            "purchase agreement",
            "master services agreement",
            "saas agreement",
        ],
        [
            r"\b(?:service|license|non-disclosure|employment|purchase|master\s+services?|saas)\s+agreement\b"
        ],
    ),
    # 8
    (
        "Amendments",
        [
            "amend",
            "amendment",
            "amended",
            "modify this agreement",
            "modification",
            "no amendment",
            "shall not be amended",
        ],
        [r"\bamend(?:ed|ment|s)?\b", r"\bmodif(?:y|ication|ied)\b.*\bagreement\b"],
    ),
    # 9
    (
        "Anti-Corruption Laws",
        [
            "anti-corruption",
            "anti corruption",
            "fcpa",
            "bribery",
            "corrupt practices",
            "foreign corrupt practices",
        ],
        [
            r"\banti[-\s]?corruption\b",
            r"\bFCPA\b",
            r"\b(?:foreign\s+)?corrupt\s+practices\b",
            r"\bbribery\b",
        ],
    ),
    # 10
    (
        "Audit Rights",
        ["audit", "right to audit", "inspect records", "accounting records", "audit right"],
        [r"\bright\s+to\s+audit\b", r"\baudit\s+(?:rights?|obligations?)\b"],
    ),
    # 11
    (
        "Assignment",
        [
            "assign",
            "assignment",
            "transfer this agreement",
            "successor",
            "may not assign",
            "shall not assign",
        ],
        [
            r"\bassign(?:ment|ed|s)?\b.*\bagreement\b",
            r"\b(?:may|shall)\s+not\s+assign\b",
            r"\bsuccessor\b.*\bassign\b",
        ],
    ),
    # 12
    (
        "Authority",
        ["authority", "authorized", "duly authorized", "power and authority", "legal capacity"],
        [r"\b(?:power\s+and\s+)?authority\b", r"\bduly\s+authorized\b", r"\blegal\s+capacity\b"],
    ),
    # 13
    (
        "Binding Effect",
        ["binding", "binding effect", "binding upon", "inure to the benefit"],
        [r"\bbinding\s+(?:effect|upon|on)\b", r"\binure\s+to\s+the\s+benefit\b"],
    ),
    # 14
    (
        "Capital Stock Ownership",
        ["capital stock", "shares", "ownership interest", "equity ownership", "stock ownership"],
        [r"\bcapital\s+stock\b", r"\b(?:equity\s+)?ownership\s+interest\b"],
    ),
    # 15
    (
        "Change of Control",
        [
            "change of control",
            "acquisition",
            "merger",
            "acquired by",
            "change in control",
            "control of the company",
        ],
        [r"\bchange\s+of\s+control\b", r"\bchange\s+in\s+control\b"],
    ),
    # 16
    (
        "Compliance with Laws",
        [
            "compliance with",
            "comply with all",
            "applicable laws",
            "comply with laws",
            "all applicable laws",
        ],
        [r"\bcompl(?:y|iance)\s+with\b.*\blaws?\b", r"\bapplicable\s+laws?\b"],
    ),
    # 17
    (
        "Confidentiality",
        [
            "confidential",
            "confidentiality",
            "non-disclosure",
            "proprietary information",
            "confidential information",
        ],
        [r"\bconfidential(?:ity)?\b", r"\bnon[-\s]?disclosure\b", r"\bproprietary\s+information\b"],
    ),
    # 18
    (
        "Consideration",
        [
            "consideration",
            "in consideration of",
            "good and valuable consideration",
            "mutual consideration",
        ],
        [r"\bconsideration\b", r"\bin\s+consideration\s+of\b"],
    ),
    # 19
    (
        "Counterparts",
        ["counterpart", "counterparts", "in one or more counterparts"],
        [r"\bcounterparts?\b"],
    ),
    # 20
    (
        "Cumulative Remedies",
        ["cumulative", "cumulative remedies", "additional remedies", "other remedies available"],
        [r"\bcumulative\s+remed(?:y|ies)\b", r"\bremedies\s+(?:are\s+)?cumulative\b"],
    ),
    # 21
    (
        "Data Security",
        [
            "data security",
            "security measures",
            "data protection",
            "security breach",
            "safeguard",
            "data breach",
        ],
        [
            r"\bdata\s+security\b",
            r"\bsecurity\s+(?:measures|breach|incident)\b",
            r"\bdata\s+protection\b",
        ],
    ),
    # 22
    (
        "Dispute Resolution",
        [
            "dispute resolution",
            "disputes shall be",
            "resolution of disputes",
            "mediation",
            "arbitration",
        ],
        [
            r"\bdispute\s+resolution\b",
            r"\bresolution\s+of\s+disputes\b",
            r"\bmediation\b",
            r"\barbitration\b",
        ],
    ),
    # 23
    (
        "Dispute Resolution Forum",
        [
            "venue",
            "jurisdiction",
            "courts of",
            "forum",
            "exclusive jurisdiction",
            "exclusive venue",
        ],
        [r"\b(?:exclusive\s+)?(?:jurisdiction|venue|forum)\b", r"\bcourts?\s+of\b"],
    ),
    # 24
    (
        "Effective Date",
        ["effective date", "shall become effective", "effective as of"],
        [r"\beffective\s+date\b", r"\bbecome\s+effective\b"],
    ),
    # 25
    (
        "Entire Agreement",
        [
            "entire agreement",
            "entire understanding",
            "supersedes all prior",
            "complete agreement",
            "entire and exclusive",
        ],
        [
            r"\bentire\s+agreement\b",
            r"\bentire\s+understanding\b",
            r"\bsupersedes?\s+all\s+prior\b",
        ],
    ),
    # 26
    (
        "Exclusivity",
        ["exclusive", "exclusivity", "sole and exclusive", "only provider", "exclusive basis"],
        [r"\bexclusiv(?:e|ity)\b"],
    ),
    # 27
    (
        "Expiration Date",
        ["expiration date", "expire", "expires on", "expiration of the term"],
        [r"\bexpiration\s+date\b", r"\bexpire(?:s|d)?\s+on\b"],
    ),
    # 28
    (
        "Force Majeure",
        [
            "force majeure",
            "act of god",
            "circumstances beyond",
            "unforeseeable",
            "beyond reasonable control",
        ],
        [r"\bforce\s+majeure\b", r"\bact\s+of\s+god\b", r"\bbeyond\s+(?:reasonable\s+)?control\b"],
    ),
    # 29
    (
        "Governing Law",
        [
            "governed by",
            "laws of",
            "governing law",
            "construed in accordance",
            "governed by the laws",
        ],
        [
            r"\bgovern(?:ed|ing)\s+by\b",
            r"\bgoverning\s+law\b",
            r"\bconstrued\s+in\s+accordance\b",
            r"\blaws\s+of\s+(?:the\s+)?(?:State|state)\b",
        ],
    ),
    # 30
    (
        "Guarantee",
        ["guarantee", "guaranty", "guaranteed", "guarantor"],
        [r"\bguarantee\b", r"\bguarant(?:y|or|eed)\b"],
    ),
    # 31
    (
        "Indemnification",
        [
            "indemnify",
            "indemnification",
            "hold harmless",
            "defend and indemnify",
            "shall indemnify",
        ],
        [r"\bindemnif(?:y|ication|ied)\b", r"\bhold\s+harmless\b", r"\bdefend\s+and\s+indemnify\b"],
    ),
    # 32
    (
        "Insurance",
        [
            "insurance",
            "maintain insurance",
            "certificate of insurance",
            "general liability insurance",
            "professional liability",
        ],
        [r"\binsurance\b", r"\bmaintain\s+insurance\b", r"\bcertificate\s+of\s+insurance\b"],
    ),
    # 33
    (
        "Intellectual Property Ownership",
        [
            "intellectual property",
            "work for hire",
            "assigns all",
            "solely owned",
            "all right title and interest",
            "all right, title, and interest",
            "vest exclusively",
            "owns all",
        ],
        [
            r"\bintellectual\s+property\b.*\b(?:own|assign|vest)\b",
            r"\bwork\s+for\s+hire\b",
            r"\ball\s+right[,]?\s+title[,]?\s+and\s+interest\b",
        ],
    ),
    # 34
    (
        "Joint Intellectual Property",
        ["jointly owned", "joint intellectual property", "joint ownership", "jointly developed"],
        [r"\bjoint(?:ly)?\s+(?:owned|intellectual|ownership|developed)\b"],
    ),
    # 35
    (
        "License Grant",
        [
            "license grant",
            "grants a license",
            "license to use",
            "licensed",
            "grant of license",
            "hereby grants",
        ],
        [
            r"\blicense\s+(?:grant|to\s+use)\b",
            r"\bgrant\s+of\s+license\b",
            r"\bhereby\s+grants?\b.*\blicense\b",
        ],
    ),
    # 36
    (
        "Limitation of Liability",
        [
            "liability shall not exceed",
            "cap on liability",
            "limitation of liability",
            "aggregate liability",
            "limited to fees paid",
            "maximum liability",
            "liability is limited",
            "limited to the contract value",
            "total aggregate liability",
        ],
        [
            r"\blimitation\s+of\s+liability\b",
            r"\bliability\s+(?:shall\s+)?not\s+exceed\b",
            r"\baggregate\s+liability\b",
            r"\bmaximum\s+liability\b",
            r"\bliability\s+is\s+limited\b",
        ],
    ),
    # 37
    (
        "Minimum Commitment",
        [
            "minimum purchase",
            "minimum commitment",
            "take-or-pay",
            "minimum order",
            "minimum spend",
            "minimum volume",
        ],
        [r"\bminimum\s+(?:purchase|commitment|order|spend|volume)\b", r"\btake[-\s]or[-\s]pay\b"],
    ),
    # 38
    (
        "No Waiver",
        [
            "no waiver",
            "waiver",
            "shall not constitute a waiver",
            "failure to enforce",
            "waiver of any",
        ],
        [
            r"\bno\s+waiver\b",
            r"\bwaiver\b.*\b(?:shall\s+not|not\s+constitute)\b",
            r"\bfailure\s+to\s+enforce\b",
        ],
    ),
    # 39
    (
        "Non-Compete",
        [
            "non-compete",
            "non compete",
            "non-solicitation",
            "not solicit",
            "competitive activities",
            "not to solicit",
            "solicit",
            "restraint of trade",
        ],
        [
            r"\bnon[-\s]?compete\b",
            r"\bnon[-\s]?solicitation\b",
            r"\bnot\s+(?:to\s+)?solicit\b",
            r"\bcompetitive\s+activities\b",
        ],
    ),
    # 40
    (
        "Non-Transferability",
        [
            "non-transferable",
            "nontransferable",
            "shall not transfer",
            "may not transfer",
            "not transferable",
            "non-assignable",
        ],
        [
            r"\bnon[-\s]?transfer(?:able|ability)\b",
            r"\b(?:shall|may)\s+not\s+transfer\b",
            r"\bnot\s+transferable\b",
        ],
    ),
    # 41
    (
        "Notice",
        [
            "notice",
            "written notice",
            "shall provide notice",
            "notice period",
            "days prior notice",
            "days written notice",
        ],
        [
            r"\b(?:written\s+)?notice\b",
            r"\bnotice\s+period\b",
            r"\bdays?\s+(?:prior\s+)?(?:written\s+)?notice\b",
        ],
    ),
]

# Build a quick lookup
CUAD_LABELS: list[str] = [entry[0] for entry in CUAD_CLAUSE_TAXONOMY]
assert len(CUAD_LABELS) == 41, f"Expected 41 CUAD labels, got {len(CUAD_LABELS)}"


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------


class CUADExtractor:
    """
    Real pattern-based CUAD clause extractor.

    Primary path is 100% deterministic regex + keyword matching.
    Optional LLM enhancement via LiteLLM (traced by Opik) is available
    through ``enhance_with_llm`` but is never required for base extraction.
    """

    def __init__(self) -> None:
        self._compiled: list[tuple[str, list[str], list[re.Pattern]]] = []
        for label, keywords, patterns in CUAD_CLAUSE_TAXONOMY:
            compiled_pats = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in patterns]
            self._compiled.append((label, keywords, compiled_pats))

    # -- Text-based extraction ---------------------------------------------

    def extract_from_text(self, text: str) -> list[Clause]:
        """
        Extract CUAD clauses from a raw text string.

        Paragraphs are split on double-newlines or numbered section headers.
        Returns a list of Clause objects sorted by paragraph_ref then confidence.
        """
        if not text or not text.strip():
            return []

        paragraphs = self._split_paragraphs(text)
        return self._extract_from_paragraphs(paragraphs)

    # -- DOCX-based extraction ---------------------------------------------

    def extract_from_docx(self, path: str) -> list[Clause]:
        """
        Extract CUAD clauses from a .docx file.

        Uses python-docx to read paragraphs, preserving exact paragraph indices.
        """
        from docx import Document  # lazy import — python-docx is a runtime dep

        doc = Document(path)
        paragraphs: list[str] = []
        for para in doc.paragraphs:
            paragraphs.append(para.text)

        return self._extract_from_paragraphs(paragraphs)

    # -- Core extraction engine --------------------------------------------

    def _extract_from_paragraphs(self, paragraphs: list[str]) -> list[Clause]:
        clauses: list[Clause] = []
        seen: set[tuple[str, int]] = set()  # (label, para_idx) dedup

        for idx, para_text in enumerate(paragraphs):
            if not para_text or not para_text.strip():
                continue

            for label, keywords, compiled_pats in self._compiled:
                # Check keyword matches
                para_lower = para_text.lower()
                matched_kws = [kw for kw in keywords if kw.lower() in para_lower]

                # Check regex matches
                matched_pats: list[str] = []
                for cp in compiled_pats:
                    m = cp.search(para_text)
                    if m:
                        matched_pats.append(cp.pattern)

                # Need at least one keyword OR one regex match
                if not matched_kws and not matched_pats:
                    continue

                # Deduplicate: one clause type per paragraph
                key = (label, idx)
                if key in seen:
                    continue
                seen.add(key)

                # Confidence: base 0.50 + 0.10 per keyword (max 0.30) + 0.15 per regex (max 0.30)
                kw_score = min(0.30, 0.10 * len(matched_kws))
                pat_score = min(0.30, 0.15 * len(matched_pats))
                confidence = round(min(0.99, 0.50 + kw_score + pat_score), 2)

                clauses.append(
                    Clause(
                        type=label,
                        text=para_text.strip(),
                        paragraph_ref=idx,
                        confidence=confidence,
                        matched_keywords=matched_kws,
                        matched_patterns=matched_pats,
                    )
                )

        # Sort by paragraph_ref, then confidence descending
        clauses.sort(key=lambda c: (c.paragraph_ref, -c.confidence))
        return clauses

    # -- Paragraph splitting -----------------------------------------------

    @staticmethod
    def _split_paragraphs(text: str) -> list[str]:
        """
        Split text into paragraphs.

        Strategy:
        1. Split on double newlines (blank-line separated blocks).
        2. Also split on numbered section headers (e.g. "3. ", "Section 4:").
        3. Preserve single-newline paragraphs that look like legal text.
        """
        # First split on blank lines
        blocks = re.split(r"\n\s*\n", text)

        # Further split on numbered section headers
        paragraphs: list[str] = []
        for block in blocks:
            # Check if block contains numbered section headers
            sub_blocks = re.split(
                r"(?=\n(?:\d+\.?\s|Section\s+\d+[:.]?\s|Article\s+\d+[:.]?\s))", block
            )
            for sb in sub_blocks:
                sb = sb.strip()
                if sb:
                    paragraphs.append(sb)

        return paragraphs if paragraphs else [text.strip()]

    # -- Optional LLM enhancement ------------------------------------------

    def enhance_with_llm(
        self,
        clauses: list[Clause],
        full_text: str,
        model: str = "gpt-4o-mini",
    ) -> list[Clause]:
        """
        Optionally enhance extraction with an LLM call via LiteLLM.

        This is NOT the primary path — it augments the deterministic extraction.
        If LiteLLM is unavailable or the call fails, the original clauses are
        returned unchanged (with a log warning).

        Traced by Opik via the ``track`` decorator on the caller.
        """
        try:
            import litellm  # lazy import
        except ImportError:
            log.warning("LiteLLM not available — skipping LLM enhancement")
            return clauses

        try:
            from sidecar.observability.opik_tracer import track  # noqa: F401
        except ImportError:
            pass  # no-op fallback

        existing_types = {c.type for c in clauses}
        prompt = (
            "You are a legal contract analysis assistant. "
            "Given the following contract text, identify any CUAD clause types "
            'that may have been missed. Return JSON: [{"type": "...", "text": "...", "paragraph_ref": 0}]. '
            f"Already found: {sorted(existing_types)}. "
            f"Contract text (first 4000 chars):\n{full_text[:4000]}"
        )

        try:
            response = litellm.completion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=2000,
            )
            import json

            content = response.choices[0].message.content
            extra = json.loads(content)
            for item in extra:
                label = item.get("type", "")
                if label in CUAD_LABELS and label not in existing_types:
                    clauses.append(
                        Clause(
                            type=label,
                            text=item.get("text", ""),
                            paragraph_ref=item.get("paragraph_ref", 0),
                            confidence=0.70,  # LLM-only confidence
                            matched_keywords=[],
                            matched_patterns=["llm_enhanced"],
                        )
                    )
        except Exception as e:
            log.warning("LLM enhancement failed: %s — returning base extraction", e)

        return clauses

    # -- Utility -----------------------------------------------------------

    @staticmethod
    def get_taxonomy() -> list[str]:
        """Return the 41 CUAD clause type labels."""
        return list(CUAD_LABELS)

    @staticmethod
    def clause_types_found(clauses: list[Clause]) -> list[str]:
        """Return unique clause types found, sorted."""
        return sorted({c.type for c in clauses})
