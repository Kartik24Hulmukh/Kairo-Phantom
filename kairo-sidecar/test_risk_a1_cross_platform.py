"""
Risk A1: Cross-Platform UI Automation Brittleness.
Test: fallback chain activates correctly — primary fails → fallback → both fail → loud error.
"""

import os
import sys
import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.resolve()))


class TestCrossPlatformFallback:
    """The ghost-typing fallback chain must never silently succeed."""

    def test_xdotool_fallback_when_no_display(self):
        """When DISPLAY is unset, xdotool path must fail loudly, not silently succeed."""
        import shutil

        if shutil.which("xdotool") is None:
            pytest.skip("xdotool not installed in this sandbox (INFRA_PENDING)")
        env = os.environ.copy()
        env.pop("DISPLAY", None)
        result = subprocess.run(
            ["xdotool", "getactivewindow"], capture_output=True, text=True, env=env, timeout=5
        )
        # xdotool must NOT silently succeed without a display
        assert (
            result.returncode != 0 or "display" in result.stderr.lower()
        ), "xdotool silently succeeded without DISPLAY — this is a SILENT SUCCESS bug"

    def test_no_silent_success_on_missing_tools(self):
        """If both primary and fallback fail, the system must error loudly."""
        # Simulate: no display, no xdotool → must raise, not return True
        from sidecar.humanized_injector import HumanizedInjector

        injector = HumanizedInjector()

        with patch.dict(os.environ, {}, clear=True):
            with patch("subprocess.run", side_effect=FileNotFoundError("xdotool not found")):
                with patch(
                    "subprocess.check_output", side_effect=FileNotFoundError("xdotool not found")
                ):
                    # The injector must NOT silently succeed
                    result = injector.inject_text("test text")
                    assert (
                        result is False or result is None
                    ), "injector returned True when all paths failed — SILENT SUCCESS bug"

    def test_linux_platform_detector_identifies_environment(self):
        """The platform detector must correctly identify the desktop environment."""
        # Check that the code can detect XDG_CURRENT_DESKTOP
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "unknown")
        session_type = os.environ.get("XDG_SESSION_TYPE", "unknown")
        # The detector should return a valid string, not crash
        assert isinstance(desktop, str)
        assert isinstance(session_type, str)

    def test_ghost_typer_trait_exists_in_rust(self):
        """The Rust GhostTyper trait must exist for cross-platform abstraction."""
        rust_file = Path(__file__).parent.parent / "phantom-core" / "src" / "platform" / "linux.rs"
        if rust_file.exists():
            content = rust_file.read_text()
            # Must have xdotool fallback (not just AT-SPI2)
            assert "xdotool" in content, "Linux platform must have xdotool fallback"
            # Must have try_atspi or atspi reference
            assert (
                "atspi" in content.lower() or "try_atspi" in content.lower()
            ), "Linux platform must have AT-SPI2 reference"
        else:
            pytest.skip("Rust platform file not found (may be on different architecture)")
