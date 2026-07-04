# PROVENANCE: original | clean-room security package
"""kairo.security — out-of-band injection defense + PromptShield.

The reference monitor (``reference_monitor.py``) is the PRIMARY, load-bearing
security layer: a deterministic policy monitor that enforces Biba integrity
at action time, outside the model.

PromptShield (``injection_guard.py``) is the SECOND layer: a model-assisted
classifier that detects injection patterns in perceived content.

See prompts/05_security_out_of_band_injection.md.
"""

from kairo.security.injection_guard import (
    InjectionDetection,
    detect_injection,
    normalize_nfkc,
    strip_zero_width,
    calculate_entropy,
    try_base64_decode,
)
from kairo.security.reference_monitor import (
    TaintLabel,
    TaintedString,
    propagate_taint,
    Capability,
    ActionRequest,
    ReferenceMonitor,
    Decision,
    SecurityViolation,
    redline_contract_with_monitor,
    evaluate_injection_corpus,
    compute_attack_success_rate,
    InjectionTestResult,
)

__all__ = [
    # injection_guard (second layer)
    "InjectionDetection",
    "detect_injection",
    "normalize_nfkc",
    "strip_zero_width",
    "calculate_entropy",
    "try_base64_decode",
    # reference_monitor (primary layer)
    "TaintLabel",
    "TaintedString",
    "propagate_taint",
    "Capability",
    "ActionRequest",
    "ReferenceMonitor",
    "Decision",
    "SecurityViolation",
    "redline_contract_with_monitor",
    "evaluate_injection_corpus",
    "compute_attack_success_rate",
    "InjectionTestResult",
]
