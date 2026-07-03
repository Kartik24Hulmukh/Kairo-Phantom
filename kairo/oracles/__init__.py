# PROVENANCE: original | clean-room oracle package for specs/VERIFICATION_ORACLES.md
"""kairo.oracles — deterministic, kill-proven verification oracles.

Each oracle asserts a REAL system outcome and ships with a kill-proof (a known-bad
input it must reject). See specs/VERIFICATION_ORACLES.md and prompts/02.
"""
from kairo.oracles.docx_tracked_changes import (
    Revision,
    extract_revisions,
    reconstruct_original_and_final,
    verify_docx_tracked_changes,
)
from kairo.oracles.clause_coverage import verify_clause_coverage
from kairo.oracles.no_hallucinated_citation import verify_no_hallucinated_citation
from kairo.oracles.legal_redline_pipeline import (
    AppliedEdit,
    FlaggedClause,
    RedlineResult,
    redline_contract,
)

__all__ = [
    "Revision",
    "extract_revisions",
    "reconstruct_original_and_final",
    "verify_docx_tracked_changes",
    "verify_clause_coverage",
    "verify_no_hallucinated_citation",
    "AppliedEdit",
    "FlaggedClause",
    "RedlineResult",
    "redline_contract",
]
