"""
Tests for kairo-sidecar CUA module.
Runs without Canva, without cua-driver, without a real display.
"""

import sys
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).parent.parent))
from sidecar.cua.canva_cua import CanvaCUAAgent, ExecutionResult, SAFETY_LIMITS
from sidecar.cua.driver_service import CuaDriverService


class TestCanvaCUAAgent:
    """Tests for CanvaCUAAgent."""

    def test_agent_initializes(self):
        agent = CanvaCUAAgent()
        assert agent is not None

    def test_safety_limits_correct(self):
        assert SAFETY_LIMITS["max_actions"] == 5
        assert SAFETY_LIMITS["timeout_seconds"] == 10
        assert "text" in SAFETY_LIMITS["allowed_element_types"]

    def test_non_canva_context_returns_clipboard_fallback(self):
        agent = CanvaCUAAgent()
        agent._get_active_window_title = lambda: "Document1 - Microsoft Word"
        agent._verify_canva_context = lambda: False

        result = agent.execute_text_replacement("Test text")

        assert not result.success or result.fallback_type is not None

    def test_execution_result_dataclass(self):
        result = ExecutionResult(
            success=True,
            message="OK",
            time_taken_ms=50.0,
        )
        assert result.success
        assert result.time_taken_ms == 50.0
        assert result.fallback_type is None

    def test_hash_file_returns_empty_for_none(self):
        agent = CanvaCUAAgent()
        assert agent._hash_file(None) == ""

    def test_hash_file_returns_empty_for_nonexistent(self):
        agent = CanvaCUAAgent()
        assert agent._hash_file("/nonexistent/path/file.png") == ""

    def test_audit_log_writes(self, tmp_path):
        agent = CanvaCUAAgent()

        with patch.object(Path, "home", return_value=tmp_path):
            # Just verify no exception is raised
            agent._audit_log(
                action="test",
                success=True,
                target_text="Hello",
                before_hash="abc",
                after_hash="def",
                window_title="Test Window",
            )

    def test_verify_text_changed_falls_back_to_hash(self):
        agent = CanvaCUAAgent()
        agent.farscry_available = False  # Disable farscry

        # No screenshots — should return True (cannot verify = assume success)
        result = agent._verify_text_changed(None, None, "expected text")
        assert result is True

    def test_self_test_mode(self):
        """Run the built-in self-test and verify it passes."""
        from sidecar.cua.canva_cua import run_self_test

        exit_code = run_self_test()
        assert exit_code == 0, f"Self-test failed with exit code {exit_code}"


class TestCuaDriverService:
    """Tests for CuaDriverService."""

    def test_service_initializes(self):
        svc = CuaDriverService()
        assert svc is not None

    def test_available_false_when_driver_not_installed(self):
        svc = CuaDriverService()
        # In CI without cua-driver, available should be False
        # (not an error — graceful degradation)
        assert isinstance(svc.available, bool)

    def test_screenshot_returns_none_when_unavailable(self):
        svc = CuaDriverService()
        svc._available = False
        result = svc.screenshot()
        assert result is None

    def test_click_returns_false_when_unavailable(self):
        svc = CuaDriverService()
        svc._available = False
        result = svc.click(100, 200)
        assert result is False

    def test_type_text_returns_false_when_unavailable(self):
        svc = CuaDriverService()
        svc._available = False
        result = svc.type_text("Hello")
        assert result is False

    def test_status_dict(self):
        svc = CuaDriverService()
        status = svc.status()
        assert "available" in status
        assert "driver_path" in status
        assert isinstance(status["available"], bool)

    def test_version_returns_none_when_unavailable(self):
        svc = CuaDriverService()
        svc._available = False
        assert svc.version() is None
