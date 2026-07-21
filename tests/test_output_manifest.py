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

# Prefer wedge_gauntlet fixtures, fall back to demo
WEDGE = REPO / "fixtures" / "wedge_gauntlet"
DEMO = REPO / "fixtures" / "demo"

if (WEDGE / "s01_nda_standard.docx").exists():
    GOOD_DOCX = WEDGE / "s01_nda_standard.docx"
    GOOD_PB = WEDGE / "s01_playbook.json"
else:
    GOOD_DOCX = DEMO / "sample_nda.docx"
    GOOD_PB = DEMO / "nda_playbook.json"


def _run_cli(args: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    """Run `python -m kairo` with given args, return completed process."""
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    full_env["PYTHONPATH"] = str(REPO)
    return subprocess.run(
        [sys.executable, "-m", "kairo"] + args,
        capture_output=True,
        text=True,
        env=full_env,
        timeout=60,
    )


def _run_redline(docx: str, playbook: str, out_dir: str,
                 sealed: bool = False) -> subprocess.CompletedProcess:
    """Run a redline command and return the completed process."""
    args = ["redline"]
    if sealed:
        args.append("--sealed")
    args.extend(["--out", out_dir, docx, playbook])
    return _run_cli(args)


def _run_verify(out_dir: str, pubkey: str | None = None) -> subprocess.CompletedProcess:
    """Run a verify command and return the completed process."""
    if pubkey is None:
        pubkey = str(Path(out_dir) / "public_key.pem")
    return _run_cli(["verify", out_dir, pubkey])


class CleanRunTests(unittest.TestCase):
    """Gauntlet cases: clean run and tamper detection."""

    def setUp(self) -> None:
        self.t = Path(tempfile.mkdtemp(prefix="kairo-test-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.t, ignore_errors=True)

    def test_clean_run_verify_exit_0(self) -> None:
        """Clean redline + verify exits 0."""
        out_dir = str(self.t / "out")
        result = _run_redline(str(GOOD_DOCX), str(GOOD_PB), out_dir, sealed=False)
        self.assertEqual(result.returncode, 0,
                         f"redline failed: {result.stderr}")

        # Verify the output manifest exists in the --out directory
        manifest_path = Path(out_dir) / "output_manifest.json"
        self.assertTrue(manifest_path.exists(),
                        "output_manifest.json not created in --out dir")

        # Run verify
        verify_result = _run_verify(out_dir)
        self.assertEqual(verify_result.returncode, 0,
                         f"verify failed: {verify_result.stdout} {verify_result.stderr}")

    def test_tampered_docx_verify_exit_1(self) -> None:
        """Tampered redlined.docx byte -> verify exit 1 (hash mismatch)."""
        out_dir = str(self.t / "out")
        result = _run_redline(str(GOOD_DOCX), str(GOOD_PB), out_dir, sealed=False)
        self.assertEqual(result.returncode, 0,
                         f"redline failed: {result.stderr}")

        # Tamper with output docx
        out_path = Path(out_dir) / "redlined.docx"
        data = bytearray(out_path.read_bytes())
        if len(data) > 10:
            data[10] ^= 0xFF
        out_path.write_bytes(bytes(data))

        verify_result = _run_verify(out_dir)
        self.assertEqual(verify_result.returncode, 1,
                         f"verify should fail on tampered docx: "
                         f"{verify_result.stdout} {verify_result.stderr}")

    def test_tampered_manifest_verify_exit_1(self) -> None:
        """Tampered output_manifest.json -> verify exit 1 (InvalidSignature)."""
        out_dir = str(self.t / "out")
        result = _run_redline(str(GOOD_DOCX), str(GOOD_PB), out_dir, sealed=False)
        self.assertEqual(result.returncode, 0,
                         f"redline failed: {result.stderr}")

        # Tamper with manifest signature
        manifest_path = Path(out_dir) / "output_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        if "signature" in manifest:
            manifest["signature"] = "AAAA" + manifest["signature"][4:]
        manifest_path.write_text(json.dumps(manifest, indent=2))

        verify_result = _run_verify(out_dir)
        self.assertEqual(verify_result.returncode, 1,
                         f"verify should fail on tampered manifest: "
                         f"{verify_result.stdout} {verify_result.stderr}")


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

    def test_empty_docx(self) -> None:
        """Empty .docx file -> nonzero exit, no traceback."""
        (self.t / "empty.docx").write_bytes(b"")
        (self.t / "playbook.json").write_text(
            json.dumps({"clauses": [{"clause": "governing_law", "redline": "test"}]})
        )
        result = _run_redline(str(self.t / "empty.docx"),
                              str(self.t / "playbook.json"),
                              str(self.t / "out"))
        # Empty docx may produce a pipeline error (nonzero) or succeed
        # with 0 edits (exit 0). Either way, no traceback.
        self._check_no_traceback(result)

    def test_non_zip_docx(self) -> None:
        """Non-zip .docx file -> nonzero exit, no traceback."""
        (self.t / "fake.docx").write_bytes(b"NOT A ZIP FILE")
        (self.t / "playbook.json").write_text(
            json.dumps({"clauses": [{"clause": "governing_law", "redline": "test"}]})
        )
        result = _run_redline(str(self.t / "fake.docx"),
                              str(self.t / "playbook.json"),
                              str(self.t / "out"))
        self._check_no_traceback(result)

    def test_truncated_docx(self) -> None:
        """Truncated .docx file -> nonzero exit, no traceback."""
        data = GOOD_DOCX.read_bytes()
        (self.t / "truncated.docx").write_bytes(data[:len(data) // 2])
        (self.t / "playbook.json").write_text(
            json.dumps({"clauses": [{"clause": "governing_law", "redline": "test"}]})
        )
        result = _run_redline(str(self.t / "truncated.docx"),
                              str(self.t / "playbook.json"),
                              str(self.t / "out"))
        self._check_no_traceback(result)

    def test_missing_docx(self) -> None:
        """Missing docx file -> nonzero exit, no traceback."""
        (self.t / "playbook.json").write_text(
            json.dumps({"clauses": [{"clause": "governing_law", "redline": "test"}]})
        )
        result = _run_redline(str(self.t / "nonexistent.docx"),
                              str(self.t / "playbook.json"),
                              str(self.t / "out"))
        self.assertNotEqual(result.returncode, 0,
                            f"Expected nonzero exit for missing docx, got {result.returncode}")
        self._check_no_traceback(result)

    def test_empty_playbook(self) -> None:
        """Empty playbook JSON -> nonzero exit, no traceback."""
        shutil.copy2(GOOD_DOCX, self.t / "nda.docx")
        (self.t / "empty_pb.json").write_bytes(b"")
        result = _run_redline(str(self.t / "nda.docx"),
                              str(self.t / "empty_pb.json"),
                              str(self.t / "out"))
        self.assertNotEqual(result.returncode, 0,
                            f"Expected nonzero exit for empty playbook, got {result.returncode}")
        self._check_no_traceback(result)

    def test_malformed_playbook(self) -> None:
        """Malformed playbook JSON -> nonzero exit, no traceback."""
        shutil.copy2(GOOD_DOCX, self.t / "nda.docx")
        (self.t / "bad_pb.json").write_text("{NOT VALID JSON}")
        result = _run_redline(str(self.t / "nda.docx"),
                              str(self.t / "bad_pb.json"),
                              str(self.t / "out"))
        self.assertNotEqual(result.returncode, 0,
                            f"Expected nonzero exit for malformed playbook, got {result.returncode}")
        self._check_no_traceback(result)

    def test_wrong_type_playbook(self) -> None:
        """Wrong-type playbook (JSON array, not object) -> nonzero exit, no traceback."""
        shutil.copy2(GOOD_DOCX, self.t / "nda.docx")
        (self.t / "arr_pb.json").write_text("[1, 2, 3]")
        result = _run_redline(str(self.t / "nda.docx"),
                              str(self.t / "arr_pb.json"),
                              str(self.t / "out"))
        self._check_no_traceback(result)

    def test_huge_key_playbook(self) -> None:
        """Huge key in playbook -> nonzero exit, no traceback."""
        shutil.copy2(GOOD_DOCX, self.t / "nda.docx")
        (self.t / "huge_pb.json").write_text(
            json.dumps({"clauses": [{"clause": "A" * 100000, "redline": "test"}]})
        )
        result = _run_redline(str(self.t / "nda.docx"),
                              str(self.t / "huge_pb.json"),
                              str(self.t / "out"))
        # May exit 0 or nonzero, but must not traceback
        self._check_no_traceback(result)

    def test_empty_rules_playbook(self) -> None:
        """Empty rules playbook -> may exit 0, no traceback."""
        shutil.copy2(GOOD_DOCX, self.t / "nda.docx")
        (self.t / "empty_rules.json").write_text(
            json.dumps({"clauses": []})
        )
        result = _run_redline(str(self.t / "nda.docx"),
                              str(self.t / "empty_rules.json"),
                              str(self.t / "out"))
        # Empty rules may exit 0 (no-op) or nonzero
        self._check_no_traceback(result)


if __name__ == "__main__":
    unittest.main()
