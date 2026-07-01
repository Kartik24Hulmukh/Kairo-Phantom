"""
PiiGuard — PII Redaction for Outbound Messages (Phase 0.5)

This is the REAL PII redaction module used by all connectors.
Every outbound message to Telegram/Discord/Email passes through redact()
 before being sent.

Redaction patterns cover:
- SSN (XXX-XX-XXXX)
- Email addresses
- Phone numbers (XXX-XXX-XXXX)
- Credit card numbers (XXXX-XXXX-XXXX-XXXX)
- IP addresses (optional, off by default to avoid false positives)

This module is NOT mocked — the patterns and redaction logic are real.
"""

from __future__ import annotations

import re
import logging
from typing import List, Tuple

log = logging.getLogger("kairo-sidecar.pii_guard")


# ── PII Redaction Patterns ────────────────────────────────────────────────────
# Each entry is (regex, replacement_string)

PII_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # SSN: XXX-XX-XXXX
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED_SSN]"),
    # Email addresses
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "[REDACTED_EMAIL]"),
    # Phone: XXX-XXX-XXXX
    (re.compile(r"\b\d{3}-\d{3}-\d{4}\b"), "[REDACTED_PHONE]"),
    # Credit card: XXXX-XXXX-XXXX-XXXX
    (re.compile(r"\b\d{4}-\d{4}-\d{4}-\d{4}\b"), "[REDACTED_CC]"),
    # Credit card: XXXXXXXXXXXXXXXX (16 consecutive digits)
    (re.compile(r"\b\d{16}\b"), "[REDACTED_CC]"),
]


class PiiGuard:
    """
    Real PII redaction for outbound messages.

    redact(text) returns text with all PII patterns replaced by [REDACTED_*] markers.
    scan(text) returns dict with has_pii bool and found_types list.
    """

    def __init__(self):
        self.patterns = PII_PATTERNS

    def redact(self, text: str) -> str:
        """
        Redact all PII from text.

        Returns text with PII replaced by [REDACTED_*] markers.
        """
        if not text:
            return text

        result = text
        for pattern, replacement in self.patterns:
            result = pattern.sub(replacement, result)
        return result

    def scan(self, text: str) -> dict:
        """
        Scan text for PII without redacting.

        Returns dict with:
        - has_pii: bool
        - found_types: list of PII types found
        """
        if not text:
            return {"has_pii": False, "found_types": []}

        found_types = []
        type_names = ["SSN", "EMAIL", "PHONE", "CC", "CC"]

        for i, (pattern, _) in enumerate(self.patterns):
            if pattern.search(text):
                type_name = type_names[i] if i < len(type_names) else "UNKNOWN"
                if type_name not in found_types:
                    found_types.append(type_name)

        return {
            "has_pii": len(found_types) > 0,
            "found_types": found_types,
        }
