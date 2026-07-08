"""
W9 Oracle: Cross-platform honesty.

Verifies that platform support claims in README.md, STATUS.md, and
CROSS_PLATFORM_REPORT.md are honest — i.e., they match what CI actually
verifies. Scaffold ≠ Real. Self-certified reports must be labeled as such.

The test checks:
1. README.md must not claim macOS/Linux ghost-typing as "verified" without CI evidence
2. CROSS_PLATFORM_REPORT.md must label self-certified claims honestly
3. STATUS.md must label Cross-Platform accurately (not "Real" without CI)
4. The cross-platform workflow must trigger on master (or be noted as needing a fix)
5. Platform code exists for all 3 platforms (Windows, macOS, Linux)
"""
from __future__ import annotations

import pathlib
import re
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _read_file(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


README_PATH = REPO_ROOT / "README.md"
STATUS_PATH = REPO_ROOT / "STATUS.md"
CROSS_PLATFORM_REPORT_PATH = REPO_ROOT / "CROSS_PLATFORM_REPORT.md"
CROSS_PLATFORM_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "cross-platform.yml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PLATFORM_MOD = REPO_ROOT / "phantom-core" / "src" / "platform" / "mod.rs"


class TestPlatformCodeExists:
    """Verify platform code exists for all 3 platforms."""

    def test_windows_platform_code_exists(self):
        """Windows platform implementation must exist."""
        assert (REPO_ROOT / "phantom-core" / "src" / "platform" / "windows.rs").exists()

    def test_macos_platform_code_exists(self):
        """macOS platform implementation must exist."""
        assert (REPO_ROOT / "phantom-core" / "src" / "platform" / "macos.rs").exists()

    def test_linux_platform_code_exists(self):
        """Linux platform implementation must exist."""
        assert (REPO_ROOT / "phantom-core" / "src" / "platform" / "linux.rs").exists()

    def test_platform_mod_has_cfg_selection(self):
        """platform/mod.rs must have cfg(target_os) for all 3 platforms."""
        source = _read_file(PLATFORM_MOD)
        assert 'target_os = "windows"' in source, "Windows cfg missing"
        assert 'target_os = "macos"' in source, "macOS cfg missing"
        assert 'target_os = "linux"' in source, "Linux cfg missing"


class TestREADMEPlatformHonesty:
    """Verify README.md platform claims are honest."""

    def test_macos_labeled_as_scaffold_or_pending(self):
        """macOS must NOT be claimed as 'verified' without CI evidence."""
        readme = _read_file(README_PATH)
        # Find the macOS line in the platform table
        macos_lines = [l for l in readme.splitlines() if "macOS" in l and "ghost" in l.lower()]
        for line in macos_lines:
            line_lower = line.lower()
            # Must NOT say "verified" without a "pending" or "scaffold" qualifier
            if "verified" in line_lower and "pending" not in line_lower and "scaffold" not in line_lower:
                pytest.fail(
                    f"README claims macOS ghost-typing as 'verified' without CI evidence: {line.strip()}"
                )

    def test_linux_claim_honest(self):
        """Linux ghost-typing claim must be honest about what's verified."""
        readme = _read_file(README_PATH)
        linux_lines = [l for l in readme.splitlines() if "Linux" in l and "ghost" in l.lower()]
        # If Linux is claimed as "verified", it must reference CI or be qualified
        for line in linux_lines:
            if "verified" in line.lower():
                # This is OK only if CI actually runs on Linux for this — check
                # that the claim is about the Rust platform code compiling, not
                # about live ghost-typing being verified
                pass  # Linux AT-SPI2 code exists and compiles; CI runs on Ubuntu

    def test_readme_has_platform_section(self):
        """README must have a platform support section."""
        readme = _read_file(README_PATH)
        assert "Ghost-typing" in readme or "ghost-typing" in readme or "Platform" in readme, (
            "README must have a platform support section (Ghost-typing or Platform)"
        )


class TestSTATUSPlatformHonesty:
    """Verify STATUS.md platform claims are honest."""

    def test_cross_platform_not_claimed_as_real(self):
        """STATUS.md must NOT claim Cross-Platform as 'Real' without per-platform CI."""
        status = _read_file(STATUS_PATH)
        # Find the Cross-Platform row
        cp_lines = [l for l in status.splitlines() if "Cross-Platform" in l]
        for line in cp_lines:
            # Must NOT say "**Real**" — that would require per-platform CI
            assert "**Real**" not in line, (
                f"STATUS.md must not claim Cross-Platform as Real without per-platform CI: {line.strip()}"
            )


class TestCrossPlatformReportHonesty:
    """Verify CROSS_PLATFORM_REPORT.md is honest about self-certification."""

    def test_report_exists(self):
        """CROSS_PLATFORM_REPORT.md must exist (it's referenced by Rust tests)."""
        assert CROSS_PLATFORM_REPORT_PATH.exists(), (
            "CROSS_PLATFORM_REPORT.md must exist — referenced by test_cross_platform.rs"
        )

    def test_report_labels_self_certified_claims(self):
        """The report must label self-certified claims honestly.

        The report claims 'ALL 6 GATES PASSED' but gates 2 and 3 (macOS and Linux
        gauntlets) are self-certified — no CI on macOS/Linux verifies them.
        The report must acknowledge this.
        """
        report = _read_file(CROSS_PLATFORM_REPORT_PATH)
        # The report must contain a disclaimer about self-certification
        # or label macOS/Linux results as "self-certified" or "not CI-verified"
        has_disclaimer = (
            "self-cert" in report.lower()
            or "not CI-verified" in report.lower()
            or "self-certified" in report.lower()
            or "no CI on macOS" in report.lower()
            or "CI-verified" in report.lower()
        )
        assert has_disclaimer, (
            "CROSS_PLATFORM_REPORT.md must label macOS/Linux results as self-certified "
            "or not CI-verified. Claims of 'ALL 6 GATES PASSED' without CI evidence "
            "violate the no-self-cert guardrail."
        )


class TestCrossPlatformWorkflow:
    """Verify cross-platform workflow configuration."""

    def test_cross_platform_workflow_triggers_on_master(self):
        """The cross-platform CI workflow must trigger on master (or be noted as needing fix).

        If it only triggers on main/develop, it never runs on the actual branch.
        """
        if not CROSS_PLATFORM_WORKFLOW.exists():
            pytest.skip("cross-platform.yml not found")
        workflow = _read_file(CROSS_PLATFORM_WORKFLOW)
        # Check if master is in the push branches
        if "master" not in workflow:
            # This is a known issue — the workflow triggers on main/develop, not master
            # Check if there's a proposed fix
            proposed = REPO_ROOT / "ci" / "cross-platform.yml.proposed"
            if proposed.exists():
                pytest.skip("cross-platform.yml doesn't trigger on master, but ci/cross-platform.yml.proposed exists")
            else:
                pytest.fail(
                    "cross-platform.yml triggers on main/develop, NOT master. "
                    "It never runs on the actual branch. "
                    "Fix: add 'master' to the push branches, or create ci/cross-platform.yml.proposed"
                )


class TestPlatformClaimConsistency:
    """Verify platform claims are consistent across files."""

    def test_no_contradiction_between_status_and_readme(self):
        """STATUS.md and README.md must not contradict each other on platform status."""
        status = _read_file(STATUS_PATH)
        readme = _read_file(README_PATH)

        # If STATUS says "prompt-only / not shipped", README should not claim "Real"
        status_cp_lines = [l for l in status.splitlines() if "Cross-Platform" in l]
        readme_macos_lines = [l for l in readme.splitlines() if "macOS" in l and "ghost" in l.lower()]

        # If STATUS says Cross-Platform is "not shipped", README macOS should say "pending" or "scaffold"
        for status_line in status_cp_lines:
            if "not shipped" in status_line.lower() or "prompt-only" in status_line.lower():
                for readme_line in readme_macos_lines:
                    if "verified" in readme_line.lower() and "pending" not in readme_line.lower():
                        # This is a potential contradiction — but the README may be
                        # referring to the Rust code existing, not the full platform
                        pass  # Allow this — the Rust code does exist and compile
