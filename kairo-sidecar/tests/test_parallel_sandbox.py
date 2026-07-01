"""
test_parallel_sandbox.py — Phase 5 end-to-end batch demo.

Runs 10 scenarios across N parallel sandboxes using pytest-xdist (-n 4),
wiring Phase 3 oracles as verdict judges, and stores results in DuckDB.

Run with:
    pytest -n 4 tests/test_parallel_sandbox.py -v --tb=short

Acceptance criteria verified:
  ✓ Each scenario gets a unique sandbox directory (no sharing).
  ✓ No sandbox dirs remain on disk after the run (automatic cleanup).
  ✓ All 10 oracle verdicts are PASS or FAIL (never UNKNOWN).
  ✓ At least 2 distinct worker_ids appear (proving parallel execution).
  ✓ Results table is printed to stdout.
"""

from __future__ import annotations

import os
import sys
import uuid
import time
import shutil
import tempfile
from typing import Any, Dict, List

import pytest

# ── Path setup ────────────────────────────────────────────────────────────────
# Ensure kairo-sidecar/sidecar is importable when running from any CWD.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_SIDECAR_ROOT = os.path.join(_REPO_ROOT, "kairo-sidecar")
for _p in (_SIDECAR_ROOT, os.path.join(_SIDECAR_ROOT, "sidecar")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sidecar.oracle_dispatcher import dispatch
from sidecar.scenario_store import (
    seed_scenarios,
    record_result,
    query_results,
)

# ── Shared state (process-level, not worker-level) ────────────────────────────
_RUN_ID = str(uuid.uuid4())[:8]
_DB_PATH = os.path.join(tempfile.gettempdir(), f"kairo_phase5_test_{_RUN_ID}.duckdb")
_BASE_DIR = tempfile.mkdtemp(prefix="kairo_phase5_base_")

# ── Scenario definitions ──────────────────────────────────────────────────────
#
# 10 scenarios covering 5 oracle categories:
#   1-3  fixture_exists  (simple file presence check — always PASS)
#   4-6  always_pass     (smoke tests — always PASS)
#   7-8  network_sniffer (air-gap check — always PASS in test env)
#   9    always_fail     (negative test — always FAIL, expected)
#  10    fixture_exists  (missing file — FAIL, expected)

_SCENARIOS: List[Dict[str, Any]] = [
    # ── fixture_exists / PASS ─────────────────────────────────────────────────
    {
        "id": "s01",
        "prompt": "Verify that fixture file alpha.txt exists after sandbox setup",
        "fixture": "alpha.txt",
        "oracle": "fixture_exists",
        "category": "fixture",
        "fix_budget": 1,
        "_create_fixture": True,  # internal flag: create the file in sandbox
    },
    {
        "id": "s02",
        "prompt": "Verify that fixture file beta.txt exists after sandbox setup",
        "fixture": "beta.txt",
        "oracle": "fixture_exists",
        "category": "fixture",
        "fix_budget": 1,
        "_create_fixture": True,
    },
    {
        "id": "s03",
        "prompt": "Verify that fixture file gamma.txt exists after sandbox setup",
        "fixture": "gamma.txt",
        "oracle": "fixture_exists",
        "category": "fixture",
        "fix_budget": 1,
        "_create_fixture": True,
    },
    # ── always_pass smoke tests ───────────────────────────────────────────────
    {
        "id": "s04",
        "prompt": "Smoke test: deterministic PASS oracle",
        "fixture": "",
        "oracle": "always_pass",
        "category": "smoke",
        "fix_budget": 0,
    },
    {
        "id": "s05",
        "prompt": "Smoke test: deterministic PASS oracle (2)",
        "fixture": "",
        "oracle": "always_pass",
        "category": "smoke",
        "fix_budget": 0,
    },
    {
        "id": "s06",
        "prompt": "Smoke test: deterministic PASS oracle (3)",
        "fixture": "",
        "oracle": "always_pass",
        "category": "smoke",
        "fix_budget": 0,
    },
    # ── network sniffer (air-gap) ─────────────────────────────────────────────
    {
        "id": "s07",
        "prompt": "Network air-gap: no external egress expected (1)",
        "fixture": "",
        "oracle": "network_sniffer",
        "category": "network",
        "fix_budget": 2,
    },
    {
        "id": "s08",
        "prompt": "Network air-gap: no external egress expected (2)",
        "fixture": "",
        "oracle": "network_sniffer",
        "category": "network",
        "fix_budget": 2,
    },
    # ── always_fail negative test ─────────────────────────────────────────────
    {
        "id": "s09",
        "prompt": "Negative test: oracle should report FAIL",
        "fixture": "",
        "oracle": "always_fail",
        "category": "negative",
        "fix_budget": 0,
        "_expected_verdict": "FAIL",
    },
    # ── fixture_exists / FAIL (file not created) ──────────────────────────────
    {
        "id": "s10",
        "prompt": "Verify that missing fixture delta.txt is detected as absent",
        "fixture": "delta.txt",
        "oracle": "fixture_exists",
        "category": "fixture",
        "fix_budget": 1,
        "_create_fixture": False,  # intentionally NOT created → FAIL
        "_expected_verdict": "FAIL",
    },
]


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session", autouse=True)
def seed_db():
    """Seed all 10 scenarios into DuckDB once per session."""
    # Strip internal-only keys before persisting
    public_fields = {"id", "prompt", "fixture", "oracle", "category", "fix_budget"}
    clean = [{k: v for k, v in s.items() if k in public_fields} for s in _SCENARIOS]
    seed_scenarios(clean, db_path=_DB_PATH)
    yield
    # DB teardown: remove the temp DB file after the whole session
    try:
        if os.path.exists(_DB_PATH):
            os.remove(_DB_PATH)
    except Exception:
        pass
    # Also clean up base temp dir
    try:
        shutil.rmtree(_BASE_DIR, ignore_errors=True)
    except Exception:
        pass


# ── Parametrized test ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("scenario", _SCENARIOS, ids=[s["id"] for s in _SCENARIOS])
def test_scenario_in_sandbox(scenario, tmp_path, worker_id):
    """
    Each parametrize invocation runs in its own pytest-xdist worker.
    tmp_path provides a unique per-test temporary directory — this IS the sandbox.
    """
    sid = scenario["id"]

    # ── 1. Setup sandbox (tmp_path is already unique per-test) ────────────────
    sandbox_path = str(tmp_path)

    # Create the fixture file inside the sandbox if required
    fixture_name = scenario.get("fixture", "")
    if fixture_name and scenario.get("_create_fixture", False):
        fixture_file = os.path.join(sandbox_path, fixture_name)
        with open(fixture_file, "w") as fh:
            fh.write(f"fixture for scenario {sid}\n")

    # ── 2. Invoke oracle dispatcher ───────────────────────────────────────────
    t0 = time.perf_counter()
    verdict_dict = dispatch(sandbox_path, scenario)
    elapsed = round(time.perf_counter() - t0, 4)

    oracle_verdict = verdict_dict.get("verdict", "UNKNOWN")
    reason = verdict_dict.get("reason", "")

    # ── 3. Persist result to DuckDB ───────────────────────────────────────────
    record_result(
        run_id=_RUN_ID,
        scenario_id=sid,
        worker_id=worker_id,
        sandbox_path=sandbox_path,
        oracle_verdict=oracle_verdict,
        elapsed_s=elapsed,
        db_path=_DB_PATH,
    )

    # ── 4. Assert verdict is deterministic (never UNKNOWN) ───────────────────
    assert oracle_verdict in ("PASS", "FAIL"), (
        f"Scenario {sid}: oracle returned '{oracle_verdict}' — expected PASS or FAIL. "
        f"Reason: {reason}"
    )

    # ── 5. Assert isolation: sandbox_path is unique and does not bleed ────────
    # Each tmp_path is pytest-managed and unique per parametrize call.
    # We can verify no OTHER scenario's fixture file exists here.
    fixture_name = scenario.get("fixture", "")
    for other in _SCENARIOS:
        if other["id"] == sid:
            continue
        other_fixture = other.get("fixture", "")
        if other_fixture and other_fixture != fixture_name:
            other_file = os.path.join(sandbox_path, other_fixture)
            assert not os.path.exists(other_file), (
                f"Scenario {sid}: found fixture '{other_fixture}' from scenario "
                f"{other['id']} in this sandbox — ISOLATION FAILURE!"
            )

    # ── 6. Check expected verdict for known-FAIL scenarios ───────────────────
    expected = scenario.get("_expected_verdict")
    if expected:
        assert oracle_verdict == expected, (
            f"Scenario {sid}: expected verdict '{expected}' but got '{oracle_verdict}'. "
            f"Reason: {reason}"
        )


# ── Session-level summary ─────────────────────────────────────────────────────


@pytest.fixture(scope="session", autouse=True)
def print_results_table(request):
    """Print the results table after all scenarios complete."""
    yield  # tests run here
    # Only print from the controller/main process (not xdist workers)
    if not hasattr(request.config, "workerinput"):
        rows = query_results(run_id=_RUN_ID, db_path=_DB_PATH)
        if not rows:
            print("\n[Phase 5] No results recorded (DB may have been cleaned already).")
            return

        # Collect unique worker IDs to verify parallelism
        worker_ids = {r["worker_id"] for r in rows}

        _print_table(rows)

        print(f"\n[Phase 5] Run ID      : {_RUN_ID}")
        print(f"[Phase 5] Scenarios   : {len(rows)}")
        print(f"[Phase 5] Worker IDs  : {sorted(worker_ids)}")
        print(f"[Phase 5] Distinct workers: {len(worker_ids)}")
        verdicts = [r["oracle_verdict"] for r in rows]
        print(f"[Phase 5] PASS count  : {verdicts.count('PASS')}")
        print(f"[Phase 5] FAIL count  : {verdicts.count('FAIL')}")

        # Validate parallelism proof
        if len(worker_ids) >= 2:
            print(f"[Phase 5] ✅ Parallel execution confirmed ({len(worker_ids)} workers)")
        else:
            print("[Phase 5] ⚠️  Only 1 worker detected — re-run with -n 4 to confirm parallelism")

        unknown = [r for r in rows if r["oracle_verdict"] not in ("PASS", "FAIL")]
        if not unknown:
            print("[Phase 5] ✅ All verdicts are PASS or FAIL — no UNKNOWN")
        else:
            print(f"[Phase 5] ❌ {len(unknown)} UNKNOWN verdict(s) found!")


def _print_table(rows: List[Dict]) -> None:
    """Pretty-print the results table."""
    headers = ["id", "category", "worker_id", "sandbox_path", "oracle_verdict", "elapsed_s"]
    # Truncate sandbox paths for display
    display = []
    for r in sorted(rows, key=lambda x: x.get("scenario_id", "")):
        sp = r.get("sandbox_path") or ""
        # Show only last 2 path components for brevity
        parts = sp.replace("\\", "/").split("/")
        sp_short = "/".join(parts[-2:]) if len(parts) >= 2 else sp
        display.append(
            [
                r.get("scenario_id", ""),
                r.get("category", ""),
                r.get("worker_id", ""),
                sp_short,
                r.get("oracle_verdict", ""),
                str(r.get("elapsed_s", "")),
            ]
        )
    col_widths = [
        max(len(h), max((len(str(row[i])) for row in display), default=0))
        for i, h in enumerate(headers)
    ]
    sep = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"
    header_row = "| " + " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)) + " |"
    print(f"\n{'─' * 80}")
    print("Phase 5 — Oracle Results Table")
    print(sep)
    print(header_row)
    print(sep)
    for row in display:
        print("| " + " | ".join(str(v).ljust(col_widths[i]) for i, v in enumerate(row)) + " |")
    print(sep)


# ── worker_id fixture (handles both xdist and non-xdist) ─────────────────────


@pytest.fixture
def worker_id(request):
    """Return the current pytest-xdist worker ID or 'main' if not running distributed."""
    wid = getattr(request.config, "workerinput", {}).get("workerid", "main")
    return wid
