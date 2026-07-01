"""
Discord Connector (Phase 0.5)

Same security pipeline as Telegram:
inbound → PromptShield → PiiGuard → Kairo handler → PiiGuard → outbound

DISABLED by default. Enabled via: kairo connectors enable discord --token <BOT_TOKEN>
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from sidecar.connectors.telegram_connector import (
    is_airgap_mode,
)

log = logging.getLogger("kairo-sidecar.connectors.discord")


@dataclass
class DiscordInboundMessage:
    """A message received from Discord."""

    channel_id: int
    guild_id: Optional[int]
    text: str
    sender_username: str
    message_id: int
    raw: Dict[str, Any] = field(default_factory=dict)


def process_inbound(
    message: DiscordInboundMessage,
    kairo_handler: Callable[[str], str],
) -> Dict[str, Any]:
    """
    Process an inbound Discord message through the full security pipeline.

    Reuses the same security screening as Telegram (PromptShield + PiiGuard).
    """
    if is_airgap_mode():
        return {
            "ok": False,
            "response": "",
            "blocked": True,
            "reason": "Air-gap mode is ON — all connectors disabled",
        }

    # Reuse the same security screening
    from sidecar.connectors.telegram_connector import InboundMessage, process_inbound as _process

    # Adapt Discord message to the common inbound format
    adapted = InboundMessage(
        chat_id=message.channel_id,
        text=message.text,
        sender_username=message.sender_username,
        message_id=message.message_id,
        raw=message.raw,
    )
    return _process(adapted, kairo_handler)
