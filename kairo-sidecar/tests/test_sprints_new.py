"""
New test suite verifying the Sprints 5.5, 6, and 7 implementations.
"""

import sys
import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock


# Add project root to path to resolve scripts imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sidecar.sops_manager import SopsManager
from sidecar.sandbox_runner import SandboxRunner
from sidecar.test_fix_loop import TestFixLoop, ProtectedPathViolation, OscillationDetected
from sidecar.outcome_store import OutcomeStore
from sidecar.gym_env import KairoDocEnv
from sidecar.synthetic_users import SyntheticUserSwarm
from sidecar.judging import GauntletJudge
from sidecar.drift_alarm import DriftAlarm
from sidecar.test_generator import TestGenerator
from scripts.ci.sbom_gate import scan_for_secrets, generate_sbom, run_cargo_audit
from scripts.ci.no_skip_gates import scan_python_files
from sidecar import secret_gate


# --- SOPS MANAGER TESTS ---


def test_sops_manager_fallback():
    manager = SopsManager()
    # Non-existent file should fall back to mock secrets
    secrets = manager.decrypt_file("non_existent_secrets.enc.yaml")
    assert "DATABASE_URL" in secrets
    assert "LLM_API_KEY" in secrets
    assert secrets["LLM_API_KEY"].startswith("sk-mock")


def test_sops_manager_manual_yaml_parse():
    manager = SopsManager()
    yaml_content = "KEY1: val1\nKEY2: \"val2\"\n# comment\nKEY3: 'val3'"
    parsed = manager._parse_simple_yaml(yaml_content)
    assert parsed == {"KEY1": "val1", "KEY2": "val2", "KEY3": "val3"}


# --- SBOM GATE TESTS ---


def test_sbom_gate_secrets_scan():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a clean file
        with open(os.path.join(tmpdir, "test_file.py"), "w") as f:
            f.write("# Normal mock file\nDATABASE_URL = 'mock-url'")
        assert scan_for_secrets(tmpdir) is True

        # Create a file with a hardcoded secret keyword (not containing mock/test)
        with open(os.path.join(tmpdir, "bad_file.py"), "w") as f:
            f.write("AWS_SECRET_ACCESS_KEY = 'super-secret-real-key'")
        assert scan_for_secrets(tmpdir) is False


def test_sbom_gate_generation():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create mock Cargo.toml
        with open(os.path.join(tmpdir, "Cargo.toml"), "w") as f:
            f.write("[dependencies]\nserde = '1.0'\ntokio = '1.0'")

        sbom = generate_sbom(tmpdir)
        assert sbom["bomFormat"] == "CycloneDX"
        names = [comp["name"] for comp in sbom["components"]]
        assert "serde" in names
        assert "tokio" in names
        assert "fastapi" in names


def test_sbom_gate_cargo_audit():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Without Cargo.toml, it should return True immediately (graceful degradation)
        assert run_cargo_audit(tmpdir) is True

        # Write a dummy Cargo.toml
        with open(os.path.join(tmpdir, "Cargo.toml"), "w") as f:
            f.write("[package]\nname = 'test'\nversion = '0.1.0'\n")

        # Mock subprocess.run to simulate cargo-audit success
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="{}", stderr="")
            assert run_cargo_audit(tmpdir) is True

            # Simulate cargo-audit failure (vulnerability found)
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout='{"vulnerabilities": {"list": [{"id": "RUSTSEC-1"}]}}',
                stderr="",
            )
            assert run_cargo_audit(tmpdir) is False


def test_secret_gate_scanning():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a clean python file
        clean_file = os.path.join(tmpdir, "clean.py")
        with open(clean_file, "w") as f:
            f.write("# This is a clean file\npassword = 'mock_password'\n")

        # Scanned directory should be clean
        res = secret_gate.scan_directory(tmpdir)
        assert res.clean is True
        assert res.total_files_scanned == 1

        # Create a file containing a real secret pattern (e.g. OpenAI key)
        dirty_file = os.path.join(tmpdir, "dirty.py")
        with open(dirty_file, "w") as f:
            f.write("api_key = 'sk-" + "a" * 32 + "'\n")

        res2 = secret_gate.scan_directory(tmpdir)
        assert res2.clean is False
        assert len(res2.findings) >= 1
        openai_findings = [f for f in res2.findings if f.pattern_name == "OPENAI_API_KEY"]
        assert len(openai_findings) == 1
        assert openai_findings[0].risk_level == "CRITICAL"

        # Test CI entrypoint
        assert secret_gate.run_gate(tmpdir) is False


# --- SANDBOX RUNNER TESTS ---


def test_sandbox_runner_setup_and_execution():
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = SandboxRunner(tmpdir, max_workers=2)

        scenario = {"id": "scen_1", "fixture": None}

        def mock_execute(sandbox_path, scen):
            assert os.path.exists(sandbox_path)
            return {"success": True, "output": "Done"}

        res = runner.run_scenario(scenario, mock_execute)
        assert res["id"] == "scen_1"
        assert res["status"] == "PASS"
        assert res["output"] == "Done"


# --- TEST FIX LOOP TESTS ---


def test_test_fix_loop_protected_path():
    loop = TestFixLoop(workspace_root=".")

    # Check that editing a protected file raises an exception
    with pytest.raises(ProtectedPathViolation):
        loop.verify_patch_safety({"phantom-core/src/response_validator.rs"})

    # Clean files should pass
    loop.verify_patch_safety({"phantom-core/src/main.rs", "kairo-sidecar/sidecar/main.py"})


def test_test_fix_loop_oscillation():
    loop = TestFixLoop(workspace_root=".")

    # First time is fine
    loop.check_convergence("diff content 1")

    # Second time identical diff should raise exception
    with pytest.raises(OscillationDetected):
        loop.check_convergence("diff content 1")


# --- OUTCOME STORE TESTS ---


def test_outcome_store_logging():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        store = OutcomeStore(db_path)

        row_id = store.log_episode(
            scenario_id="test_scen",
            state={"step": 1},
            intent="legal",
            action="modify",
            outcome="PASSED",
            accepted=True,
        )
        assert row_id != -1

        episodes = store.get_episodes("test_scen")
        assert len(episodes) == 1
        assert episodes[0]["scenario_id"] == "test_scen"
        assert episodes[0]["intent"] == "legal"
        assert episodes[0]["accepted"] is True


# --- GYMNASIUM ENV TESTS ---


def test_gym_env_step():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "gym_test.db")
        scenario_data = {
            "id": "gym_scen_1",
            "prompt": "Review this contract",
            "category": "word",
            "fix_budget": 5,
        }

        env = KairoDocEnv(scenario_data, outcome_store_path=db_path)
        state, info = env.reset()
        assert state["text_length"] == len("Review this contract")
        assert info["scenario_id"] == "gym_scen_1"

        # Step with Accept (action 0)
        next_state, reward, terminated, truncated, step_info = env.step(0)
        assert reward == 1.0
        assert terminated is True
        assert step_info["success"] is True


# --- NO SKIP GATES TESTS ---


def test_no_skip_gates():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Clean test python file
        test_file = os.path.join(tmpdir, "test_ok.py")
        with open(test_file, "w") as f:
            f.write("def test_hello():\n    assert True")
        assert scan_python_files(tmpdir) is True

        # Bad test file with skip
        bad_file = os.path.join(tmpdir, "test_bad.py")
        with open(bad_file, "w") as f:
            f.write("@pytest.mark" + ".skip\ndef test_hello():\n    assert True")
        assert scan_python_files(tmpdir) is False


# --- SYNTHETIC USER SWARM TESTS ---


def test_synthetic_user_swarm():
    swarm = SyntheticUserSwarm()

    # Test Impatient Persona
    impatient = swarm.get_persona("impatient")
    prompt = impatient.generate_prompt("Summarize this text")
    assert "DO NOT include any greeting" in prompt

    # Conversational response fails Impatient rubric
    res1 = impatient.evaluate_response("Sure! Here is the summary: hello")
    assert res1["satisfied"] is False

    # Concise response passes Impatient rubric
    res2 = impatient.evaluate_response("concise output")
    assert res2["satisfied"] is True


def test_drive_sandbox_all_personas():
    swarm = SyntheticUserSwarm()
    with tempfile.TemporaryDirectory() as tmpdir:
        for name in [
            "novice",
            "expert",
            "impatient",
            "messy",
            "adversary",
            "privacy",
            "multi_session",
        ]:
            persona = swarm.get_persona(name)
            res = persona.drive_sandbox(tmpdir, "Please review this contract")

            # Check response format
            assert res["success"] is True
            assert isinstance(res["actions_taken"], list)
            assert len(res["actions_taken"]) > 0
            assert "gui_mode" in res
            assert res["persona"] == persona.name

            # Check prompt file exists and is written
            prompt_file = os.path.join(tmpdir, "user_prompt.txt")
            assert os.path.exists(prompt_file)
            content = open(prompt_file, "r", encoding="utf-8").read()
            assert len(content) > 0

            # Check persona-specific expectations
            if name == "privacy":
                assert any("PII" in action for action in res["actions_taken"])
            elif name == "multi_session":
                assert any("previous" in action.lower() for action in res["actions_taken"])
            elif name == "adversary":
                assert any("injection" in action.lower() for action in res["actions_taken"])


# --- JUDGING TESTS ---


def test_gauntlet_judge():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "judge.db")
        judge = GauntletJudge(db_path)

        scenario = {
            "id": "scenario_legal_99",
            "category": "word",
            "prompt": "Verify contract indemnity",
        }

        # Output file doesn't exist, Tier 1 oracle will fail
        result = judge.judge_scenario(scenario, "non_existent_file.docx", "Response text")
        assert result["passed"] is False
        assert result["tiers"]["tier1"]["passed"] is False


# --- DRIFT ALARM TESTS ---


def test_drift_alarm():
    alarm = DriftAlarm(threshold=0.05)

    # Setup results matching calibration human labels exactly (zero drift)
    syn_results = [
        {"scenario_id": "scen_1", "passed": True},
        {"scenario_id": "scen_2", "passed": False},
    ]
    human_labels = {"scen_1": True, "scen_2": False}

    drift = alarm.check_drift(syn_results, human_labels)
    assert drift == 0.0
    assert alarm.is_frozen() is False

    # Setup high drift results
    syn_results_drifted = [
        {"scenario_id": "scen_1", "passed": True},
        {"scenario_id": "scen_2", "passed": True},  # synthetic thinks it passed, human marked fail
    ]

    drift_high = alarm.check_drift(syn_results_drifted, human_labels)
    assert drift_high == 0.5
    assert alarm.is_frozen() is True


# --- TEST GENERATOR TESTS ---


def test_test_generator():
    generator = TestGenerator()
    seed = [{"id": "seed_1", "prompt": "Edit contract", "category": "word"}]

    variants = generator.generate_variants(seed, target_count=5)
    assert len(variants) == 5
    assert variants[0]["id"] == "seed_1"
    assert variants[1]["id"].startswith("seed_1_var_")
    assert variants[1]["is_variant"] is True
