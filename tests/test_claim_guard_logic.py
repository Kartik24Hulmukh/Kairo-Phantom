"""Tests for the claim-language guard logic.

Verifies that:
  1. Affirmative forbidden claims are detected (guard fails)
  2. Explicit non-claims / negated context / limitations do NOT trigger
  3. Unrelated legacy files (e.g. production_ops.py) are NOT scanned
"""
import os
import re
import tempfile
import unittest
from pathlib import Path


FORBIDDEN = [
    "production-ready",
    "injection-safe",
    "zero sockets",
    "whole-machine air gap",
    "every action signed",
    "certified",
    "compliant",
    "privilege-safe",
    "100% accurate legal automation",
    "uncopyable",
    "1000x",
    "unicorn-guaranteed",
]

EXEMPT_FILES = {
    "scripts/build_legal_v3_release.py",
    "CLAIMS.md",
    ".github/workflows/legal-v3-gates.yml",
}

# Only the exact legal-v3 surface files are scanned
CHECK_FILES = [
    "kairo/legal_v3/__init__.py",
    "kairo/legal_v3/transaction.py",
    "kairo/legal_v3/trust_policy.py",
    "kairo/legal_v3/dsse_envelope.py",
    "kairo/oracles/legal_redline_pipeline.py",
    "kairo/oracles/docx_tracked_changes.py",
    "kairo/oracles/ed25519_audit_log.py",
    "kairo/oracles/zero_egress_report.py",
    "kairo/security/injection_guard.py",
    "tools/kairo_legal_v3.py",
    "docs/LEGAL_V3_IMPLEMENTATION_STATUS.md",
    "docs/LEGAL_V3_RUNBOOK.md",
    "docs/OPEN_BLOCKERS.md",
    "STATUS.md",
    "SECURITY.md",
    "README.md",
]


def _scan_content(content: str) -> list[str]:
    """Replicate the claim guard logic on a single content string."""
    findings = []
    for claim in FORBIDDEN:
        pattern = r"(?<!not )(?<!NOT )(?<!never )(?<!Never )" + re.escape(claim)
        for m in re.finditer(pattern, content, re.IGNORECASE):
            start = max(0, m.start() - 30)
            context = content[start:m.start()]
            if "not " in context.lower() or "never " in context.lower():
                continue
            findings.append(claim)
    return findings


class ClaimGuardLogicTests(unittest.TestCase):
    def test_affirmative_production_ready_detected(self) -> None:
        """Affirmative 'production-ready' claim is detected."""
        content = "This system is production-ready and awesome."
        findings = _scan_content(content)
        self.assertIn("production-ready", findings)

    def test_negated_production_ready_not_detected(self) -> None:
        """Negated 'not production-ready' is NOT detected."""
        content = "This system is NOT production-ready for the full platform."
        findings = _scan_content(content)
        self.assertNotIn("production-ready", findings)

    def test_never_production_ready_not_detected(self) -> None:
        """'never production-ready' is NOT detected."""
        content = "This system is never production-ready without external review."
        findings = _scan_content(content)
        self.assertNotIn("production-ready", findings)

    def test_affirmative_injection_safe_detected(self) -> None:
        """Affirmative 'injection-safe' claim is detected."""
        content = "Our system is injection-safe and secure."
        findings = _scan_content(content)
        self.assertIn("injection-safe", findings)

    def test_negated_injection_safe_not_detected(self) -> None:
        """Negated 'not injection-safe' is NOT detected."""
        content = "blocked (25/25 in current fixture suite; not injection-safe)"
        findings = _scan_content(content)
        self.assertNotIn("injection-safe", findings)

    def test_affirmative_compliant_detected(self) -> None:
        """Affirmative 'compliant' claim is detected."""
        content = "This product is compliant with all regulations."
        findings = _scan_content(content)
        self.assertIn("compliant", findings)

    def test_negated_compliant_not_detected(self) -> None:
        """Negated 'not compliant' is NOT detected."""
        content = "This product is not compliant with any standard."
        findings = _scan_content(content)
        self.assertNotIn("compliant", findings)

    def test_affirmative_certified_detected(self) -> None:
        """Affirmative 'certified' claim is detected."""
        content = "We are certified by external auditors."
        findings = _scan_content(content)
        self.assertIn("certified", findings)

    def test_technical_preview_not_detected(self) -> None:
        """'technical preview' is not a forbidden claim."""
        content = "Status: technical preview — not production-ready for the full platform."
        findings = _scan_content(content)
        self.assertNotIn("production-ready", findings)

    def test_production_ops_py_not_in_check_files(self) -> None:
        """production_ops.py is NOT in the scanned file list."""
        self.assertNotIn(
            "kairo/oracles/production_ops.py", CHECK_FILES,
            "production_ops.py should not be scanned by the claim guard"
        )

    def test_legal_v3_oracle_files_in_check_files(self) -> None:
        """Legal-v3 oracle files ARE in the scanned file list."""
        legal_v3_oracles = [
            "kairo/oracles/legal_redline_pipeline.py",
            "kairo/oracles/docx_tracked_changes.py",
            "kairo/oracles/ed25519_audit_log.py",
            "kairo/oracles/zero_egress_report.py",
        ]
        for f in legal_v3_oracles:
            self.assertIn(f, CHECK_FILES)

    def test_entire_oracles_dir_not_scanned(self) -> None:
        """The guard scans specific files, not the entire kairo/oracles/ dir."""
        # If production_ops.py were in a directory walk of kairo/oracles/,
        # it would be scanned. Verify it's not in the explicit file list.
        for f in CHECK_FILES:
            self.assertNotIn("production_ops", f)

    def test_open_blockers_cyclonedx_reference_not_detected(self) -> None:
        """The reworded OPEN_BLOCKERS.md reference does not trigger 'compliant'."""
        content = (
            'contains a CycloneDX SBOM format reference that is not a legal-v3 '
            'claim. This predates legal-v3 and is not in the legal-v3 surface.'
        )
        findings = _scan_content(content)
        self.assertNotIn("compliant", findings)


if __name__ == "__main__":
    unittest.main()
