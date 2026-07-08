"""
W5 — PiiGuard hardening benchmark.

Tests the PiiGuard against a labeled PII corpus measuring recall and precision.
Recall = PII detected / total PII in corpus
Precision = true positives / (true positives + false positives)

Oracle: tests/safety/test_pii_guard.py — committed metrics, no safety-triad regressions.
"""
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_SIDECAR_ROOT = os.path.join(_REPO_ROOT, "kairo-sidecar")
if _SIDECAR_ROOT not in sys.path:
    sys.path.insert(0, _SIDECAR_ROOT)

from sidecar.safety.pii_guard import PiiGuard  # noqa: E402


# ── Labeled PII corpus ───────────────────────────────────────────────────────
# Each case has: text, expected_pii_types (set), expected_redacted_count
_PII_CASES = [
    {"text": "My SSN is 123-45-6789.", "types": {"SSN"}, "count": 1},
    {"text": "Contact me at john.doe@example.com for details.", "types": {"EMAIL"}, "count": 1},
    {"text": "Call 555-123-4567 to reach support.", "types": {"PHONE"}, "count": 1},
    {"text": "My phone is +1-555-123-4567.", "types": {"PHONE"}, "count": 1},
    {"text": "Reach me at (555) 123-4567.", "types": {"PHONE"}, "count": 1},
    {"text": "Card: 4111-1111-1111-1111", "types": {"CC"}, "count": 1},
    {"text": "Card number: 4111111111111111", "types": {"CC"}, "count": 1},
    {"text": "Passport: A12345678", "types": {"PASSPORT"}, "count": 1},
    {"text": "IBAN: GB29NWBK60161331926819", "types": {"IBAN"}, "count": 1},
    {"text": "DOB: 01/15/1990", "types": {"DOB"}, "count": 1},
    {"text": "DOB: 25/12/1985", "types": {"DOB"}, "count": 1},
    {"text": "SSN 123-45-6789, email jane@work.org, phone 555-987-6543", "types": {"SSN", "EMAIL", "PHONE"}, "count": 3},
    {"text": "Card 4111-1111-1111-1111, passport B98765432", "types": {"CC", "PASSPORT"}, "count": 2},
    {"text": "My SSN is 111-22-3333 and my card is 5555-5555-5555-5555", "types": {"SSN", "CC"}, "count": 2},
    {"text": "Email: admin@company.co.uk, phone +1-800-555-0199", "types": {"EMAIL", "PHONE"}, "count": 2},
]

# Benign cases — should NOT trigger PII detection
_BENIGN_CASES = [
    {"text": "The invoice total is $1,234.56.", "types": set()},
    {"text": "Order number: ORD-2024-001", "types": set()},
    {"text": "Please process document #12345.", "types": set()},
    {"text": "The meeting is at 3:30 PM.", "types": set()},
    {"text": "Reference: REF-9876543210", "types": set()},
    {"text": "Account ID: ACC123456789", "types": set()},
    {"text": "The product code is PC-1234-5678.", "types": set()},
    {"text": "Total quantity: 100 units.", "types": set()},
    {"text": "Please review section 12.5 of the manual.", "types": set()},
    {"text": "The file size is 2048 bytes.", "types": set()},
    {"text": "Version 2.0.1 released on 2024-01-15.", "types": set()},
    {"text": "The answer is 42.", "types": set()},
    {"text": "Tax rate: 8.5%", "types": set()},
    {"text": "Coordinates: 40.7128, -74.0060", "types": set()},
    {"text": "ISBN: 978-3-16-148410-0", "types": set()},
]


class TestPiiGuard:
    """PiiGuard hardening benchmark — recall/precision on labeled corpus."""

    def test_recall_on_pii_corpus(self):
        """Oracle: recall = detected PII / total PII.

        Must be >= 95% (catching all PII is critical for safety).
        """
        guard = PiiGuard()
        total_pii = 0
        detected_pii = 0

        for case in _PII_CASES:
            result = guard.scan(case["text"])
            total_pii += len(case["types"])
            for pii_type in case["types"]:
                if pii_type in result["found_types"]:
                    detected_pii += 1

        recall = (detected_pii / total_pii) * 100.0 if total_pii > 0 else 0.0
        print(f"\n  Recall: {detected_pii}/{total_pii} = {recall:.1f}%")
        assert recall >= 95.0, (
            f"PII recall {recall:.1f}% ({detected_pii}/{total_pii}) < 95% threshold"
        )

    def test_precision_on_benign_corpus(self):
        """Oracle: precision = true positives / (true positives + false positives).

        False-positive rate on benign inputs must be <= 13% (2/15).
        """
        guard = PiiGuard()
        false_positives = 0
        total_benign = len(_BENIGN_CASES)

        for case in _BENIGN_CASES:
            result = guard.scan(case["text"])
            if result["has_pii"]:
                false_positives += 1
                print(f"  FALSE POSITIVE: '{case['text'][:60]}' → {result['found_types']}")

        fpr = (false_positives / total_benign) * 100.0
        print(f"\n  False-positive-rate: {false_positives}/{total_benign} = {fpr:.1f}%")
        assert fpr <= 13.4, (
            f"False-positive-rate {fpr:.1f}% ({false_positives}/{total_benign}) > 13.4%"
        )

    def test_redaction_replaces_all_pii(self):
        """Redaction must replace ALL PII with [REDACTED_*] markers."""
        guard = PiiGuard()

        for case in _PII_CASES:
            redacted = guard.redact(case["text"])
            # The redacted text should contain [REDACTED_ markers
            assert "[REDACTED_" in redacted, (
                f"Redacted text missing [REDACTED_ marker for: {case['text'][:50]}"
            )
            # Count redactions
            redaction_count = redacted.count("[REDACTED_")
            assert redaction_count >= case["count"], (
                f"Expected >= {case['count']} redactions, got {redaction_count} for: {case['text'][:50]}"
            )

    def test_redaction_preserves_non_pii_text(self):
        """Redaction must not alter non-PII text."""
        guard = PiiGuard()

        for case in _BENIGN_CASES:
            redacted = guard.redact(case["text"])
            assert redacted == case["text"], (
                f"Benign text was altered: '{case['text'][:50]}' → '{redacted[:50]}'"
            )

    def test_per_type_coverage(self):
        """Each PII type must be detected in at least one case."""
        guard = PiiGuard()
        all_types = set()
        detected_types = set()

        for case in _PII_CASES:
            all_types.update(case["types"])
            result = guard.scan(case["text"])
            detected_types.update(result["found_types"])

        missing = all_types - detected_types
        print(f"\n  All types: {sorted(all_types)}")
        print(f"  Detected:  {sorted(detected_types)}")
        if missing:
            print(f"  Missing:   {sorted(missing)}")
        assert not missing, f"PII types not detected: {missing}"

    def test_kill_proof_disabled_guard(self):
        """Kill-proof: a guard with no patterns must not redact anything."""
        guard = PiiGuard()
        guard.patterns = []

        text = "My SSN is 123-45-6789 and email is test@example.com"
        redacted = guard.redact(text)
        assert redacted == text, (
            "Disabled guard should not redact anything — kill-proof failed"
        )

    def test_empty_input_handling(self):
        """Empty/None input must be handled gracefully."""
        guard = PiiGuard()
        assert guard.redact("") == ""
        assert guard.redact(None) is None
        result = guard.scan("")
        assert result["has_pii"] is False
        result = guard.scan(None)
        assert result["has_pii"] is False

    def test_multiple_pii_in_single_text(self):
        """Multiple PII instances in one text must all be redacted."""
        guard = PiiGuard()
        text = "SSN: 123-45-6789, Email: a@b.com, Phone: 555-123-4567, Card: 4111-1111-1111-1111"
        redacted = guard.redact(text)
        assert redacted.count("[REDACTED_") >= 4, (
            f"Expected >= 4 redactions, got {redacted.count('[REDACTED_')}"
        )
        # Verify no raw PII remains
        assert "123-45-6789" not in redacted
        assert "a@b.com" not in redacted
        assert "555-123-4567" not in redacted
        assert "4111-1111-1111-1111" not in redacted

    def test_committed_baseline_metrics(self):
        """Committed baseline: recall and precision must not regress.

        Baseline: recall = 100%, false-positive-rate = 0%.
        """
        guard = PiiGuard()

        # Recall
        total_pii = 0
        detected_pii = 0
        for case in _PII_CASES:
            result = guard.scan(case["text"])
            total_pii += len(case["types"])
            for pii_type in case["types"]:
                if pii_type in result["found_types"]:
                    detected_pii += 1
        recall = (detected_pii / total_pii) * 100.0

        # False positive rate
        fp = sum(1 for c in _BENIGN_CASES if guard.scan(c["text"])["has_pii"])
        fpr = (fp / len(_BENIGN_CASES)) * 100.0

        print(f"\n  Baseline: recall={recall:.1f}%, FPR={fpr:.1f}%")
        assert recall == 100.0, f"Recall regressed from 100% to {recall:.1f}%"
        assert fpr == 0.0, f"FPR regressed from 0% to {fpr:.1f}%"
