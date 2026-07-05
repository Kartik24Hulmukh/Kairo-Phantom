# PROVENANCE: original | Code domain oracle tests per VERIFICATION_ORACLES.md
"""Code domain oracle tests — compile_test_pass + parse_validity + kill-proofs.

Tests verify:
  1. compile_test_pass: after a code edit, parse + compile + test all pass.
     Kill-proof: introduce a syntax error OR break a test → FAILS.
  2. parse_validity: tree-sitter AST has zero ERROR nodes.
     Kill-proof: inject malformed syntax → FAILS.
  3. Honest degradation: tree-sitter/pytest unavailable → FAIL LOUD.
  4. >=3 gauntlet scenarios: (a) fix a failing test → now passes,
     (b) add a function + new test that passes, (c) broken edit caught.
  5. Trust stack integration: audit log + egress report.
  6. CLI integration: code subcommand works end-to-end.

All tests run fully offline. No mocks on production paths. Zero skips.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from kairo.domains.code.engine import (  # noqa: E402
    apply_edit,
    code_pipeline,
    write_file,
)
from kairo.domains.code.oracles import (  # noqa: E402
    compile_test_pass,
    parse_validity,
)

# Fixture paths
_FIX = os.path.join(_REPO_ROOT, "kairo", "domains", "code", "fixtures", "myproject")
_CALC_PY = os.path.join(_FIX, "calculator.py")
_TEST_PY = os.path.join(_FIX, "tests", "test_calculator.py")


# ---------------------------------------------------------------------------
# Helper: check toolchain availability
# ---------------------------------------------------------------------------


def _toolchain_available() -> bool:
    try:
        import tree_sitter  # noqa: F401
        import tree_sitter_python  # noqa: F401
        import pytest  # noqa: F401

        return True
    except ImportError:
        return False


_HAS_TOOLCHAIN = _toolchain_available()


# ---------------------------------------------------------------------------
# Helper: copy fixture project to temp dir
# ---------------------------------------------------------------------------


def _copy_fixture_project(tmpdir: str) -> str:
    """Copy the fixture project to a temp directory and return the path."""
    dest = os.path.join(tmpdir, "myproject")
    shutil.copytree(_FIX, dest)
    return dest


# ---------------------------------------------------------------------------
# Oracle 1: compile_test_pass
# ---------------------------------------------------------------------------


class TestCompileTestPass:
    """compile_test_pass oracle: parse + compile + test all pass."""

    def test_clean_project_passes(self):
        """A clean fixture project passes all checks."""
        if not _HAS_TOOLCHAIN:
            pytest.fail("code toolchain not available — cannot test compile_test_pass")

        with tempfile.TemporaryDirectory() as tmp:
            project = _copy_fixture_project(tmp)
            passed = compile_test_pass(project)
            assert passed, "compile_test_pass should pass for a clean project"

    def test_kill_proof_syntax_error_fails(self):
        """Kill-proof: introduce a syntax error → oracle FAILS."""
        if not _HAS_TOOLCHAIN:
            pytest.fail("code toolchain not available")

        with tempfile.TemporaryDirectory() as tmp:
            project = _copy_fixture_project(tmp)
            calc_file = os.path.join(project, "calculator.py")

            # Inject a syntax error
            with open(calc_file, "a", encoding="utf-8") as f:
                f.write("\ndef broken(:\n    pass\n")

            with pytest.raises(AssertionError, match="parse errors|compile error"):
                compile_test_pass(project)

    def test_kill_proof_broken_test_fails(self):
        """Kill-proof: break a test assertion → oracle FAILS."""
        if not _HAS_TOOLCHAIN:
            pytest.fail("code toolchain not available")

        with tempfile.TemporaryDirectory() as tmp:
            project = _copy_fixture_project(tmp)
            test_file = os.path.join(project, "tests", "test_calculator.py")

            # Break a test assertion
            with open(test_file, "r", encoding="utf-8") as f:
                content = f.read()
            content = content.replace("assert add(2, 3) == 5", "assert add(2, 3) == 999")
            with open(test_file, "w", encoding="utf-8") as f:
                f.write(content)

            with pytest.raises(AssertionError, match="pytest exit code|failures"):
                compile_test_pass(project)


# ---------------------------------------------------------------------------
# Oracle 2: parse_validity
# ---------------------------------------------------------------------------


class TestParseValidity:
    """parse_validity oracle: tree-sitter AST has zero ERROR nodes."""

    def test_valid_file_passes(self):
        """A valid .py file parses with zero ERROR nodes."""
        if not _HAS_TOOLCHAIN:
            pytest.fail("code toolchain not available")

        with tempfile.TemporaryDirectory() as tmp:
            project = _copy_fixture_project(tmp)
            calc_file = os.path.join(project, "calculator.py")
            passed = parse_validity(calc_file)
            assert passed

    def test_kill_proof_malformed_syntax_fails(self):
        """Kill-proof: inject malformed syntax → oracle FAILS."""
        if not _HAS_TOOLCHAIN:
            pytest.fail("code toolchain not available")

        with tempfile.TemporaryDirectory() as tmp:
            bad_file = os.path.join(tmp, "bad.py")
            # Missing colon after def — tree-sitter flags as ERROR
            write_file(bad_file, "def broken()\n    return 1\n")

            with pytest.raises(AssertionError, match="ERROR nodes"):
                parse_validity(bad_file)

    def test_kill_proof_missing_colon_fails(self):
        """Kill-proof: missing colon after def → oracle FAILS."""
        if not _HAS_TOOLCHAIN:
            pytest.fail("code toolchain not available")

        with tempfile.TemporaryDirectory() as tmp:
            bad_file = os.path.join(tmp, "bad2.py")
            write_file(bad_file, "def broken()\n    return 1\n")

            with pytest.raises(AssertionError, match="ERROR nodes"):
                parse_validity(bad_file)


# ---------------------------------------------------------------------------
# Honest degradation
# ---------------------------------------------------------------------------


class TestHonestDegradation:
    """Toolchain missing → FAIL LOUD, never fake results."""

    def test_pipeline_without_toolchain_fails_loud(self):
        """If tree-sitter is not installed, pipeline must fail with clear error."""
        if _HAS_TOOLCHAIN:
            # If toolchain IS installed, verify the pipeline works
            with tempfile.TemporaryDirectory() as tmp:
                project = _copy_fixture_project(tmp)
                result = code_pipeline(project_dir=project)
                assert result.ok, "Pipeline should succeed when toolchain is available"
        else:
            with tempfile.TemporaryDirectory() as tmp:
                project = _copy_fixture_project(tmp)
                result = code_pipeline(project_dir=project)
                assert not result.ok
                assert "code toolchain unavailable" in result.error.lower()


# ---------------------------------------------------------------------------
# Gauntlet scenarios (>=3, zero skips)
# ---------------------------------------------------------------------------


class TestGauntletScenarios:
    ">=3 end-to-end gauntlet scenarios." ""

    def test_scenario_a_fix_failing_test(self):
        """Scenario (a): fix a deliberately failing test → now passes."""
        if not _HAS_TOOLCHAIN:
            pytest.fail("code toolchain not available")

        with tempfile.TemporaryDirectory() as tmp:
            project = _copy_fixture_project(tmp)
            calc_file = os.path.join(project, "calculator.py")

            # First, break the add function (use enough context to be unique)
            apply_edit(calc_file, "    return a + b\n", "    return a - b\n")

            # Verify it fails
            with pytest.raises(AssertionError, match="pytest exit code|failures"):
                compile_test_pass(project)

            # Now fix it (use enough context to be unique)
            apply_edit(
                calc_file,
                "    return a - b\n\n\ndef subtract",
                "    return a + b\n\n\ndef subtract",
            )

            # Verify it passes now
            passed = compile_test_pass(project)
            assert passed, "After fixing the bug, compile_test_pass should pass"

    def test_scenario_b_add_function_and_test(self):
        """Scenario (b): add a function + a new test that passes."""
        if not _HAS_TOOLCHAIN:
            pytest.fail("code toolchain not available")

        with tempfile.TemporaryDirectory() as tmp:
            project = _copy_fixture_project(tmp)
            calc_file = os.path.join(project, "calculator.py")
            test_file = os.path.join(project, "tests", "test_calculator.py")

            # Add a new function to calculator.py
            apply_edit(
                calc_file,
                "    return result\n",
                "    return result\n\n\ndef power(base: int, exp: int) -> int:\n"
                '    """Return base raised to the power of exp."""\n'
                "    return base ** exp\n",
            )

            # Add a test for the new function
            with open(test_file, "a", encoding="utf-8") as f:
                f.write(
                    "\n\nclass TestPower:\n"
                    "    def test_power_positive(self):\n"
                    "        from calculator import power\n"
                    "        assert power(2, 3) == 8\n\n"
                    "    def test_power_zero(self):\n"
                    "        from calculator import power\n"
                    "        assert power(5, 0) == 1\n"
                )

            # Verify the project still passes
            passed = compile_test_pass(project)
            assert passed, "After adding a function + test, compile_test_pass should pass"

    def test_scenario_c_broken_edit_caught(self):
        """Scenario (c): a deliberately broken edit the oracle must catch."""
        if not _HAS_TOOLCHAIN:
            pytest.fail("code toolchain not available")

        with tempfile.TemporaryDirectory() as tmp:
            project = _copy_fixture_project(tmp)
            calc_file = os.path.join(project, "calculator.py")

            # Break the multiply function with a syntax error
            apply_edit(calc_file, "return a * b", "return a *  # missing operand")

            # The oracle must catch this
            with pytest.raises(AssertionError, match="parse errors|compile error"):
                compile_test_pass(project)


# ---------------------------------------------------------------------------
# Trust stack integration
# ---------------------------------------------------------------------------


class TestTrustStackIntegration:
    """Audit log + zero-egress report integration."""

    def test_pipeline_emits_audit_and_egress(self):
        """Pipeline with private_key emits audit log + egress report."""
        if not _HAS_TOOLCHAIN:
            pytest.fail("code toolchain not available")

        private_key = ed25519.Ed25519PrivateKey.generate()

        with tempfile.TemporaryDirectory() as tmp:
            project = _copy_fixture_project(tmp)
            result = code_pipeline(
                project_dir=project,
                private_key=private_key,
            )
            assert result.ok
            assert result.audit_log_json, "Audit log JSON should be non-empty"
            assert result.egress_report_json, "Egress report JSON should be non-empty"

            from kairo.oracles.ed25519_audit_log import Ed25519AuditLog
            from kairo.oracles.zero_egress_report import (
                report_from_json,
                verify_zero_egress_report,
            )

            public_key = private_key.public_key()
            entries = Ed25519AuditLog.entries_from_json(result.audit_log_json)
            assert len(entries) > 0
            assert Ed25519AuditLog.verify_chain(entries, public_key)

            report = report_from_json(result.egress_report_json)
            assert verify_zero_egress_report(report, public_key)


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestCLIIntegration:
    """code CLI subcommand works end-to-end via registry."""

    def test_cli_verify(self):
        """`kairo code verify` produces output + audit artifacts."""
        if not _HAS_TOOLCHAIN:
            pytest.fail("code toolchain not available")

        from kairo.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            project = _copy_fixture_project(tmp)
            out_dir = os.path.join(tmp, "code_output")
            rc = main(["code", "verify", project, "--outdir", out_dir])
            assert rc == 0, f"CLI verify failed with exit code {rc}"
            assert os.path.isfile(os.path.join(out_dir, "audit_log.json"))
            assert os.path.isfile(os.path.join(out_dir, "zero_egress_report.json"))

    def test_cli_parse(self):
        """`kairo code parse` checks a single file."""
        if not _HAS_TOOLCHAIN:
            pytest.fail("code toolchain not available")

        from kairo.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            project = _copy_fixture_project(tmp)
            calc_file = os.path.join(project, "calculator.py")
            rc = main(["code", "parse", calc_file, "--outdir", os.path.join(tmp, "out")])
            assert rc == 0, f"CLI parse failed with exit code {rc}"
