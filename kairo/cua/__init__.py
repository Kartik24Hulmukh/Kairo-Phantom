# PROVENANCE: original | clean-room CUA world model + verifier per prompts/04 + ANCHOR_ARCHITECTURE
"""CUA world model + action verification — predict, act, verify, receipt-gate.

Implements the observe→predict→act→verify loop:
  1. World model (CUWM-style): predict structural UI state transition for a candidate action.
  2. Universal Verifier: score trajectory with rubric (process + outcome signals).
  3. Loop detection: detect stagnation/repeated states → hard-stop.
  4. Receipt gating: NO Ed25519 receipt emitted unless verifier + UI-state oracle BOTH pass.

HONEST SCOPING:
  - World-model prediction + Universal Verifier + loop-detection + receipt-gating
    on recorded fixtures = Real
  - Live observe→act on a real desktop = Experimental (fail-loud; no display in CI)

All operations are fully offline. No network calls. No LLM. No cloud.
No AGPL/GPL. Clean-room per prompts/15.
"""

from __future__ import annotations

from .engine import (
    Action,
    ActionOutcome,
    CUAExperimentalError,
    CUAUnavailableError,
    Trajectory,
    TrajectoryStep,
    UIState,
    UniversalVerifier,
    WorldModel,
    predict_transition,
    verify_trajectory,
    detect_loop,
    CUAExecutor,
)
from .oracles import (
    uistate_transition,
    verifier_agreement,
    loop_detection,
    no_receipt_without_verification,
)

__all__ = [
    "Action",
    "ActionOutcome",
    "CUAExperimentalError",
    "CUAUnavailableError",
    "Trajectory",
    "TrajectoryStep",
    "UIState",
    "UniversalVerifier",
    "WorldModel",
    "predict_transition",
    "verify_trajectory",
    "detect_loop",
    "CUAExecutor",
    "uistate_transition",
    "verifier_agreement",
    "loop_detection",
    "no_receipt_without_verification",
]
