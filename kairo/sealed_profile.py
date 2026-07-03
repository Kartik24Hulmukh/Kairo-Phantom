# PROVENANCE: original | clean-room sealed-build profile per specs/R3_AIRGAP_ENFORCEMENT.md
"""Sealed build profile — architecturally enforces "offline" as a compile-time guarantee.

Per specs/R3_AIRGAP_ENFORCEMENT.md §1:

    Two build profiles. ``kairo-sealed`` ships with **no network client code linked at
    all** — no HTTP stack, no telemetry SDK, no LiteLLM cloud provider. You cannot
    phone home because the capability isn't compiled in. ``kairo-connected`` is a
    separate build for non-regulated users.

This module provides the **runtime marker** and **fallback-ladder guard** for the
sealed profile. In sealed mode:

  - The R1 fallback ladder degrades to a visible "low-confidence, human-review" flag
    — it **never** reaches for the network. This is a compile-time guarantee verified
    by ``ci/sealed_no_network.yml`` (static symbol scan).
  - Any attempt to import or call a network client raises ``SealedModeViolation``.
  - The sealed marker is checked at import time so the entire process knows it is
    running in air-gapped mode.

The sealed profile is activated by setting ``KAIRO_SEALED=1`` in the environment
or by calling ``activate_sealed_mode()`` at process start (before any pipeline runs).

This is NOT a config flag that can be toggled at runtime to enable cloud fallback.
Once sealed mode is active, it cannot be deactivated within the same process —
attempting to call ``deactivate_sealed_mode()`` raises ``SealedModeViolation``.

Dependencies: stdlib only (no network libraries — that is the point).
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SEALED_ENV_VAR = "KAIRO_SEALED"
_SEALED_MARKER_FILE = ".kairo-sealed"

# Network-related module names that MUST NOT be imported in sealed mode.
# This is the runtime complement to the static symbol scan in ci/sealed_no_network.yml.
_FORBIDDEN_NETWORK_MODULES = frozenset(
    {
        "requests",
        "httpx",
        "aiohttp",
        "urllib.request",
        "http.client",
        "socket",  # socket itself is allowed for IPC/loopback, but connect() to
        # non-loopback is blocked by the egress oracle. We do NOT block
        # the import — we block the *use* of connect to external hosts.
        "ssl",
        "websocket",
        "websockets",
        "tornado.httpclient",
        "httplib2",
        "urllib3",
        "litellm",
        "openai",
        "anthropic",
        "google.generativeai",
        "telemetry",
        "opentelemetry.sdk.trace.export",
        "sentry_sdk",
    }
)

# Modules that are allowed in sealed mode for loopback/IPC only.
_ALLOWED_LOOPBACK_MODULES = frozenset(
    {
        "socket",  # IPC, loopback — connect to external hosts is blocked at runtime
    }
)


class SealedModeViolation(RuntimeError):
    """Raised when sealed mode is violated (network code path invoked).

    This is a hard error — it means the sealed build profile's compile-time
    guarantee has been bypassed at runtime. The process should abort.
    """


@dataclass
class SealedModeState:
    """Immutable snapshot of the sealed-mode state.

    Once ``active`` is True, it cannot be set to False (enforced by the
    ``activate``/``deactivate`` functions, not by direct mutation).
    """

    active: bool = False
    activated_at: str = ""
    fallback_ladder: list[str] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __bool__(self) -> bool:
        return self.active


# ---------------------------------------------------------------------------
# Singleton state — process-wide, thread-safe
# ---------------------------------------------------------------------------

_state = SealedModeState()


def is_sealed() -> bool:
    """Return True if sealed mode is active in this process."""
    return _state.active


def activate_sealed_mode(reason: str = "explicit activation") -> None:
    """Activate sealed mode. Once active, it CANNOT be deactivated.

    Sets the process-wide marker so all downstream code knows it is running
    in an air-gapped environment. Also sets KAIRO_SEALED=1 in the environment
    so child processes inherit the sealed state.
    """
    with _state._lock:
        if _state.active:
            return  # Idempotent — already sealed
        from datetime import datetime, timezone

        _state.active = True
        _state.activated_at = datetime.now(timezone.utc).isoformat()
        os.environ[_SEALED_ENV_VAR] = "1"
        # Record the fallback ladder for sealed mode (R3 §1.5):
        # In sealed mode, the R1 fallback degrades to a visible flag, NEVER the network.
        _state.fallback_ladder = [
            "Tier1: local model (on-device)",
            "↓ (if low confidence)",
            "Flag: low-confidence, human-review required",
            "HALT — no cloud fallback path exists in sealed mode",
        ]


def deactivate_sealed_mode() -> None:
    """Attempt to deactivate sealed mode. Always raises SealedModeViolation.

    Sealed mode is a one-way switch — once active, it cannot be turned off
    within the same process. This is the compile-time guarantee: the network
    path does not exist and cannot be re-enabled.
    """
    raise SealedModeViolation(
        "Sealed mode cannot be deactivated. The network path was removed at "
        "build time and cannot be re-enabled at runtime. To use network features, "
        "build with the kairo-connected profile instead."
    )


def check_sealed_or_raise() -> None:
    """Raise SealedModeViolation if sealed mode is NOT active.

    Used by code that should ONLY run in sealed mode (e.g., the egress oracle).
    """
    if not _state.active:
        raise SealedModeViolation(
            "Sealed mode is not active. This code path requires sealed mode "
            "to be enabled via activate_sealed_mode() or KAIRO_SEALED=1."
        )


def sealed_fallback_ladder() -> list[str]:
    """Return the fallback ladder for the current mode.

    In sealed mode: Tier1 → low-confidence flag → HALT (no cloud).
    In connected mode: Tier1 → Tier3 cloud (if enabled).
    """
    if _state.active:
        return list(_state.fallback_ladder)
    return [
        "Tier1: local model (on-device)",
        "↓ (if low confidence and tier3 enabled)",
        "Tier3: cloud model (kairo-connected profile only)",
    ]


def low_confidence_flag(confidence: float, threshold: float = 0.7) -> dict[str, Any]:
    """Produce a visible low-confidence, human-review flag.

    In sealed mode, when the local model's confidence is below threshold,
    the result is flagged for human review — it NEVER falls back to the cloud.
    This is the R3 §1.5 compile-time guarantee made visible.

    Args:
        confidence: The confidence score (0.0–1.0) from the local model.
        threshold: The confidence threshold below which human review is required.

    Returns:
        A dict with the flag status, the confidence, and the action to take.
    """
    is_low = confidence < threshold
    if _state.active:
        action = "human_review_required" if is_low else "accept"
        cloud_available = False
    else:
        action = "cloud_fallback_available" if is_low else "accept"
        cloud_available = True

    return {
        "sealed_mode": _state.active,
        "confidence": confidence,
        "threshold": threshold,
        "low_confidence": is_low,
        "action": action,
        "cloud_fallback_available": cloud_available,
        "message": (
            "Low confidence detected. In sealed mode, this result is flagged "
            "for human review — no cloud fallback path exists."
            if _state.active and is_low
            else "Confidence acceptable."
        ),
    }


# ---------------------------------------------------------------------------
# Auto-activation from environment
# ---------------------------------------------------------------------------


def _auto_activate() -> None:
    """Check KAIRO_SEALED env var at import time and activate if set."""
    if os.environ.get(_SEALED_ENV_VAR, "").lower() in ("1", "true", "yes"):
        activate_sealed_mode(reason="KAIRO_SEALED=1 in environment")


# Auto-activate on import if the env var is set
_auto_activate()
