"""
OpenHands Bridge (Domain 7)

OpenHands (https://github.com/All-Hands-AI/OpenHands) is an autonomous
coding agent (MIT, 54K+ stars) that can be delegated complex coding tasks.

This bridge provides a real HTTP client that talks to the OpenHands API
at ``http://localhost:3000``.  OpenHands requires Docker to run its
runtime sandbox — when Docker / OpenHands is not available the bridge
**fails loudly** with a ``ConnectionError`` containing install instructions.

NEVER mock: if the service is down, every method that needs it raises.
The bridge is gated behind ``KAIRO_OPENHANDS_ENABLED=1``.

Security:
- Task descriptions are treated as UNTRUSTED and passed through
  ``PromptShield`` before being sent to OpenHands.
- Responses from OpenHands are also treated as UNTRUSTED.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

log = logging.getLogger("kairo-sidecar.connectors.openhands")

# Default OpenHands API endpoint
DEFAULT_BASE_URL = "http://localhost:3000"

# Environment flag that must be set to "1" to enable the bridge
ENV_FLAG = "KAIRO_OPENHANDS_ENABLED"

_INSTALL_INSTRUCTIONS = (
    "OpenHands is not reachable at {url}.\n"
    "OpenHands requires Docker to run its runtime sandbox.\n"
    "Install instructions:\n"
    "  1. Install Docker: https://docs.docker.com/get-docker/\n"
    "  2. Clone OpenHands: git clone https://github.com/All-Hands-AI/OpenHands\n"
    "  3. Start OpenHands: cd OpenHands && make start\n"
    "  4. Set KAIRO_OPENHANDS_ENABLED=1\n"
    "  5. Verify: curl http://localhost:3000/api/health\n"
)


class OpenHandsBridge:
    """
    Real HTTP client for the OpenHands autonomous coding agent.

    Uses ``urllib.request`` (no external dependencies) to call the
    OpenHands REST API.  Every method makes a real network call —
    no mocking, no silent fallbacks.
    """

    def __init__(self, base_url: str = DEFAULT_BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")
        self._timeout = 30  # seconds

    # ── Internal HTTP helper ───────────────────────────────────────────

    def _request(
        self,
        endpoint: str,
        method: str = "GET",
        body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Make a real HTTP request to OpenHands.

        Raises ``ConnectionError`` if the service is unreachable.
        """
        import urllib.request
        import urllib.error

        url = f"{self.base_url}{endpoint}"
        data = None
        headers: Dict[str, str] = {"Accept": "application/json"}

        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as response:
                raw = response.read().decode("utf-8")
                if raw:
                    return json.loads(raw)
                return {}
        except urllib.error.URLError as exc:
            raise ConnectionError(_INSTALL_INSTRUCTIONS.format(url=self.base_url)) from exc
        except ConnectionError as exc:
            raise ConnectionError(_INSTALL_INSTRUCTIONS.format(url=self.base_url)) from exc

    # ── Public API ─────────────────────────────────────────────────────

    def health_check(self) -> bool:
        """
        Check if OpenHands is running and healthy.

        Makes a real GET request to ``/api/health``.
        Returns ``True`` if healthy, raises ``ConnectionError`` if down.
        """
        try:
            result = self._request("/api/health")
            # A healthy response should be a JSON dict
            if isinstance(result, dict):
                return True
            return False
        except ConnectionError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("OpenHands health check failed: %s", exc)
            raise ConnectionError(_INSTALL_INSTRUCTIONS.format(url=self.base_url)) from exc

    def is_available(self) -> bool:
        """
        Non-raising availability check.

        Returns ``True`` if OpenHands is reachable and healthy,
        ``False`` otherwise (including when disabled by env flag).
        """
        if not is_openhands_enabled():
            return False
        try:
            return self.health_check()
        except (ConnectionError, OSError, Exception):  # noqa: BLE001
            return False

    def delegate_task(self, task: str, project_dir: str) -> Dict[str, Any]:
        """
        Delegate a coding task to OpenHands.

        *task* is the natural-language description of what the agent should do.
        *project_dir* is the absolute path to the project the agent should
        work in.

        Returns the OpenHands response dict.

        Raises:
            ConnectionError — if OpenHands is unreachable.
            RuntimeError — if the env flag is not set.
        """
        if not is_openhands_enabled():
            raise RuntimeError(f"OpenHands bridge is disabled. Set {ENV_FLAG}=1 to enable.")

        # Security: scan task description for injection attempts
        try:
            from sidecar.safety.prompt_shield import PromptShield

            shield = PromptShield()
            if not shield.scan(task):
                raise ValueError(
                    "Task description blocked by PromptShield: "
                    "potential prompt injection detected."
                )
        except ImportError:
            log.warning("PromptShield not available — skipping injection scan")

        body = {
            "task": task,
            "project_dir": project_dir,
        }
        return self._request("/api/conversations", method="POST", body=body)


def is_openhands_enabled() -> bool:
    """Return ``True`` if ``KAIRO_OPENHANDS_ENABLED=1`` is set."""
    return os.environ.get(ENV_FLAG, "") == "1"


def create_bridge() -> Optional[OpenHandsBridge]:
    """
    Create an ``OpenHandsBridge`` from environment variables.

    Returns ``None`` if not enabled.
    """
    if not is_openhands_enabled():
        return None
    url = os.environ.get("KAIRO_OPENHANDS_URL", DEFAULT_BASE_URL)
    return OpenHandsBridge(url)
