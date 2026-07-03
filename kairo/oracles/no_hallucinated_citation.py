# PROVENANCE: original | clean-room oracle `no_hallucinated_citation` per prompts/domains/08a_legal_redline.md
"""Deterministic no-hallucinated-citation oracle for the Legal-redline wedge.

Implements the ``no_hallucinated_citation`` oracle required by
prompts/domains/08a_legal_redline.md.

Asserts that every citation in the redline result traces to a **real source**
in the playbook (the firm's clause library). A fabricated citation — one that
does not match any playbook entry — FAILS the oracle.

Deterministic and kill-proof (see tests): inject a fake citation → fail.
"""
from __future__ import annotations

from kairo.oracles.legal_redline_pipeline import RedlineResult


def verify_no_hallucinated_citation(
    result: RedlineResult,
    playbook_clauses: list[dict],
) -> bool:
    """Assert every citation in the redline result resolves to a playbook source.

    Args:
        result: The RedlineResult from the pipeline run.
        playbook_clauses: The list of clause dicts from the playbook.

    Returns:
        True if every citation traces to a playbook entry.

    Raises:
        AssertionError if any citation does not match a playbook source.
    """
    if not playbook_clauses:
        raise AssertionError("playbook_clauses must be a non-empty list")

    # Build the set of valid citations from the playbook
    valid_citations: set[str] = set()
    for clause in playbook_clauses:
        citation = clause.get("citation", "")
        if citation:
            valid_citations.add(citation.strip())

    # Check every applied edit's citation
    fake: list[tuple[str, str]] = []  # (clause_id, citation)
    for edit in result.applied_edits:
        citation = (edit.citation or "").strip()
        if not citation:
            # An empty citation is not a hallucination — it's a missing citation.
            # The 08a spec says "every legal reference traces to a retrieved source doc."
            # If the playbook has no citation for this clause, that's allowed (the
            # clause might be a pure text edit with no legal authority cited).
            # But if a citation IS present, it must be real.
            continue
        if citation not in valid_citations:
            fake.append((edit.clause_id, citation))

    if fake:
        raise AssertionError(
            f"no_hallucinated_citation FAILED: {len(fake)} citation(s) do not resolve "
            f"to any playbook source: {fake}"
        )

    return True
