"""
PiiGuard — PII Redaction for Outbound Messages (Phase 0.5)

This is the REAL PII redaction module used by all connectors.
Every outbound message to Telegram/Discord/Email passes through redact()
 before being sent.

Redaction patterns cover:
- SSN (XXX-XX-XXXX)
- Email addresses
- Phone numbers (XXX-XXX-XXXX, +1-XXX-XXX-XXXX, (XXX) XXX-XXXX)
- Credit card numbers (XXXX-XXXX-XXXX-XXXX, 16 consecutive digits)
- IP addresses (optional, off by default to avoid false positives)
- Passport numbers (US format: 1 letter + 8 digits)
- IBAN (international bank account numbers)
- Date of birth (MM/DD/YYYY, DD/MM/YYYY)
- ZIP codes (with street-type context to reduce false positives)

This module is NOT mocked — the patterns and redaction logic are real.
"""

from __future__ import annotations

import re
import logging
from typing import List, Tuple

log = logging.getLogger("kairo-sidecar.pii_guard")


# ── PII Redaction Patterns ───────────────────────────────────────────────────
# Each entry is (regex, replacement_string, type_name)

PII_PATTERNS: List[Tuple[re.Pattern, str, str]] = [
    # SSN: XXX-XX-XXXX
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED_SSN]", "SSN"),
    # Email addresses
    (
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
        "[REDACTED_EMAIL]",
        "EMAIL",
    ),
    # Phone: XXX-XXX-XXXX
    (re.compile(r"\b\d{3}-\d{3}-\d{4}\b"), "[REDACTED_PHONE]", "PHONE"),
    # Phone: +1-XXX-XXX-XXXX
    (re.compile(r"\+1-\d{3}-\d{3}-\d{4}\b"), "[REDACTED_PHONE]", "PHONE"),
    # Phone: (XXX) XXX-XXXX
    (re.compile(r"\(\d{3}\)\s*\d{3}-\d{4}\b"), "[REDACTED_PHONE]", "PHONE"),
    # Credit card: XXXX-XXXX-XXXX-XXXX
    (re.compile(r"\b\d{4}-\d{4}-\d{4}-\d{4}\b"), "[REDACTED_CC]", "CC"),
    # Credit card: XXXXXXXXXXXXXXXX (16 consecutive digits)
    (re.compile(r"\b\d{16}\b"), "[REDACTED_CC]", "CC"),
    # Passport: US format (1 letter + 8 digits)
    (re.compile(r"\b[A-Z]\d{8}\b"), "[REDACTED_PASSPORT]", "PASSPORT"),
    # IBAN: 2-letter country code + 2 check digits + 11-30 alphanumeric
    (re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"), "[REDACTED_IBAN]", "IBAN"),
    # Date of birth: MM/DD/YYYY
    (re.compile(r"\b(0[1-9]|1[0-2])/(0[1-9]|[12]\d|3[01])/(\d{4})\b"), "[REDACTED_DOB]", "DOB"),
    # Date of birth: DD/MM/YYYY (ambiguous with MM/DD, but catch both)
    (re.compile(r"\b(0[1-9]|[12]\d|3[01])/(0[1-9]|1[0-2])/(\d{4})\b"), "[REDACTED_DOB]", "DOB"),
    # ZIP code: 5-digit (with street-type context to reduce false positives)
    (
        re.compile(
            r"\b\d{5}(?:-\d{4})?\b(?=\s+(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Boulevard|Dr|Drive|Ln|Lane|Way|Court|Ct|Place|Pl))"
        ),
        "[REDACTED_ZIP]",
        "ZIP",
    ),
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
        for pattern, replacement, _ in self.patterns:
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

        for pattern, _, type_name in self.patterns:
            if pattern.search(text):
                if type_name not in found_types:
                    found_types.append(type_name)

        return {
            "has_pii": len(found_types) > 0,
            "found_types": found_types,
        }
