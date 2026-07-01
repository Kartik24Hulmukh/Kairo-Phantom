"""
tests/test_phase11_drift_alarm.py — Regression test for Phase 11 Drift Alarm.

Verifies the four-tier judging hierarchy and the calibration drift alarm pipeline.
"""

import os
import sys
import json
import logging
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

# Add sidecar package to path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from sidecar.judging import GauntletJudge
from sidecar.drift_alarm import DriftAlarm

# Setup logging capture
log = logging.getLogger("kairo.drift_alarm")


@pytest.fixture
def manage_training_state():
    """Fixture to back up training_state.json and restore it after test run."""
    sidecar_dir = Path(__file__).parent.parent.resolve()
    state_path = sidecar_dir / "training_state.json"

    backup_exists = state_path.exists()
    backup_content = None
    if backup_exists:
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                backup_content = f.read()
        except Exception:
            pass

    yield state_path

    # Restore the state
    if backup_exists and backup_content is not None:
        try:
            with open(state_path, "w", encoding="utf-8") as f:
                f.write(backup_content)
        except Exception:
            pass
    elif state_path.exists():
        try:
            os.remove(state_path)
        except Exception:
            pass


def test_phase11_drift_alarm_pipeline(manage_training_state, caplog):
    """
    Regression test to verify the four-tier judging hierarchy and drift alarm.
    Injects synthetic-vs-human divergence and asserts training freeze state,
    critical alarm logs, and training_state.json updates.
    """
    # Enable capturing of drift_alarm critical logs
    caplog.set_level(logging.CRITICAL, logger="kairo.drift_alarm")

    state_path = manage_training_state

    # 1. Define synthetic test scenario
    scenario_id = "scenario_drift_regression_01"
    scenario = {"id": scenario_id, "category": "word", "prompt": "Test drift detection prompt"}

    # 2. Inject synthetic-vs-human divergence:
    # - Mock Tier 1 oracle to return True/Success
    # - Mock the AI judges (Tier 3) to return passed=True and score=1.0
    # - Mock Tier 4 Human Anchor to return True (matched) and False (failed verdict)

    judge = GauntletJudge()

    with (
        patch.object(judge, "_run_tier1_oracle", return_value=(True, "Success")),
        patch.object(
            judge,
            "_run_tier3_ai_judge",
            return_value=(1.0, "Mocked AI Judge consensus passed=True"),
        ),
        patch.object(judge, "_run_tier4_human_anchor", return_value=(True, False)),
    ):
        # Run scenario through judge_scenario
        result = judge.judge_scenario(
            scenario=scenario,
            output_file_path="dummy_path.docx",
            response_text="Standard clean response",
        )

        # Assert final scenario outcome is passed=False (due to Tier 4 Human Anchor override)
        assert result["passed"] is False, "Final verdict must be False due to Tier 4 human override"
        assert result["tiers"]["tier1"]["passed"] is True
        assert result["tiers"]["tier3"]["score"] == 1.0
        assert result["tiers"]["tier4"]["matched"] is True
        assert result["tiers"]["tier4"]["verdict"] is False

    # 3. Pass synthetic outcomes (without human override) and the human ground-truth calibration map to DriftAlarm.check_drift
    # Without human override, the synthetic outcome has passed=True.
    synthetic_results = [{"scenario_id": scenario_id, "passed": True}]

    # Human calibration labels map this scenario to False (failed)
    human_calibration_labels = {scenario_id: False}

    # Instantiate DriftAlarm with safety threshold 0.05
    alarm = DriftAlarm(threshold=0.05)

    # Mock duckdb.connect to avoid side effects on actual DuckDB database files
    with patch("duckdb.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        # Check drift
        drift_gap = alarm.check_drift(synthetic_results, human_labels=human_calibration_labels)

        # Verify drift gap is 1.0 (exceeds threshold 0.05)
        # Synthetic pass rate is 1/1 = 1.0, human pass rate is 0/1 = 0.0, so drift gap is 1.0.
        assert drift_gap == 1.0, f"Expected drift gap of 1.0, got {drift_gap}"

        # Verify drift alarm triggers a training freeze and sets training_frozen = True
        assert alarm.training_frozen is True, "DriftAlarm training_frozen must be True"

        # Verify the persistent freeze state is saved successfully in training_state.json
        assert state_path.exists(), "training_state.json should be saved"
        with open(state_path, "r", encoding="utf-8") as f:
            state_data = json.load(f)
        assert (
            state_data.get("training_frozen") is True
        ), "training_state.json must contain training_frozen: True"

        # Verify the alarm triggers a critical log containing "DRIFT ALARM" and "TRAINING FROZEN"
        log_messages = [rec.message for rec in caplog.records]
        alarm_logs = [
            msg for msg in log_messages if "DRIFT ALARM" in msg and "TRAINING FROZEN" in msg
        ]
        assert (
            len(alarm_logs) > 0
        ), f"CRITICAL log containing 'DRIFT ALARM' and 'TRAINING FROZEN' not found: {log_messages}"
