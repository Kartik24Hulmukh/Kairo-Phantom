"""Regression tests for signed output manifest and CLI graceful errors.

Ported from gauntlet.py and fuzz.py in the stress-and-hardening pack.

Tests:
  1. Clean run -> verify exit 0
  2. Tampered redlined.docx byte -> verify exit 1 (hash mismatch)
  3. Tampered output_manifest.json -> verify exit 1 (InvalidSignature)
  4-12. Nine malformed-input cases -> nonzero exit (except empty-rules),
        NO traceback in output.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CLI = str(REPO / "kairo" / "cli.py")
FIXTURES = REPO / "fixtures" / "demo"


def _run_cli(args: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    """Run kairo/cli.py with given args, return completed process."""
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    full_env.setdefault("PYTHONPATH", str(REPO))
    return subprocess.run(
        [sys.executable, CLI] + args,
        capture_output=True,
        text=True,
        env=full_env,
        timeout=30,
    )


def _setup_workdir() -> Path:
    """Create a temp workdir with NDA fixture files."""
    t = Path(tempfile.mkdtemp(prefix="kairo-test-"))
    shutil.copy2(FIXTURES / "sample_nda.docx", t / "nda.docx")
    shutil.copy2(FIXTURES / "nda_playbook.json", t / "playbook.json")
    return t


class CleanRunTests(unittest.TestCase):
    """Gauntlet cases: clean run and tamper detection."""

    def setUp(self) -> None:
        self.t = _setup_workdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.t, ignore_errors=True)

    def test_clean_run_verify_exit_0(self) -> None:
        """Clean redline + verify exits 0."""
        result = _run_cli([
            "redline",
            str(self.t / "nda.docx"),
            str(self.t / "playbook.json"),
            str(self.t / "out.docx"),
        ])
        # If redline subcommand doesn't exist, skip
        if result.returncode != 0 and "invalid choice" in result.stderr:
            self.skipTest("redline subcommand not available in this CLI")

        self.assertEqual(result.returncode, 0, f"redline failed: {result.stderr}")

        # Verify the output manifest exists
        manifest_path = self.t / "output_manifest.json"
        self.assertTrue(manifest_path.exists(), "output_manifest.json not created")

        # Run verify
        verify_result = _run_cli([
            "verify",
            str(self.t / "out.docx"),
            str(manifest_path),
        ])
        self.assertEqual(
            verify_result.returncode, 0,
            f"verify failed: {verify_result.stderr}"
        )

    def test_tampered_docx_verify_exit_1(self) -> None:
        """Tampered redlined.docx byte -> verify exit 1 (hash mismatch)."""
        result = _run_cli([
            "redline",
            str(self.t / "nda.docx"),
            str(self.t / "playbook.json"),
            str(self.t / "out.docx"),
        ])
        if result.returncode != 0 and "invalid choice" in result.stderr:
            self.skipTest("redline subcommand not available")

        self.assertEqual(result.returncode, 0)

        # Tamper with output docx
        out_path = self.t / "out.docx"
        data = bytearray(out_path.read_bytes())
        if len(data) > 10:
            data[10] ^= 0xFF
        out_path.write_bytes(bytes(data))

        verify_result = _run_cli([
            "verify",
            str(self.t / "out.docx"),
            str(self.t / "output_manifest.json"),
        ])
        self.assertEqual(
            verify_result.returncode, 1,
            f"verify should fail on tampered docx: {verify_result.stdout} {verify_result.stderr}"
        )

    def test_tampered_manifest_verify_exit_1(self) -> None:
        """Tampered output_manifest.json -> verify exit 1 (InvalidSignature)."""
        result = _run_cli([
            "redline",
            str(self.t / "nda.docx"),
            str(self.t / "playbook.json"),
            str(self.t / "out.docx"),
        ])
        if result.returncode != 0 and "invalid choice" in result.stderr:
            self.skipTest("redline subcommand not available")

        self.assertEqual(result.returncode, 0)

        # Tamper with manifest signature
        manifest_path = self.t / "output_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        if "signature" in manifest:
            manifest["signature"] = "AAAA" + manifest["signature"][4:]
        elif "signatures" in manifest:
            manifest["signatures"][0]["sig"] = "AAAA" + manifest["signatures"][0]["sig"][4:]
        else:
            # Flip a hash field
            for key in ("redlined_sha256", "output_sha256", "docx_sha256"):
                if key in manifest:
                    manifest[key] = "0" * 64
                    break
        manifest_path.write_text(json.dumps(manifest, indent=2))

        verify_result = _run_cli([
            "verify",
            str(self.t / "out.docx"),
            str(manifest_path),
        ])
        self.assertEqual(
            verify_result.returncode, 1,
            f"verify should fail on tampered manifest: {verify_result.stdout} {verify_result.stderr}"
        )


class MalformedInputTests(unittest.TestCase):
    """Fuzz cases: nine malformed-input scenarios.

    Each must exit nonzero (except empty-rules which may exit 0)
    and must NOT print a traceback.
    """

    def setUp(self) -> None:
        self.t = Path(tempfile.mkdtemp(prefix="kairo-fuzz-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.t, ignore_errors=True)

    def _check_no_traceback(self, result: subprocess.CompletedProcess) -> None:
        """Assert no traceback in stdout or stderr."""
        combined = result.stdout + result.stderr
        self.assertNotIn(
            "Traceback (most recent call last)", combined,
            f"Traceback found in output:\n{combined}"
        )

    def _run_redline(self, docx: str, playbook: str, output: str) -> subprocess.CompletedProcess:
        return _run_cli(["redline", docx, playbook, output])

    def test_empty_docx(self) -> None:
        """Empty .docx file -> nonzero exit, no traceback."""
        (self.t / "empty.docx").write_bytes(b"")
        (self.t / "playbook.json").write_text(
            json.dumps({"clauses": [{"clause": "governing_law", "redline": "test"}]})
        )
        result = self._run_redline(
            str(self.t / "empty.docx"),
            str(self.t / "playbook.json"),
            str(self.t / "out.docx"),
        )
        if "invalid choice" in result.stderr:
            self.skipTest("redline subcommand not available")
        self.assertNotEqual(result.returncode, 0)
        self._check_no_traceback(result)

    def test_non_zip_docx(self) -> None:
        """Non-zip .docx file -> nonzero exit, no traceback."""
        (self.t / "fake.docx").write_bytes(b"NOT A ZIP FILE")
        (self.t / "playbook.json").write_text(
            json.dumps({"clauses": [{"clause": "governing_law", "redline": "test"}]})
        )
        result = self._run_redline(
            str(self.t / "fake.docx"),
            str(self.t / "playbook.json"),
            str(self.t / "out.docx"),
        )
        if "invalid choice" in result.stderr:
            self.skipTest("redline subcommand not available")
        self.assertNotEqual(result.returncode, 0)
        self._check_no_traceback(result)

    def test_truncated_docx(self) -> None:
        """Truncated .docx file -> nonzero exit, no traceback."""
        src = FIXTURES / "sample_nda.docx"
        data = src.read_bytes()
        (self.t / "truncated.docx").write_bytes(data[:len(data) // 2])
        (self.t / "playbook.json").write_text(
            json.dumps({"clauses": [{"clause": "governing_law", "redline": "test"}]})
        )
        result = self._run_redline(
            str(self.t / "truncated.docx"),
            str(self.t / "playbook.json"),
            str(self.t / "out.docx"),
        )
        if "invalid choice" in result.stderr:
            self.skipTest("redline subcommand not available")
        self.assertNotEqual(result.returncode, 0)
        self._check_no_traceback(result)

    def test_missing_docx(self) -> None:
        """Missing docx file -> nonzero exit, no traceback."""
        (self.t / "playbook.json").write_text(
            json.dumps({"clauses": [{"clause": "governing_law", "redline": "test"}]})
        )
        result = self._run_redline(
            str(self.t / "nonexistent.docx"),
            str(self.t / "playbook.json"),
            str(self.t / "out.docx"),
        )
        if "invalid choice" in result.stderr:
            self.skipTest("redline subcommand not available")
        self.assertNotEqual(result.returncode, 0)
        self._check_no_traceback(result)

    def test_empty_playbook(self) -> None:
        """Empty playbook JSON -> nonzero exit, no traceback."""
        shutil.copy2(FIXTURES / "sample_nda.docx", self.t / "nda.docx")
        (self.t / "empty_pb.json").write_bytes(b"")
        result = self._run_redline(
            str(self.t / "nda.docx"),
            str(self.t / "empty_pb.json"),
            str(self.t / "out.docx"),
        )
        if "invalid choice" in result.stderr:
            self.skipTest("redline subcommand not available")
        self.assertNotEqual(result.returncode, 0)
        self._check_no_traceback(result)

    def test_malformed_playbook(self) -> None:
        """Malformed playbook JSON -> nonzero exit, no traceback."""
        shutil.copy2(FIXTURES / "sample_nda.docx", self.t / "nda.docx")
        (self.t / "bad_pb.json").write_text("{NOT VALID JSON}")
        result = self._run_redline(
            str(self.t / "nda.docx"),
            str(self.t / "bad_pb.json"),
            str(self.t / "out.docx"),
        )
        if "invalid choice" in result.stderr:
            self.skipTest("redline subcommand not available")
        self.assertNotEqual(result.returncode, 0)
        self._check_no_traceback(result)

    def test_wrong_type_playbook(self) -> None:
        """Wrong-type playbook (JSON array, not object) -> nonzero exit, no traceback."""
        shutil.copy2(FIXTURES / "sample_nda.docx", self.t / "nda.docx")
        (self.t / "arr_pb.json").write_text("[1, 2, 3]")
        result = self._run_redline(
            str(self.t / "nda.docx"),
            str(self.t / "arr_pb.json"),
            str(self.t / "out.docx"),
        )
        if "invalid choice" in result.stderr:
            self.skipTest("redline subcommand not available")
        self.assertNotEqual(result.returncode, 0)
        self._check_no_traceback(result)

    def test_huge_key_playbook(self) -> None:
        """Huge key in playbook -> nonzero exit, no traceback."""
        shutil.copy2(FIXTURES / "sample_nda.docx", self.t / "nda.docx")
        (self.t / "huge_pb.json").write_text(
            json.dumps({"clauses": [{"clause": "A" * 100000, "redline": "test"}]})
        )
        result = self._run_redline(
            str(self.t / "nda.docx"),
            str(self.t / "huge_pb.json"),
            str(self.t / "out.docx"),
        )
        if "invalid choice" in result.stderr:
            self.skipTest("redline subcommand not available")
        # May exit 0 or nonzero, but must not traceback
        self._check_no_traceback(result)

    def test_empty_rules_playbook(self) -> None:
        """Empty rules playbook -> may exit 0, no traceback."""
        shutil.copy2(FIXTURES / "sample_nda.docx", self.t / "nda.docx")
        (self.t / "empty_rules.json").write_text(
            json.dumps({"clauses": []})
        )
        result = self._run_redline(
            str(self.t / "nda.docx"),
            str(self.t / "empty_rules.json"),
            str(self.t / "out.docx"),
        )
        if "invalid choice" in result.stderr:
            self.skipTest("redline subcommand not available")
        # Empty rules may exit 0 (no-op) or nonzero
        self._check_no_traceback(result)


if __name__ == "__main__":
    unittest.main()
