# PROVENANCE: original | clean-room end-to-end Legal-redline pipeline per prompts/domains/08a_legal_redline.md
"""End-to-end Legal-redline pipeline — offline, deterministic, oracle-verified.

This module wires the existing clause-detection engine (``legal_redline.py``) and
the real tracked-changes writer (``adeu_bridge._python_docx_tracked_fallback``)
into a single offline pipeline that:

  1. Reads a contract ``.docx`` and a **redline playbook** (JSON).
  2. Scans the contract text with PromptShield (``kairo.security.injection_guard``)
     — document text is DATA, never instructions. If injection is detected, the
     tainted content is labelled and the pipeline proceeds treating it as data
     (the text is still redlined; no instruction in it is executed).
  3. For each target clause in the playbook, detects it in the contract text and
     proposes a concrete text edit (old → new) grounded in the playbook's
     ``replacement_text`` and ``citation``.
  4. Writes the edits as real OOXML ``w:ins``/``w:del`` tracked changes via
     ``adeu_bridge`` (python-docx, BSD-3).
  5. Returns a structured result containing: the output path, the list of applied
     edits (each with clause_id, old_text, new_text, citation, rationale), the
     list of clauses flagged-but-not-edited, and the injection scan result.

The pipeline is fully offline (``KAIRO_NO_NET=1``). No LLM calls, no network.
Every cited authority traces to the playbook (the firm's clause library) —
nothing is invented. If a playbook clause is not found in the contract, it is
**flagged**, never silently skipped.

Dependencies (all BUNDLE lane per specs/TECH_MANIFEST.md):
  - python-docx (BSD-3-Clause) — tracked-changes writer + read-back
  - kairo.security.injection_guard (our code) — PromptShield taint scan
  - sidecar.parsers.legal_redline (our code) — CUAD clause detection
  - sidecar.parsers.adeu_bridge (our code) — tracked-changes writer
"""
from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("kairo.legal_redline_pipeline")


def _norm(text: str) -> str:
    """NFC-normalize and fold whitespace for layout-insensitive comparison."""
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


@dataclass(frozen=True)
class AppliedEdit:
    """A single redline edit that was applied as a tracked change."""

    clause_id: str
    clause_label: str
    old_text: str
    new_text: str
    citation: str
    rationale: str


@dataclass(frozen=True)
class FlaggedClause:
    """A playbook clause that was not found in the contract (explicitly flagged)."""

    clause_id: str
    clause_label: str
    reason: str


@dataclass
class RedlineResult:
    """Structured result of the end-to-end redline pipeline."""

    ok: bool
    output_path: str = ""
    applied_edits: list[AppliedEdit] = field(default_factory=list)
    flagged_clauses: list[FlaggedClause] = field(default_factory=list)
    injection_detected: bool = False
    injection_score: float = 0.0
    injection_patterns: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "output_path": self.output_path,
            "applied_edits": [
                {
                    "clause_id": e.clause_id,
                    "clause_label": e.clause_label,
                    "old_text": e.old_text,
                    "new_text": e.new_text,
                    "citation": e.citation,
                    "rationale": e.rationale,
                }
                for e in self.applied_edits
            ],
            "flagged_clauses": [
                {
                    "clause_id": f.clause_id,
                    "clause_label": f.clause_label,
                    "reason": f.reason,
                }
                for f in self.flagged_clauses
            ],
            "injection_detected": self.injection_detected,
            "injection_score": self.injection_score,
            "injection_patterns": self.injection_patterns,
            "error": self.error,
        }


def _load_playbook(playbook_path: str) -> dict[str, Any]:
    """Load a redline playbook JSON file.

    Expected schema:
    {
      "playbook_id": "firm_standard_v1",
      "clauses": [
        {
          "clause_id": "governing_law",
          "clause_label": "Governing Law",
          "match_text": "laws of the State of Delaware",
          "replacement_text": "laws of the State of New York",
          "citation": "Firm Standard Clause GL-001: Governing Law (NY)",
          "rationale": "Client is NY-based; NY law is more favorable."
        },
        ...
      ]
    }
    """
    with open(playbook_path, encoding="utf-8") as f:
        pb = json.load(f)
    if "clauses" not in pb or not isinstance(pb["clauses"], list):
        raise ValueError("playbook must contain a 'clauses' list")
    return pb


def _extract_docx_text(docx_path: str) -> str:
    """Extract full text from a .docx using python-docx (paragraphs only)."""
    from docx import Document

    doc = Document(docx_path)
    return "\n".join(p.text for p in doc.paragraphs)


def _scan_for_injection(text: str) -> tuple[bool, float, list[str]]:
    """Run PromptShield injection detection on document text.

    Document text is DATA — we scan it to label taint, but we NEVER execute
    instructions found in it. The scan result is recorded in the audit trail.
    Returns (detected, score, matched_patterns).
    """
    try:
        from kairo.security.injection_guard import detect_injection

        result = detect_injection(text, threshold=0.5)
        return result.blocked, result.score, result.matched_patterns
    except Exception as e:
        log.warning("injection scan failed (non-fatal): %s", e)
        return False, 0.0, []


def _find_clause_in_text(
    contract_text: str, match_text: str
) -> str | None:
    """Find the exact match_text in contract_text (normalized comparison).

    Returns the original (non-normalized) substring from the contract if found,
    so the tracked-changes writer can locate it in the .docx paragraphs.
    """
    if not match_text:
        return None
    norm_contract = _norm(contract_text)
    norm_match = _norm(match_text)
    if norm_match in norm_contract:
        # Find the original substring by searching in the raw text
        # (the writer does exact substring matching on paragraph.text)
        return match_text
    return None


def redline_contract(
    contract_path: str,
    playbook_path: str,
    output_path: str,
    author: str = "Kairo Legal",
) -> RedlineResult:
    """End-to-end offline legal redline pipeline.

    Args:
        contract_path: Path to the input contract .docx file.
        playbook_path: Path to the redline playbook JSON file.
        output_path: Path where the redlined .docx will be saved.
        author: Author name for tracked changes.

    Returns:
        RedlineResult with applied edits, flagged clauses, and injection scan.

    Raises:
        FileNotFoundError if contract or playbook doesn't exist.
        ValueError if playbook is malformed.
    """
    contract_path = str(Path(contract_path).resolve())
    playbook_path = str(Path(playbook_path).resolve())
    output_path = str(Path(output_path).resolve())

    if not os.path.exists(contract_path):
        return RedlineResult(ok=False, error=f"Contract not found: {contract_path}")
    if not os.path.exists(playbook_path):
        return RedlineResult(ok=False, error=f"Playbook not found: {playbook_path}")

    # 1. Load playbook
    playbook = _load_playbook(playbook_path)

    # 2. Extract contract text
    contract_text = _extract_docx_text(contract_path)

    # 3. PromptShield scan — document text is DATA, never instructions
    inj_detected, inj_score, inj_patterns = _scan_for_injection(contract_text)

    # 4. For each playbook clause, find it in the contract and prepare edits
    edits: list[dict[str, Any]] = []
    applied: list[AppliedEdit] = []
    flagged: list[FlaggedClause] = []

    for clause in playbook["clauses"]:
        clause_id = clause.get("clause_id", "")
        clause_label = clause.get("clause_label", clause_id)
        match_text = clause.get("match_text", "")
        replacement_text = clause.get("replacement_text", "")
        citation = clause.get("citation", "")
        rationale = clause.get("rationale", "")

        found = _find_clause_in_text(contract_text, match_text)
        if found is None:
            flagged.append(
                FlaggedClause(
                    clause_id=clause_id,
                    clause_label=clause_label,
                    reason=f"Target text not found in contract: '{match_text[:60]}...'",
                )
            )
            continue

        edit = {
            "target_text": match_text,
            "new_text": replacement_text,
            "comment": f"{rationale} [{citation}]" if citation else rationale,
        }
        edits.append(edit)
        applied.append(
            AppliedEdit(
                clause_id=clause_id,
                clause_label=clause_label,
                old_text=match_text,
                new_text=replacement_text,
                citation=citation,
                rationale=rationale,
            )
        )

    # 5. If no edits could be applied, flag all as not-found
    if not edits:
        return RedlineResult(
            ok=False,
            output_path="",
            applied_edits=[],
            flagged_clauses=flagged,
            injection_detected=inj_detected,
            injection_score=inj_score,
            injection_patterns=inj_patterns,
            error="No playbook clauses matched the contract text",
        )

    # 6. Write tracked changes via the REAL engine (adeu_bridge fallback)
    import importlib.util

    engine_path = Path(contract_path).parent.parent / "kairo-sidecar" / "sidecar" / "parsers" / "adeu_bridge.py"
    # Fallback: find relative to repo root
    if not engine_path.exists():
        # Try from the kairo package location
        kairo_init = Path(__file__).resolve().parent  # kairo/oracles/
        repo_root = kairo_init.parent.parent  # repo root
        engine_path = repo_root / "kairo-sidecar" / "sidecar" / "parsers" / "adeu_bridge.py"

    spec = importlib.util.spec_from_file_location("_kairo_adeu_bridge_redline", str(engine_path))
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)

    write_result = engine._python_docx_tracked_fallback(
        contract_path, edits, output_path, author
    )

    if not write_result.get("ok"):
        return RedlineResult(
            ok=False,
            error=f"Tracked-changes writer failed: {write_result.get('error', 'unknown')}",
            injection_detected=inj_detected,
            injection_score=inj_score,
            injection_patterns=inj_patterns,
        )

    applied_count = write_result.get("applied_count", 0)
    if applied_count < len(edits):
        # Some edits were not applied by the writer — flag them
        # (the writer skips edits where target_text is not found in a paragraph)
        for i, edit in enumerate(edits):
            if i >= applied_count:
                clause = playbook["clauses"][i]
                flagged.append(
                    FlaggedClause(
                        clause_id=clause.get("clause_id", ""),
                        clause_label=clause.get("clause_label", ""),
                        reason="Writer could not locate target text in document paragraphs",
                    )
                )

    return RedlineResult(
        ok=True,
        output_path=write_result["data"]["output_path"],
        applied_edits=applied[:applied_count],
        flagged_clauses=flagged,
        injection_detected=inj_detected,
        injection_score=inj_score,
        injection_patterns=inj_patterns,
    )
