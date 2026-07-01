"""
PromptShield — Injection Detection for Inbound Messages (Phase 0.5)

This is the REAL injection detection module used by all connectors.
Every inbound message from Telegram/Discord/Email passes through scan()
before it can influence the agent or trigger an action.

PATTERN PARITY: This module maintains parity with the Rust-side
phantom-core/src/guardrails.rs PromptGuard (29 hard + 27 soft = 56 patterns).
The Rust patterns are reproduced here as Python regex equivalents plus
additional regex patterns for broader coverage. A parity test
(test_prompt_shield_rust_parity) verifies that every Rust pattern is
covered by a Python pattern.

Sync strategy: When guardrails.rs is updated, update INJECTION_PATTERNS
here and run test_prompt_shield_rust_parity to verify coverage.
"""

from __future__ import annotations

import re
import logging
from typing import List

log = logging.getLogger("kairo-sidecar.prompt_shield")


# ── Injection Detection Patterns ──────────────────────────────────────────────
# Each pattern is a regex that matches known prompt injection techniques.
# These are based on OWASP LLM Top 10 and real-world attack vectors.
#
# PATTERN PARITY with Rust guardrails.rs:
# - Rust hard_patterns (29): all reproduced below as HARD_PATTERNS
# - Rust soft_patterns (27): all reproduced below as SOFT_PATTERNS
# - Additional regex patterns (28): broader regex coverage for connector inputs
# Total: 84 patterns (56 from Rust + 28 additional)

# ── Rust hard_patterns (29) — exact substring matches, case-insensitive ───────
HARD_PATTERNS: List[str] = [
    # System prompt revelation
    r"reveal\s+your\s+system\s+prompt",
    r"print\s+your\s+instructions",
    r"output\s+your\s+prompt",
    r"show\s+me\s+your\s+rules",
    r"repeat\s+your\s+system",
    r"what\s+are\s+your\s+instructions",
    # Absolute override commands
    r"ignore\s+all\s+previous\s+instructions",
    r"ignore\s+all\s+prior\s+instructions",
    r"ignore\s+previous\s+instructions",
    r"disregard\s+all\s+previous",
    r"forget\s+all\s+previous\s+instructions",
    r"override\s+your\s+training",
    r"bypass\s+your\s+guidelines",
    # Role jailbreaks
    r"you\s+are\s+now\s+dan",
    r"enter\s+developer\s+mode",
    r"jailbreak\s+mode",
    r"enable\s+unrestricted\s+mode",
    r"pretend\s+you\s+have\s+no\s+restrictions",
    r"dan\s+mode",
    r"developer\s+mode\s+enabled",
    r"bypass\s+all\s+your\s+guidelines",
    r"bypass\s+your\s+guidelines",
    r"bypass\s+all\s+your\s+rules",
    r"role\s+play\s+as\s+a",
    r"pretend\s+you\s+are\s+a",
    r"pretend\s+you\s+are\s+gpt",
    # Sentinel/security probes
    r"what\s+is\s+your\s+sentinel",
    r"print\s+the\s+sentinel",
    r"output\s+the\s+sentinel\s+hash",
]

# ── Rust soft_patterns (27) — scored cumulatively in Rust, all blocked here ───
SOFT_PATTERNS: List[str] = [
    r"ignore\s+previous",
    r"ignore\s+above",
    r"new\s+instructions",
    r"new\s+rules",
    r"system\s+prompt",
    r"you\s+are\s+now",
    r"pretend\s+you\s+are",
    r"act\s+as\s+if",
    r"for\s+educational\s+purposes",
    r"hypothetically\s+speaking",
    r"in\s+a\s+fictional\s+scenario",
    r"as\s+an\s+ai\s+with\s+no",
    r"without\s+restrictions",
    r"stop\s+following",
    r"disregard\s+your",
    r"output\s+the\s+above",
    r"repeat\s+after\s+me",
    r"translate\s+the\s+following",
    r"do\s+anything\s+now",
    r"dan\s+mode",
    r"developer\s+mode",
    r"god\s+mode",
    r"unlock\s+mode",
    r"simulate\s+being",
    r"role\s+play\s+as",
    r"your\s+real\s+self",
    r"your\s+true\s+self",
]

# ── Additional regex patterns (28) — broader coverage for connector inputs ───
ADDITIONAL_PATTERNS: List[str] = [
    # Direct instruction overrides (broader regex)
    r"forget\s+(?:all\s+|your\s+)?(?:previous\s+|prior\s+)?(?:instructions?|rules|guidelines)",
    r"override\s+(?:all\s+|your\s+)?(?:system\s+|safety\s+)?(?:rules|guidelines|instructions)",
    # Role hijacking (broader regex)
    r"you\s+are\s+now\s+(?:DAN|an?\s+unrestricted|an?\s+unfiltered|an?\s+unlimited)",
    r"act\s+as\s+(?:an?\s+unrestricted|DAN|jailbreak|unfiltered)",
    r"enter\s+(?:developer\s+mode|admin\s+mode|jailbreak\s+mode|unrestricted\s+mode)",
    r"you\s+are\s+(?:no\s+longer|not\s+)\s*(?:bound\s+by|limited\s+by|restricted\s+by)",
    # Tool/command injection
    r"execute\s+(?:the\s+following\s+)?(?:command|script|code):\s*",
    r"run\s+(?:system\s+)?(?:command|shell|bash|cmd)\s*",
    r"(?:rm\s+-rf|del\s+/[fqs]|format\s+[a-z]:)",
    r"(?:import\s+os|subprocess|eval\s*\(|exec\s*\()",
    # Data exfiltration (broader regex)
    r"(?:reveal|show|print|display|output)\s+(?:the\s+)?(?:system\s+)?(?:prompt|instructions?|rules|guidelines)",
    r"(?:print|show|reveal|exfiltrate)\s+(?:all\s+)?(?:secrets?|api\s+keys?|tokens?|passwords?|credentials?)",
    r"(?:send|transmit|exfiltrate)\s+(?:data|secrets?|info)\s+to\s+",
    # Hidden instructions in formatting
    r"\[SYSTEM(?:\s+OVERRIDE)?\]",
    r"<\|system\|>",
    r"\[ADMIN\]",
    r"\[INST\]",
    r"###\s*SYSTEM:",
    r"---\s*SYSTEM\s*---",
    # Encoding tricks
    r"(?:base64|btoa|atob)\s*\(",
    r"\\x[0-9a-f]{2}\\x[0-9a-f]{2}",
    r"\\u[0-9a-f]{4}\\u[0-9a-f]{4}",
    # Prompt leaking
    r"(?:what\s+are\s+your|tell\s+me\s+your)\s+(?:system\s+)?(?:prompt|instructions?|rules)",
    r"repeat\s+(?:everything|all\s+instructions)\s+(?:above|before)",
    # Privilege escalation
    r"(?:grant|give)\s+me\s+(?:admin|root|sudo|elevated)\s+(?:access|privileges)",
    r"(?:escalate|bypass)\s+(?:security|safety|restrictions?|guardrails?)",
]

# All patterns combined
INJECTION_PATTERNS: List[str] = HARD_PATTERNS + SOFT_PATTERNS + ADDITIONAL_PATTERNS

# Compile patterns for performance
_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in INJECTION_PATTERNS]


class PromptShield:
    """
    Real injection detection for inbound messages.

    scan(text) returns True if the text is SAFE (no injection detected).
    scan(text) returns False if injection patterns are detected.

    This is a FAIL-CLOSED design: if anything goes wrong, the message is blocked.

    PATTERN PARITY: Maintains parity with Rust guardrails.rs PromptGuard.
    See test_prompt_shield_rust_parity for the parity verification test.
    """

    def __init__(self):
        self.patterns = _COMPILED_PATTERNS

    def scan(self, text: str) -> bool:
        """
        Scan text for prompt injection patterns.

        Returns True if SAFE (no injection detected).
        Returns False if injection is detected (message should be BLOCKED).
        """
        if not text or not text.strip():
            return True  # Empty messages are safe

        for pattern in self.patterns:
            if pattern.search(text):
                log.warning(
                    f"PromptShield: Injection detected — pattern '{pattern.pattern}' matched"
                )
                return False

        return True

    def scan_detailed(self, text: str) -> dict:
        """
        Detailed scan returning matched patterns.

        Returns dict with:
        - safe: bool (True if no injection)
        - matched_patterns: list of matched pattern strings
        """
        if not text or not text.strip():
            return {"safe": True, "matched_patterns": []}

        matched = []
        for pattern in self.patterns:
            if pattern.search(text):
                matched.append(pattern.pattern)

        return {
            "safe": len(matched) == 0,
            "matched_patterns": matched,
        }

    def get_pattern_count(self) -> int:
        """Return total number of compiled patterns (for parity testing)."""
        return len(self.patterns)
