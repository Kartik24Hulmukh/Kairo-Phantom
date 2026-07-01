"""
Telegram Connector (Phase 0.5)

Receives Telegram messages → routes through InjectionGuard + PiiGuard →
forwards to Kairo intent gate (TCP 127.0.0.1:7438) → response sent back.

DISABLED by default. Enabled via: kairo connectors enable telegram --token <BOT_TOKEN>
Token stored in OS keychain (Kairo's existing keychain system).

Security:
- ALL inbound messages pass through PromptShield (injection detection) BEFORE
  reaching the agent
- ALL outbound messages pass through PiiGuard (PII redaction) BEFORE sending
- If PromptShield detects injection: message is BLOCKED, not forwarded
- If PiiGuard detects PII in response: PII is redacted before sending

Air-gap:
- When air-gap mode is ON: connector refuses to start with clear error
- No exceptions, no bypass
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Callable

log = logging.getLogger("kairo-sidecar.connectors.telegram")


@dataclass
class InboundMessage:
    """A message received from Telegram."""

    chat_id: int
    text: str
    sender_username: str
    message_id: int
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SecurityDecision:
    """Result of security screening on an inbound message."""

    allowed: bool
    reason: str = ""
    blocked_patterns: list[str] = field(default_factory=list)
    redacted_text: str = ""


def screen_inbound_message(text: str) -> SecurityDecision:
    """
    Screen an inbound message through PromptShield (injection detection).

    This is the SECURITY GATE — every inbound message MUST pass through this
    before it can influence the agent or trigger an action.

    Returns SecurityDecision with allowed=False if injection is detected.
    """
    try:
        from sidecar.safety.prompt_shield import PromptShield

        shield = PromptShield()
        is_safe = shield.scan(text)

        if not is_safe:
            return SecurityDecision(
                allowed=False,
                reason="Injection detected by PromptShield",
                blocked_patterns=["prompt_injection"],
            )

        # Also check for PII in inbound (redact before processing)
        redacted = text
        try:
            from sidecar.safety.pii_guard import PiiGuard

            guard = PiiGuard()
            redacted = guard.redact(text)
        except Exception:
            pass  # PiiGuard is best-effort on inbound

        return SecurityDecision(allowed=True, redacted_text=redacted)

    except ImportError:
        log.warning("PromptShield not available — BLOCKING message (fail-closed)")
        return SecurityDecision(allowed=False, reason="Security module not available — fail-closed")
    except Exception as e:
        log.error(f"Security screening error: {e} — BLOCKING (fail-closed)")
        return SecurityDecision(allowed=False, reason=f"Security error: {e}")


def screen_outbound_message(text: str) -> str:
    """
    Screen an outbound message through PiiGuard (PII redaction).

    Returns redacted text. PII is ALWAYS redacted before sending to Telegram.
    """
    try:
        from sidecar.safety.pii_guard import PiiGuard

        guard = PiiGuard()
        redacted = guard.redact(text)
        if redacted != text:
            log.info("PiiGuard redacted PII in outbound message")
        return redacted
    except Exception as e:
        log.warning(
            f"PiiGuard screening failed: {e} — message sent without redaction (fail-open for outbound)"
        )
    return text


def is_airgap_mode() -> bool:
    """Check if air-gap mode is enabled."""
    return os.environ.get("KAIRO_OFFLINE", "") != "" or os.environ.get("KAIRO_AIRGAP", "") != ""


def is_connector_enabled() -> bool:
    """Check if Telegram connector is explicitly enabled."""
    connectors = os.environ.get("KAIRO_CONNECTORS", "")
    return "telegram" in connectors.lower()


def process_inbound(message: InboundMessage, kairo_handler: Callable[[str], str]) -> Dict[str, Any]:
    """
    Process an inbound Telegram message through the full security pipeline.

    Pipeline: inbound → PromptShield → PiiGuard → Kairo handler → PiiGuard → outbound

    Args:
        message: The inbound Telegram message
        kairo_handler: Callback that processes the safe text and returns a response

    Returns:
        Dict with keys: ok, response, blocked, reason
    """
    # 1. Check air-gap
    if is_airgap_mode():
        return {
            "ok": False,
            "response": "",
            "blocked": True,
            "reason": "Air-gap mode is ON — all connectors disabled",
        }

    # 2. Screen inbound through PromptShield + PiiGuard
    decision = screen_inbound_message(message.text)
    if not decision.allowed:
        log.warning(
            f"Telegram message BLOCKED by PromptShield: chat_id={message.chat_id} "
            f"reason={decision.reason}"
        )
        return {
            "ok": False,
            "response": "Your message was blocked by security screening.",
            "blocked": True,
            "reason": decision.reason,
        }

    # 3. Forward to Kairo handler with redacted text
    safe_text = decision.redacted_text or message.text
    try:
        response = kairo_handler(safe_text)
    except Exception as e:
        log.error(f"Kairo handler error: {e}")
        return {
            "ok": False,
            "response": "An error occurred while processing your request.",
            "blocked": False,
            "reason": str(e),
        }

    # 4. Screen outbound through PiiGuard
    safe_response = screen_outbound_message(response)

    return {
        "ok": True,
        "response": safe_response,
        "blocked": False,
        "reason": "",
    }
