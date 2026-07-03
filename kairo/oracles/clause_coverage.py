# PROVENANCE: original | clean-room oracle `clause_coverage` per prompts/domains/08a_legal_redline.md
"""Deterministic clause-coverage oracle for the Legal-redline wedge.

Implements the ``clause_coverage`` oracle required by prompts/domains/08a_legal_redline.md.

Asserts that every target clause in the redline playbook is **addressed**:
  - either **edited** (appears in the applied_edits list with a real tracked change), or
  - **explicitly flagged** (appears in the flagged_clauses list with a reason).

No clause may be **silently skipped** — if the pipeline dropped a clause without
recording it in either list, the oracle FAILS.

Deterministic and kill-proof (see tests): remove a clause from the result → fail.
"""
from __future__ import annotations

from kairo.oracles.legal_redline_pipeline import RedlineResult


def verify_clause_coverage(
    result: RedlineResult,
    playbook_clauses: list[dict],
) -> bool:
    """Assert every playbook clause is addressed (edited or flagged).

    Args:
        result: The RedlineResult from the pipeline run.
        playbook_clauses: The list of clause dicts from the playbook.

    Returns:
        True if every clause is addressed.

    Raises:
        AssertionError with a specific message if any clause is silently skipped.
    """
    if not playbook_clauses:
        raise AssertionError("playbook_clauses must be a non-empty list")

    edited_ids = {e.clause_id for e in result.applied_edits}
    flagged_ids = {f.clause_id for f in result.flagged_clauses}

    missing: list[str] = []
    for clause in playbook_clauses:
        cid = clause.get("clause_id", "")
        if not cid:
            raise AssertionError(f"playbook clause missing clause_id: {clause}")
        if cid not in edited_ids and cid not in flagged_ids:
            missing.append(cid)

    if missing:
        raise AssertionError(
            f"clause_coverage FAILED: {len(missing)} playbook clause(s) silently skipped "
            f"(not in applied_edits or flagged_clauses): {missing}"
        )

    return True
