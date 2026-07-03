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

__all__ = [
    "Revision",
    "extract_revisions",
    "reconstruct_original_and_final",
    "verify_docx_tracked_changes",
]
