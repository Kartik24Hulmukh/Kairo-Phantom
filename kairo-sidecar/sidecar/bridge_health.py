# PROVENANCE: original | Honest degradation health check for all sidecar bridges
"""Bridge health check — shared honest-degradation infrastructure.

Provides a unified health-check interface for all sidecar bridges. When an
external engine is missing/offline, bridges MUST:
  1. Report health = False via check_engine_health()
  2. Show a VISIBLE TRUTHFUL fallback message or hard-fail
  3. NEVER emit a mocked "success" or placeholder passed off as real output
  4. NEVER emit a provenance receipt for fake work

This module is imported by bridges that need shared health-check logic.
It does NOT modify the trust stack or any frozen fixtures.

All operations are fully offline. No network calls. No LLM. No cloud.
No AGPL/GPL. Clean-room per specs/CLEANROOM_IP_PROTOCOL.md.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

log = logging.getLogger("kairo-sidecar.bridge_health")


@dataclass
class EngineHealth:
    """Health status of an external engine.

    Attributes:
        engine_name:    Name of the engine (e.g. "comfyui", "synthesizer").
        available:      Whether the engine is available and healthy.
        message:        Human-readable status message.
        install_hint:   Optional install/enable instructions.
        offline_mode:   Whether the system is in offline mode (engine intentionally disabled).
    """

    engine_name: str
    available: bool
    message: str
    install_hint: str = ""
    offline_mode: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine_name": self.engine_name,
            "available": self.available,
            "message": self.message,
            "install_hint": self.install_hint,
            "offline_mode": self.offline_mode,
        }


class EngineUnavailableError(RuntimeError):
    """Raised when an external engine is unavailable and honest degradation requires a hard fail.

    This error MUST be raised (not silently swallowed) when:
      - The engine is not installed / not reachable
      - No truthful fallback exists
      - Producing fake output would violate CLAIM_DISCIPLINE

    The caller MUST handle this error — it MUST NOT be caught and replaced
    with a mock "success" response.
    """

    def __init__(self, engine_name: str, message: str, install_hint: str = ""):
        self.engine_name = engine_name
        self.install_hint = install_hint
        full_msg = f"[{engine_name}] {message}"
        if install_hint:
            full_msg += f"\nInstall/enable: {install_hint}"
        super().__init__(full_msg)


def check_binary_available(binary_name: str) -> bool:
    """Check if a binary is available on PATH."""
    return shutil.which(binary_name) is not None


def check_python_module(module_name: str) -> bool:
    """Check if a Python module is importable."""
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False


def check_subprocess_version(binary_name: str, timeout: float = 5.0) -> bool:
    """Check if a binary responds to --version (quick health check)."""
    try:
        result = subprocess.run(
            [binary_name, "--version"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0
    except Exception:
        return False


def honest_fallback(
    engine_name: str,
    capability: str,
    offline_mode: bool = False,
    install_hint: str = "",
) -> EngineHealth:
    """Return an honest EngineHealth indicating the engine is unavailable.

    This is the LOUD, TRUTHFUL fallback — it does NOT produce fake output.
    The caller should either:
      - Use this to surface a visible "capability disabled" message to the user
      - Or raise EngineUnavailableError to hard-fail

    Args:
        engine_name:  Name of the engine.
        capability:   What capability is lost (e.g. "image generation", "audio synthesis").
        offline_mode: Whether the system is intentionally offline.
        install_hint: Optional install/enable instructions.

    Returns:
        EngineHealth with available=False and a truthful message.
    """
    msg = f"{engine_name} is unavailable — {capability} disabled"
    if offline_mode:
        msg += " (offline mode)"
    log.warning(f"LOUD WARNING: {msg}")
    return EngineHealth(
        engine_name=engine_name,
        available=False,
        message=msg,
        install_hint=install_hint,
        offline_mode=offline_mode,
    )
