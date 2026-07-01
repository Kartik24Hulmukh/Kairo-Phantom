"""
tests/test_gauntlet_scaffold.py — Unit tests for the gauntlet scaffold configuration.
"""

import sys
import os
from unittest.mock import patch

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))


def test_gauntlet_scenarios_count():
    from run_sequential_gauntlet import DOCUMENT_QUEUE, PENDING_SCENARIOS

    total_scenarios = sum(len(doc_cfg["scenarios"]) for doc_cfg in DOCUMENT_QUEUE)
    assert total_scenarios >= 200, f"Expected 200+ scenarios, found {total_scenarios}"

    # Assert PENDING_SCENARIOS is a set
    assert isinstance(PENDING_SCENARIOS, set)
    assert len(PENDING_SCENARIOS) > 0


def test_run_doc_block_skips_pending():
    from run_sequential_gauntlet import run_doc_block

    doc_cfg = {
        "agent_id": "test_agent",
        "label": "Test Agent",
        "scenarios": ["TEST1", "TEST2"],
        "module": "test_module",
        "fn": "test_fn",
    }

    # Mock PENDING_SCENARIOS to include TEST1 but not TEST2
    with (
        patch("run_sequential_gauntlet.PENDING_SCENARIOS", {"TEST1"}),
        patch("run_sequential_gauntlet.run_one_scenario") as mock_run,
    ):
        mock_run.return_value = (True, "mock pass", False)

        result = run_doc_block(doc_cfg)

        assert result["total"] == 2
        assert result["passed"] == 2
        assert result["failed"] == 0

        # run_one_scenario should only be called for TEST2 (since TEST1 is skipped as pending)
        mock_run.assert_called_once_with(doc_cfg, "TEST2")

        passed_scenarios = result["passed_scenarios"]
        assert passed_scenarios[0]["id"] == "TEST1"
        assert (
            "Pending" in passed_scenarios[0]["message"]
            or "Skipped" in passed_scenarios[0]["message"]
        )
        assert passed_scenarios[1]["id"] == "TEST2"
