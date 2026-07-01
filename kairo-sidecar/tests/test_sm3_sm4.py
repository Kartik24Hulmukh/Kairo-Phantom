import os
import json
import shutil
import pytest
from unittest.mock import patch, mock_open
import duckdb

from sidecar.judging import GauntletJudge, JudgeOutputSchema
from sidecar.drift_alarm import DriftAlarm


# Test Tier 2 metamorphic perturbations
def test_tier2_metamorphic_perturbations():
    judge = GauntletJudge()

    # Normal clean response should pass Tier 2
    assert judge._run_tier2_metamorphic("This is a valid contract review") is True

    # Response containing forbidden markers should fail
    assert judge._run_tier2_metamorphic("Review error: [blocked]") is False
    assert judge._run_tier2_metamorphic("REVIEW ERROR: [BLOCKED]") is False

    # Perturbations in whitespace/casing
    assert judge._run_tier2_metamorphic("This contains [  BLOCKED   ] with extra spaces") is True
    assert judge._run_tier2_metamorphic("This has [blocked]") is False
    assert judge._run_tier2_metamorphic("Execution Failed") is False
    assert judge._run_tier2_metamorphic("execution   failed") is False


# Test Tier 3 AI Judge with 2-Model Tiebreak and Fallback
@patch("sidecar.llm_caller.call_with_schema")
def test_tier3_ai_judge_consensus_and_tiebreak(mock_call):
    judge = GauntletJudge()
    scenario = {"id": "test_s1", "prompt": "Check indemnity clause", "category": "word"}

    # Case 1: Both models agree on passed=True
    mock_call.side_effect = [
        JudgeOutputSchema(passed=True, score=0.9, feedback="Excellent"),
        JudgeOutputSchema(passed=True, score=0.8, feedback="Good structure"),
    ]
    avg_score, feedback = judge._run_tier3_ai_judge(scenario, "Response text")
    assert avg_score == pytest.approx(0.85)
    assert "Consensus" in feedback

    # Case 2: Disagree on passed, but average score >= 0.7
    mock_call.side_effect = [
        JudgeOutputSchema(passed=True, score=0.8, feedback="Model A says OK"),
        JudgeOutputSchema(passed=False, score=0.6, feedback="Model B says missing details"),
    ]
    avg_score, feedback = judge._run_tier3_ai_judge(scenario, "Response text")
    assert avg_score == pytest.approx(0.7)
    assert "Tiebreaker" in feedback

    # Case 3: Disagree on passed, and average score < 0.7
    mock_call.side_effect = [
        JudgeOutputSchema(passed=True, score=0.6, feedback="Model A says OK"),
        JudgeOutputSchema(passed=False, score=0.4, feedback="Model B says bad"),
    ]
    avg_score, feedback = judge._run_tier3_ai_judge(scenario, "Response text")
    assert avg_score == pytest.approx(0.5)
    assert "Tiebreaker" in feedback

    # Case 4: Exception / LiteLLM not available - fallback
    mock_call.side_effect = Exception("Connection Refused")
    avg_score, feedback = judge._run_tier3_ai_judge(
        scenario, "Indemnity clause is checked and verified."
    )
    assert avg_score > 0.0
    assert "Fallback" in feedback


# Test Tier 4 Human Ground-Truth Anchor Loading dynamically
def test_tier4_human_anchor():
    judge = GauntletJudge()

    mock_data = '{"s001": true, "s003": false}'
    with patch("builtins.open", mock_open(read_data=mock_data)):
        # Verify lookup of scenarios from calibration_set.json
        matched, verdict = judge._run_tier4_human_anchor("s001", "Response")
        assert matched is True
        assert verdict is True

        matched, verdict = judge._run_tier4_human_anchor("s003", "Response")
        assert matched is True
        assert verdict is False

        matched, verdict = judge._run_tier4_human_anchor("non_existent_id", "Response")
        assert matched is False


# Test Drift Alarm persistent freeze state (training_state.json)
def test_drift_alarm_persistent_freeze_state():
    # Setup temporary sidecar dir for isolation
    sidecar_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    state_path = os.path.join(sidecar_dir, "training_state.json")

    # Backup existing training_state.json if any
    backup_path = state_path + ".backup"
    if os.path.exists(state_path):
        shutil.move(state_path, backup_path)

    try:
        alarm = DriftAlarm(threshold=0.05)
        assert alarm.is_frozen() is False

        # Manually trigger freeze
        alarm.trigger_freeze(0.1)
        assert alarm.is_frozen() is True

        # Check that state file was written
        assert os.path.exists(state_path)
        with open(state_path, "r") as f:
            state_data = json.load(f)
            assert state_data["training_frozen"] is True

        # Re-initialize new DriftAlarm and verify it loads the frozen state
        alarm2 = DriftAlarm(threshold=0.05)
        assert alarm2.is_frozen() is True

        # Reset freeze
        alarm2.training_frozen = False
        alarm2._save_freeze_state(False)

        alarm3 = DriftAlarm(threshold=0.05)
        assert alarm3.is_frozen() is False
    finally:
        # Restore backup
        if os.path.exists(state_path):
            os.remove(state_path)
        if os.path.exists(backup_path):
            shutil.move(backup_path, state_path)


# Test Drift Alarm DuckDB persistence
def test_drift_alarm_duckdb_persistence():
    alarm = DriftAlarm(threshold=0.05)

    # Test check_drift with overlap resulting in drift gap > threshold
    syn_results = [
        {"scenario_id": "s001", "passed": False},  # calibration says True
        {"scenario_id": "s002", "passed": False},  # calibration says True
    ]

    # Mock database target path to target/gauntlet_outcomes.duckdb
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    test_db_path = os.path.join(repo_root, "target", "gauntlet_outcomes.duckdb")

    # Run check_drift
    mock_data = '{"s001": true, "s002": true}'
    with patch("builtins.open", mock_open(read_data=mock_data)):
        drift = alarm.check_drift(syn_results)

    # Human label for s001 and s002 in calibration_set.json is True/True, so human_pass_rate = 1.0
    # Synthetic results pass rate = 0.0
    # Drift gap = 1.0 (exceeds 0.05)
    assert drift == 1.0
    assert alarm.is_frozen() is True

    # Verify DuckDB database table and entry
    assert os.path.exists(test_db_path)
    con = duckdb.connect(test_db_path)
    try:
        res = con.execute("SELECT * FROM drift_metrics ORDER BY timestamp DESC LIMIT 1").fetchone()
        assert res is not None
        # Columns: id, synthetic_pass_rate, human_pass_rate, drift_gap, threshold, frozen, timestamp
        assert res[1] == 0.0  # synthetic_pass_rate
        assert res[2] == 1.0  # human_pass_rate
        assert res[3] == 1.0  # drift_gap
        assert res[4] == 0.05  # threshold
        assert res[5] is True  # frozen
    finally:
        con.close()
