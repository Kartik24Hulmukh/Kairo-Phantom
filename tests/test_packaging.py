"""
W15 Oracle: Packaging — honest installable artifact.

Verifies that:
1. install.sh exists and is valid bash
2. install.sh honestly labels platform support
3. install.sh references real requirements files
4. install.sh runs a smoke test after install
5. The Makefile has the documented commands
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

INSTALL_SH = REPO_ROOT / "install.sh"
MAKEFILE = REPO_ROOT / "Makefile"


class TestInstallScriptExists:
    """Verify install.sh exists and is valid."""

    def test_install_sh_exists(self):
        assert INSTALL_SH.exists(), "install.sh must exist"

    def test_install_sh_is_executable_content(self):
        content = INSTALL_SH.read_text()
        assert content.startswith("#!"), "install.sh must start with a shebang"
        assert "bash" in content[:20], "install.sh must be a bash script"


class TestInstallScriptHonesty:
    """Verify install.sh honestly labels platform support."""

    def test_mentions_linux(self):
        content = INSTALL_SH.read_text()
        assert "Linux" in content, "install.sh must mention Linux"

    def test_mentions_macos(self):
        content = INSTALL_SH.read_text()
        assert "macOS" in content or "Darwin" in content, "install.sh must mention macOS"

    def test_mentions_windows(self):
        content = INSTALL_SH.read_text()
        assert "Windows" in content or "MINGW" in content, "install.sh must mention Windows"

    def test_linux_labeled_ci_verified(self):
        content = INSTALL_SH.read_text()
        assert "CI-verified" in content, "install.sh must label Linux as CI-verified"

    def test_macos_not_claimed_as_full_verified(self):
        content = INSTALL_SH.read_text()
        # macOS must have a warning about not being CI-verified
        macos_section = [l for l in content.splitlines() if "macOS" in l]
        has_warning = any("NOT" in l or "not" in l.lower() or "partial" in l.lower() or "⚠" in l
                         for l in macos_section)
        assert has_warning, (
            "install.sh must warn that macOS is not fully CI-verified"
        )

    def test_windows_not_claimed_as_full_verified(self):
        content = INSTALL_SH.read_text()
        windows_section = [l for l in content.splitlines() if "Windows" in l]
        has_warning = any("NOT" in l or "not" in l.lower() or "partial" in l.lower() or "⚠" in l
                         for l in windows_section)
        assert has_warning, (
            "install.sh must warn that Windows is not fully CI-verified"
        )


class TestInstallScriptReferences:
    """Verify install.sh references real files."""

    def test_references_requirements(self):
        content = INSTALL_SH.read_text()
        assert "requirements.txt" in content, "install.sh must reference requirements files"
        assert (REPO_ROOT / "kairo-sidecar" / "requirements.txt").exists()

    def test_references_test_requirements(self):
        content = INSTALL_SH.read_text()
        assert "requirements-test.txt" in content, "install.sh must reference test requirements"
        assert (REPO_ROOT / "requirements-test.txt").exists()

    def test_has_smoke_test(self):
        content = INSTALL_SH.read_text()
        assert "import kernel" in content, "install.sh must have a smoke test importing kernel"
        assert "import packs" in content, "install.sh must have a smoke test importing packs"
        assert "import bench" in content, "install.sh must have a smoke test importing bench"

    def test_has_corpus_integrity_test(self):
        content = INSTALL_SH.read_text()
        assert "test_corpus_integrity" in content, (
            "install.sh must run corpus integrity test as a smoke check"
        )


class TestMakefileCommands:
    """Verify the Makefile has the documented commands."""

    def test_makefile_exists(self):
        assert MAKEFILE.exists(), "Makefile must exist"

    def test_has_build_target(self):
        content = MAKEFILE.read_text()
        assert "build:" in content, "Makefile must have a build target"

    def test_has_test_target(self):
        content = MAKEFILE.read_text()
        assert "test:" in content, "Makefile must have a test target"

    def test_has_demo_target(self):
        content = MAKEFILE.read_text()
        assert "demo:" in content, "Makefile must have a demo target"

    def test_has_bench_target(self):
        content = MAKEFILE.read_text()
        assert "bench:" in content, "Makefile must have a bench target"

    def test_has_run_target(self):
        content = MAKEFILE.read_text()
        assert "run:" in content, "Makefile must have a run target"
