"""
test_phase10_loop.py — Proof integration test for Phase 10.

Demonstrates the full temporal Test-Fix-Test loop (Item 35) wired to the
DuckDB Verified Outcome Store (Item 37).

Test strategy
-------------
The test seeds a *deterministically failing* scenario — a Python file with
a deliberate TypeError — runs TestFixLoop against it, and verifies:

1.  Terminal state is exactly PASS or QUARANTINE (never None, never silent).
2.  DuckDB audit trail has ≥ 1 AttemptRecord with all required fields.
3.  Quarantine ticket JSON exists in target/quarantine_tickets/ if QUARANTINE.
4.  argilla_queue.jsonl was appended if terminal is QUARANTINE or ESCALATE.
5.  A formatted audit table is printed to stdout.
6.  KairoDocEnv.run_fix_loop_episode() also returns a valid LoopResult.

Run:
    python -m pytest tests/test_phase10_loop.py -v -s
"""

from __future__ import annotations

import json
import os
import sys
import textwrap
import time
from pathlib import Path
from typing import Any, Dict, Set, Tuple

import pytest

# ── import helpers ────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sidecar.test_fix_loop import (
    AttemptRecord,
    LoopResult,
    TestFixLoop,
    REWARD_ESCALATE,
    REWARD_PASS,
    REWARD_QUARANTINE,
)
from sidecar.outcome_store import OutcomeStore
from sidecar.gym_env import KairoDocEnv


# ── Seeded failing scenario fixture ──────────────────────────────────────────

SCENARIO_ID = "phase10-proof-001"
SEEDED_BUG = textwrap.dedent("""\
    # seeded_target.py — deliberately broken
    def compute(x):
        return x + "not_a_number"   # TypeError: unsupported operand
""")

SEEDED_FIX = textwrap.dedent("""\
    # seeded_target.py — fixed
    def compute(x):
        return x + 0   # correct: add zero
""")


@pytest.fixture()
def tmp_workspace(tmp_path: Path):
    """Set up a fresh isolated workspace for the test run."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "target").mkdir()
    (workspace / "target" / "quarantine_tickets").mkdir()
    return workspace


@pytest.fixture()
def tmp_db(tmp_path: Path) -> str:
    """Return a fresh DuckDB path isolated from the real outcome store."""
    return str(tmp_path / "test_outcomes.duckdb")


# ── Helper callbacks ─────────────────────────────────────────────────────────


def _make_callbacks(
    workspace: Path,
    attempt_cap: int = 3,
) -> Tuple[Any, Any, Any, Any]:
    """
    Return (run_tests_fn, generate_fix_fn, apply_patch_fn, rollback_fn) for
    a deterministic scenario that:
      - Fails on attempt 1 (simulates a failed test)
      - Passes on attempt 2 (fix applied)
    This guarantees a PASS outcome within the budget.
    """
    state = {"attempt_count": 0, "fixed": False}
    target_file = workspace / "seeded_target.py"
    target_file.write_text(SEEDED_BUG, encoding="utf-8")

    def run_tests_fn() -> bool:
        """Return True only after the fix has been applied."""
        return state["fixed"]

    def generate_fix_fn(fail_result: Dict[str, Any]) -> Tuple[str, Set[str]]:
        state["attempt_count"] += 1
        diff = f"--- a/seeded_target.py\n+++ b/seeded_target.py\n@@ fix attempt {state['attempt_count']} @@\n"
        modified = {str(target_file)}
        return diff, modified

    def apply_patch_fn(patch_diff: str) -> None:
        """Simulate applying the fix on the second attempt."""
        if state["attempt_count"] >= 2:
            target_file.write_text(SEEDED_FIX, encoding="utf-8")
            state["fixed"] = True

    def rollback_fn() -> None:
        target_file.write_text(SEEDED_BUG, encoding="utf-8")
        state["fixed"] = False

    return run_tests_fn, generate_fix_fn, apply_patch_fn, rollback_fn


def _make_always_fail_callbacks(workspace: Path) -> Tuple[Any, Any, Any, Any]:
    """
    Callbacks where tests ALWAYS fail → QUARANTINE on budget exhaustion.
    Uses a unique diff each time to avoid oscillation detection.
    """
    state = {"attempt_count": 0}
    target_file = workspace / "seeded_target.py"
    target_file.write_text(SEEDED_BUG, encoding="utf-8")

    def run_tests_fn() -> bool:
        return False

    def generate_fix_fn(fail_result: Dict[str, Any]) -> Tuple[str, Set[str]]:
        state["attempt_count"] += 1
        # Unique diff each time (avoids oscillation QUARANTINE, exercises budget path)
        diff = (
            f"--- a/seeded_target.py\n+++ b/seeded_target.py\n"
            f"@@ attempt-{state['attempt_count']}-ts-{time.time()} @@\n"
            f"-    return x + 'not_a_number'\n"
            f"+    return x + {state['attempt_count']}\n"
        )
        return diff, {str(target_file)}

    def apply_patch_fn(patch_diff: str) -> None:
        pass  # no-op

    def rollback_fn() -> None:
        pass

    return run_tests_fn, generate_fix_fn, apply_patch_fn, rollback_fn


# ── Audit table printer ───────────────────────────────────────────────────────


def _print_audit_table(result: LoopResult) -> None:
    """Print a formatted ASCII table of the loop's attempt audit trail."""
    print("\n" + "=" * 75)
    print(f"  PHASE 10 AUDIT — scenario={result.scenario_id}")
    print(
        f"  terminal_state={result.terminal_state}  reward={result.reward:+.1f}  "
        f"elapsed={result.elapsed_s:.3f}s  attempts={result.attempts_used}"
    )
    if result.failure_reason:
        print(f"  failure_reason={result.failure_reason}")
    if result.ticket_path:
        print(f"  ticket={result.ticket_path}")
    print("-" * 75)
    header = f"{'Attempt':>7}  {'Action':<18}  {'Test':>5}  {'Guardrails':<35}  {'ms':>7}"
    print(header)
    print("-" * 75)
    for rec in result.audit_trail:
        guards = ", ".join(rec.guardrails_checked)
        print(
            f"{rec.attempt:>7}  {rec.action_taken:<18}  {rec.test_result:>5}  "
            f"{guards:<35}  {rec.elapsed_ms:>7.1f}"
        )
    print("=" * 75 + "\n")


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestPhase10Loop:
    """Full proof tests for Item 35 (temporal loop) and Item 37 (outcome store)."""

    def test_pass_convergence(self, tmp_workspace: Path, tmp_db: str):
        """
        Proof A — Loop converges to PASS on a seeded scenario that fixes itself
        on the second attempt.  Verifies all acceptance criteria.
        """
        loop = TestFixLoop(
            workspace_root=str(tmp_workspace),
            budget_attempts=5,
            budget_seconds=60.0,
        )
        run_tests_fn, generate_fix_fn, apply_patch_fn, rollback_fn = _make_callbacks(tmp_workspace)

        result = loop.run_loop(
            scenario_id=SCENARIO_ID,
            initial_fail_result={"status": "FAIL", "reason": "TypeError in compute()"},
            run_tests_fn=run_tests_fn,
            generate_fix_fn=generate_fix_fn,
            apply_patch_fn=apply_patch_fn,
            rollback_fn=rollback_fn,
            log_to_store=False,  # we log manually below to our test DB
        )

        _print_audit_table(result)

        # ── Core assertions ────────────────────────────────────────────────
        assert result.terminal_state in (
            "PASS",
            "QUARANTINE",
            "ESCALATE",
        ), f"terminal_state must be one of the 3 states, got: {result.terminal_state!r}"
        assert (
            result.terminal_state == "PASS"
        ), f"Expected PASS for auto-fixing scenario, got {result.terminal_state}"
        assert result.reward == REWARD_PASS
        assert result.attempts_used >= 1
        assert result.elapsed_s >= 0  # non-negative; may be 0.0 on fast machines

        # ── Audit trail ────────────────────────────────────────────────────
        assert len(result.audit_trail) >= 1, "Must have ≥ 1 AttemptRecord"
        for rec in result.audit_trail:
            assert isinstance(rec, AttemptRecord)
            assert rec.attempt >= 1
            assert rec.timestamp > 0
            assert isinstance(rec.guardrails_checked, list)
            assert len(rec.guardrails_checked) >= 1
            assert rec.test_result in ("PASS", "FAIL", "ERROR")
            assert rec.action_taken in ("APPLY_PATCH", "ROLLBACK", "ESCALATE", "QUARANTINE")

        # ── DuckDB persistence ─────────────────────────────────────────────
        store = OutcomeStore(tmp_db)
        store.log_loop_result(result)

        audit_rows = store.get_loop_audit(SCENARIO_ID)
        assert len(audit_rows) >= 1, "DuckDB must have ≥ 1 loop_result row"
        row = audit_rows[0]
        assert row["terminal_state"] == "PASS"
        assert row["reward"] == REWARD_PASS
        assert isinstance(row["attempts"], list)
        assert len(row["attempts"]) >= 1
        attempt_keys = {
            "attempt",
            "timestamp",
            "patch_hash",
            "guardrails_checked",
            "test_result",
            "action_taken",
            "elapsed_ms",
        }
        for a in row["attempts"]:
            missing = attempt_keys - set(a.keys())
            assert not missing, f"AttemptRecord missing keys: {missing}"

    def test_quarantine_on_budget_exhaustion(self, tmp_workspace: Path, tmp_db: str):
        """
        Proof B — Loop hits QUARANTINE when budget is exhausted.
        Verifies auto-ticket JSON and Argilla queue append.
        """
        loop = TestFixLoop(
            workspace_root=str(tmp_workspace),
            budget_attempts=3,
            budget_seconds=120.0,
        )
        run_tests_fn, generate_fix_fn, apply_patch_fn, rollback_fn = _make_always_fail_callbacks(
            tmp_workspace
        )

        result = loop.run_loop(
            scenario_id="phase10-quarantine-001",
            initial_fail_result={"status": "FAIL", "reason": "Persistent failure"},
            run_tests_fn=run_tests_fn,
            generate_fix_fn=generate_fix_fn,
            apply_patch_fn=apply_patch_fn,
            rollback_fn=rollback_fn,
            log_to_store=False,
        )

        _print_audit_table(result)

        # Terminal state must be QUARANTINE
        assert (
            result.terminal_state == "QUARANTINE"
        ), f"Expected QUARANTINE on budget exhaustion, got {result.terminal_state}"
        assert result.reward == REWARD_QUARANTINE
        assert result.attempts_used == 3

        # ── Quarantine ticket ──────────────────────────────────────────────
        tmp_workspace / "target" / "quarantine_tickets"
        # The ticket path from the loop should exist (loop uses workspace_root)
        # Re-write ticket to our tmp dir for assertion since loop writes to workspace_root
        assert result.ticket_path is not None, "QUARANTINE must emit a ticket_path"
        assert os.path.exists(
            result.ticket_path
        ), f"Quarantine ticket file does not exist: {result.ticket_path}"
        with open(result.ticket_path, encoding="utf-8") as fh:
            ticket = json.load(fh)
        assert ticket["scenario_id"] == "phase10-quarantine-001"
        assert ticket["terminal_state"] == "QUARANTINE"
        assert isinstance(ticket["attempts"], list)

        # ── Argilla queue ──────────────────────────────────────────────────
        argilla_queue = os.path.join(str(tmp_workspace), "target", "argilla_queue.jsonl")
        assert os.path.exists(argilla_queue), "argilla_queue.jsonl must exist after QUARANTINE"
        with open(argilla_queue, encoding="utf-8") as fh:
            lines = [l.strip() for l in fh if l.strip()]
        assert len(lines) >= 1, "Argilla queue must have ≥ 1 record"
        record = json.loads(lines[-1])
        assert record["terminal_state"] == "QUARANTINE"
        assert record["label"] is None  # pending human review

        # ── DuckDB audit ───────────────────────────────────────────────────
        store = OutcomeStore(tmp_db)
        store.log_loop_result(result)
        audit_rows = store.get_loop_audit("phase10-quarantine-001")
        assert len(audit_rows) >= 1
        assert audit_rows[0]["terminal_state"] == "QUARANTINE"

    def test_escalate_on_protected_path(self, tmp_workspace: Path, tmp_db: str):
        """
        Proof C — Loop immediately ESCALATEs when fixer tries to touch a protected file.
        """
        loop = TestFixLoop(
            workspace_root=str(tmp_workspace),
            budget_attempts=5,
            budget_seconds=60.0,
        )

        protected_file = "kairo-sidecar/sidecar/oracles.py"

        def generate_fix_fn(fail):
            diff = "--- a/oracles.py\n+++ b/oracles.py\n@@ evil patch @@\n"
            return diff, {protected_file}

        result = loop.run_loop(
            scenario_id="phase10-escalate-001",
            initial_fail_result={"status": "FAIL"},
            run_tests_fn=lambda: False,
            generate_fix_fn=generate_fix_fn,
            apply_patch_fn=lambda d: None,
            rollback_fn=lambda: None,
            log_to_store=False,
        )

        _print_audit_table(result)

        assert result.terminal_state == "ESCALATE"
        assert result.reward == REWARD_ESCALATE
        assert result.attempts_used == 1  # halts immediately

    def test_quarantine_on_oscillation(self, tmp_workspace: Path, tmp_db: str):
        """
        Proof D — Duplicate diff hash triggers immediate QUARANTINE.
        """
        loop = TestFixLoop(
            workspace_root=str(tmp_workspace),
            budget_attempts=5,
            budget_seconds=60.0,
        )
        IDENTICAL_DIFF = "--- a/foo.py\n+++ b/foo.py\n@@ same every time @@\n"

        call_count = {"n": 0}

        def generate_fix_fn(fail):
            call_count["n"] += 1
            return IDENTICAL_DIFF, set()  # same hash on attempt 2 → oscillation

        result = loop.run_loop(
            scenario_id="phase10-oscillation-001",
            initial_fail_result={"status": "FAIL"},
            run_tests_fn=lambda: False,
            generate_fix_fn=generate_fix_fn,
            apply_patch_fn=lambda d: None,
            rollback_fn=lambda: None,
            log_to_store=False,
        )

        _print_audit_table(result)

        assert result.terminal_state == "QUARANTINE"
        assert result.reward == REWARD_QUARANTINE

    def test_time_budget(self, tmp_workspace: Path, tmp_db: str):
        """
        Proof E — Wall-clock time budget terminates the loop before attempts run out.
        """
        loop = TestFixLoop(
            workspace_root=str(tmp_workspace),
            budget_attempts=100,  # very large attempt budget
            budget_seconds=0.01,  # 10 ms — expires immediately
        )

        call_count = {"n": 0}

        def generate_fix_fn(fail):
            call_count["n"] += 1
            time.sleep(0.05)  # each attempt takes 50ms > 10ms budget
            return f"diff-{call_count['n']}", set()

        result = loop.run_loop(
            scenario_id="phase10-timebudget-001",
            initial_fail_result={"status": "FAIL"},
            run_tests_fn=lambda: False,
            generate_fix_fn=generate_fix_fn,
            apply_patch_fn=lambda d: None,
            rollback_fn=lambda: None,
            log_to_store=False,
        )

        _print_audit_table(result)

        assert result.terminal_state == "QUARANTINE"
        assert result.elapsed_s < 5.0  # should finish fast, not run 100 attempts

    def test_duckdb_episode_api_backward_compat(self, tmp_db: str):
        """
        Verify the backward-compatible episode API still works after DuckDB migration.
        """
        store = OutcomeStore(tmp_db)
        ep_id = store.log_episode(
            scenario_id="compat-test-001",
            state={"text_length": 100, "turns_count": 0},
            intent="word",
            action="0",
            outcome="ACCEPTED",
            accepted=True,
        )
        assert ep_id > 0 or ep_id == -1  # -1 only on hard DB error

        episodes = store.get_episodes("compat-test-001")
        assert len(episodes) >= 1
        ep = episodes[0]
        assert ep["scenario_id"] == "compat-test-001"
        assert ep["accepted"] is True
        assert isinstance(ep["state"], dict)

        all_eps = store.get_all_episodes()
        assert any(e["scenario_id"] == "compat-test-001" for e in all_eps)

    def test_gym_env_run_fix_loop_episode(self, tmp_workspace: Path, tmp_db: str):
        """
        Verify KairoDocEnv.run_fix_loop_episode() returns a valid LoopResult.
        """
        scenario = {
            "id": "phase10-gym-001",
            "prompt": "Write a report",
            "category": "word",
            "fix_budget": 5,
        }
        env = KairoDocEnv(scenario, outcome_store_path=tmp_db)
        obs, info = env.reset()
        assert isinstance(obs, dict)
        assert info["scenario_id"] == "phase10-gym-001"

        loop = TestFixLoop(
            workspace_root=str(tmp_workspace),
            budget_attempts=3,
            budget_seconds=30.0,
        )
        run_tests_fn, generate_fix_fn, apply_patch_fn, rollback_fn = _make_callbacks(
            tmp_workspace, attempt_cap=3
        )

        result = env.run_fix_loop_episode(
            fix_loop=loop,
            initial_fail_result={"status": "FAIL"},
            run_tests_fn=run_tests_fn,
            generate_fix_fn=generate_fix_fn,
            apply_patch_fn=apply_patch_fn,
            rollback_fn=rollback_fn,
        )

        assert isinstance(result, LoopResult)
        assert result.terminal_state in ("PASS", "QUARANTINE", "ESCALATE")
        assert result.reward in (REWARD_PASS, REWARD_QUARANTINE, REWARD_ESCALATE)


class TestPhase10OutcomeStore:
    """Unit tests for the DuckDB OutcomeStore (Item 37 — Verified Outcome Store)."""

    def test_log_and_retrieve_loop_result(self, tmp_db: str):
        """log_loop_result + get_loop_audit round-trip."""
        from sidecar.test_fix_loop import AttemptRecord, LoopResult

        trail = [
            AttemptRecord(
                attempt=1,
                timestamp=time.time(),
                patch_hash="abc123",
                guardrails_checked=["oracle_immutability", "protected_paths"],
                test_result="FAIL",
                action_taken="ROLLBACK",
                elapsed_ms=120.5,
            ),
            AttemptRecord(
                attempt=2,
                timestamp=time.time(),
                patch_hash="def456",
                guardrails_checked=[
                    "oracle_immutability",
                    "protected_paths",
                    "convergence",
                    "regression_gate",
                ],
                test_result="PASS",
                action_taken="APPLY_PATCH",
                elapsed_ms=98.0,
            ),
        ]
        lr = LoopResult(
            scenario_id="store-test-001",
            terminal_state="PASS",
            reward=1.0,
            attempts_used=2,
            elapsed_s=0.5,
            audit_trail=trail,
        )
        store = OutcomeStore(tmp_db)
        store.log_loop_result(lr)

        rows = store.get_loop_audit("store-test-001")
        assert len(rows) == 1
        row = rows[0]
        assert row["terminal_state"] == "PASS"
        assert row["reward"] == 1.0
        assert len(row["attempts"]) == 2
        assert row["attempts"][1]["action_taken"] == "APPLY_PATCH"
        assert "regression_gate" in row["attempts"][1]["guardrails_checked"]

    def test_get_all_loop_results(self, tmp_db: str):
        """get_all_loop_results returns rows from multiple scenarios."""
        from sidecar.test_fix_loop import LoopResult

        store = OutcomeStore(tmp_db)
        for i in range(3):
            lr = LoopResult(
                scenario_id=f"multi-{i}",
                terminal_state="QUARANTINE",
                reward=-1.0,
                attempts_used=5,
                elapsed_s=float(i + 1),
                audit_trail=[],
            )
            store.log_loop_result(lr)

        all_rows = store.get_all_loop_results()
        assert len(all_rows) >= 3
        scenario_ids = {r["scenario_id"] for r in all_rows}
        assert {"multi-0", "multi-1", "multi-2"}.issubset(scenario_ids)
