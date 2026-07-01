"""
Email Connector (Phase 0.5)

IMAP polling → PromptShield + PiiGuard → Kairo handler → PiiGuard → SMTP response

DISABLED by default. Enabled via: kairo connectors enable email --imap <url> --smtp <url>
Credentials in OS keychain.

Security: same pipeline as Telegram/Discord — all inbound email content
passes through PromptShield before reaching the agent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Callable

from sidecar.connectors.telegram_connector import (
    is_airgap_mode,
)

log = logging.getLogger("kairo-sidecar.connectors.email")


@dataclass
class EmailInboundMessage:
    """An email message received via IMAP."""

    from_address: str
    subject: str
    body: str
    message_id: str
    has_attachment: bool = False
    attachment_path: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


def process_inbound(
    message: EmailInboundMessage,
    kairo_handler: Callable[[str], str],
) -> Dict[str, Any]:
    """
    Process an inbound email through the full security pipeline.

    The email subject + body are concatenated and screened through PromptShield.
    Attachments are NOT processed here — they go through MarkItDown (Phase 0.3)
    separately, and the extracted text also goes through PromptShield.
    """
    if is_airgap_mode():
        return {
            "ok": False,
            "response": "",
            "blocked": True,
            "reason": "Air-gap mode is ON — all connectors disabled",
        }

    # Concatenate subject + body for screening
    full_text = f"Subject: {message.subject}\n\n{message.body}"

    from sidecar.connectors.telegram_connector import InboundMessage, process_inbound as _process

    adapted = InboundMessage(
        chat_id=0,  # Email doesn't have chat_id
        text=full_text,
        sender_username=message.from_address,
        message_id=hash(message.message_id) % (2**31),
        raw=message.raw,
    )
    return _process(adapted, kairo_handler)
