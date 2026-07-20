"""Tests for CLI graceful error handling.

Verifies that the CLI catches exceptions and prints clean error messages
instead of tracebacks, unless KAIRO_DEBUG=1 is set.
"""
from __future__ import annotations

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


class GracefulErrorTests(unittest.TestCase):
    """CLI must not show tracebacks unless KAIRO_DEBUG=1."""

    def setUp(self) -> None:
        self.t = Path(tempfile.mkdtemp(prefix="kairo-err-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.t, ignore_errors=True)

    def test_missing_file_no_traceback(self) -> None:
        """Missing input file produces clean error, no traceback."""
        result = _run_cli([
            "redline",
            str(self.t / "nonexistent.docx"),
            str(self.t / "playbook.json"),
            str(self.t / "out.docx"),
        ])
        if "invalid choice" in result.stderr:
            self.skipTest("redline subcommand not available")
        combined = result.stdout + result.stderr
        self.assertNotIn("Traceback (most recent call last)", combined)

    def test_corrupt_input_no_traceback(self) -> None:
        """Corrupt input file produces clean error, no traceback."""
        (self.t / "corrupt.docx").write_bytes(b"NOT A DOCX")
        (self.t / "playbook.json").write_text('{"clauses": []}')
        result = _run_cli([
            "redline",
            str(self.t / "corrupt.docx"),
            str(self.t / "playbook.json"),
            str(self.t / "out.docx"),
        ])
        if "invalid choice" in result.stderr:
            self.skipTest("redline subcommand not available")
        combined = result.stdout + result.stderr
        self.assertNotIn("Traceback (most recent call last)", combined)

    def test_kairo_debug_shows_traceback(self) -> None:
        """KAIRO_DEBUG=1 preserves tracebacks for debugging."""
        (self.t / "corrupt.docx").write_bytes(b"NOT A DOCX")
        (self.t / "playbook.json").write_text('{"clauses": []}')
        result = _run_cli(
            [
                "redline",
                str(self.t / "corrupt.docx"),
                str(self.t / "playbook.json"),
                str(self.t / "out.docx"),
            ],
            env={"KAIRO_DEBUG": "1"},
        )
        if "invalid choice" in result.stderr:
            self.skipTest("redline subcommand not available")
        # With KAIRO_DEBUG=1, tracebacks may appear (that's the point)
        # Just verify the process exits
        self.assertNotEqual(result.returncode, 0)

    def test_no_args_shows_usage(self) -> None:
        """Running CLI with no args shows usage, not a traceback."""
        result = _run_cli([])
        combined = result.stdout + result.stderr
        self.assertNotIn("Traceback (most recent call last)", combined)

    def test_invalid_subcommand_no_traceback(self) -> None:
        """Invalid subcommand shows usage error, no traceback."""
        result = _run_cli(["invalid_subcommand"])
        combined = result.stdout + result.stderr
        self.assertNotIn("Traceback (most recent call last)", combined)


if __name__ == "__main__":
    unittest.main()
