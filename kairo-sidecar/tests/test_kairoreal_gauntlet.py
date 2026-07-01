"""
tests/test_kairoreal_gauntlet.py — Pytest verification of the headless gauntlet runner.

Requirements:
  - Verifies run_kairoreal_gauntlet is importable and scenario count == 200
  - Runs a mini-gauntlet of <=5 active scenarios across >=2 categories through the real executor
  - Verifies task_completion_rate.json schema and pass_rate_active >= 80% after a full run
  - Must pass in headless/CI environments with no UI, no network, no real applications
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

# ── Path helpers ──────────────────────────────────────────────────────────────
_TESTS_DIR = Path(__file__).parent
_REPO_ROOT = (_TESTS_DIR / ".." / "..").resolve()
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
_SCENARIOS_JSON = _REPO_ROOT / "scenarios.json"
_GAUNTLET_SCRIPT = _SCRIPTS_DIR / "run_kairoreal_gauntlet.py"

# Insert sidecar root so executors can import sidecar modules
_SIDECAR_ROOT = _REPO_ROOT / "kairo-sidecar"
for _p in (str(_SIDECAR_ROOT), str(_SIDECAR_ROOT / "sidecar"), str(_SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _load_gauntlet():
    """Import run_kairoreal_gauntlet as a module (cached per process)."""
    if "run_kairoreal_gauntlet" in sys.modules:
        return sys.modules["run_kairoreal_gauntlet"]
    spec = importlib.util.spec_from_file_location("run_kairoreal_gauntlet", str(_GAUNTLET_SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["run_kairoreal_gauntlet"] = mod
    return mod


# ── Test 1: importable + scenario count ──────────────────────────────────────


def test_gauntlet_script_importable_and_scenarios_count():
    """Verify run_kairoreal_gauntlet.py is importable and scenarios.json has 200 entries."""
    rkg = _load_gauntlet()
    assert hasattr(rkg, "run_gauntlet"), "run_gauntlet function must exist"
    assert hasattr(rkg, "run_scenario"), "run_scenario function must exist"
    assert hasattr(rkg, "_CATEGORY_EXECUTORS"), "_CATEGORY_EXECUTORS dict must exist"

    assert _SCENARIOS_JSON.exists(), f"scenarios.json not found at {_SCENARIOS_JSON}"
    with open(_SCENARIOS_JSON, encoding="utf-8") as fh:
        scenarios = json.load(fh)
    assert len(scenarios) == 215, f"Expected 215 scenarios, got {len(scenarios)}"

    # All 14 categories must have executors
    expected_categories = {
        "Word",
        "Excel",
        "PPT",
        "PDF",
        "Legal",
        "Design",
        "Code",
        "Terminal",
        "Email",
        "Memory",
        "Security",
        "Offline",
        "Degradation",
        "Performance",
    }
    missing = expected_categories - set(rkg._CATEGORY_EXECUTORS.keys())
    assert not missing, f"Missing category executors: {missing}"


# ── Test 2: mini gauntlet execution ──────────────────────────────────────────


def test_mini_gauntlet_execution():
    """Run <=5 active scenarios across >=2 categories; all must PASS or SKIP."""
    rkg = _load_gauntlet()

    with open(_SCENARIOS_JSON, encoding="utf-8") as fh:
        scenarios = json.load(fh)

    # Sample one active scenario per category, cap at 5
    active = [s for s in scenarios if s.get("status") == "active"]
    sampled: list = []
    seen_cats: set = set()
    for s in active:
        if s["category"] not in seen_cats:
            sampled.append(s)
            seen_cats.add(s["category"])
        if len(sampled) == 5:
            break

    assert len(sampled) <= 5, f"Sample too large: {len(sampled)}"
    assert len(seen_cats) >= 2, f"Expected >=2 categories in sample, got {seen_cats}"

    base_dir = tempfile.mkdtemp(prefix="kairo_mini_gauntlet_")
    try:
        for scenario in sampled:
            result = rkg.run_scenario(scenario, base_dir)
            assert result["oracle_verdict"] in ("PASS", "SKIP"), (
                f"Scenario {scenario['id']} ({scenario['category']}) "
                f"failed: {result.get('reason', '')}"
            )
    finally:
        shutil.rmtree(base_dir, ignore_errors=True)


# ── Test 3: full run schema + gate ────────────────────────────────────────────


@pytest.mark.slow
def test_task_completion_rate_schema(tmp_path: Path):
    """
    Run the gauntlet script end-to-end via subprocess, verify the output JSON
    schema is complete and pass_rate_active >= 80%.

    Marked @pytest.mark.slow — included in standard `pytest tests/` run but
    skippable with `pytest -m 'not slow'` for quick feedback loops.
    """
    output_path = tmp_path / "task_completion_rate.json"
    result = subprocess.run(
        [
            sys.executable,
            str(_GAUNTLET_SCRIPT),
            "--output",
            str(output_path),
            "--workers",
            "4",
        ],
        capture_output=True,
        text=True,
        timeout=300,  # 5-minute wall-clock cap
    )
    assert result.returncode == 0, (
        f"Gauntlet exited {result.returncode}\n"
        f"STDOUT:\n{result.stdout[-2000:]}\n"
        f"STDERR:\n{result.stderr[-1000:]}"
    )

    assert output_path.exists(), "task_completion_rate.json was not written"

    with open(output_path, encoding="utf-8") as fh:
        data: Dict[str, Any] = json.load(fh)

    # ── Required top-level fields ─────────────────────────────────────────────
    required_top = [
        "product",
        "gauntlet_version",
        "run_at",
        "elapsed_seconds",
        "total",
        "active",
        "pending",
        "excluded",
        "passed",
        "failed",
        "skipped",
        "pass_rate_active",
        "pass_rate_all",
        "verdict",
        "gate_threshold",
        "categories",
        "results",
    ]
    for field in required_top:
        assert field in data, f"Required field missing from report: '{field}'"

    # ── Invariant values ──────────────────────────────────────────────────────
    assert data["product"] == "Kairo Phantom"
    assert data["gauntlet_version"] == "kairoreal-headless-v1"
    assert isinstance(data["elapsed_seconds"], (int, float))
    assert data["total"] == 215
    assert data["active"] == 215
    assert data["pending"] == 0
    assert data["excluded"] == 0
    assert data["gate_threshold"] == 80.0

    # ── Gate: active-scenario pass rate must be >= 80% ────────────────────────
    pass_rate = data["pass_rate_active"]
    assert pass_rate >= 80.0, (
        f"Active pass rate {pass_rate:.1f}% is below 80% gate.\n"
        f"verdict={data['verdict']}  active_passed={data.get('active_passed')}/"
        f"{data['active']}"
    )
    assert data["verdict"] in ("PASS", "PARTIAL"), f"Unexpected verdict '{data['verdict']}'"

    # ── Category structure ────────────────────────────────────────────────────
    expected_cats = {
        "Word",
        "Excel",
        "PPT",
        "PDF",
        "Legal",
        "Design",
        "Code",
        "Terminal",
        "Email",
        "Memory",
        "Security",
        "Offline",
        "Degradation",
        "Performance",
    }
    for cat in expected_cats:
        assert cat in data["categories"], f"Category '{cat}' missing from report"
        cs = data["categories"][cat]
        for sub in ("total", "active", "passed", "failed", "skipped"):
            assert sub in cs, f"Field '{sub}' missing from category '{cat}'"

    # ── Results list ──────────────────────────────────────────────────────────
    assert len(data["results"]) == 215, f"Expected 215 result entries, got {len(data['results'])}"
    for r in data["results"]:
        for field in ("id", "category", "status", "oracle_verdict", "reason", "elapsed_s"):
            assert field in r, f"Field '{field}' missing from result entry {r.get('id', '?')}"
        assert r["oracle_verdict"] in (
            "PASS",
            "FAIL",
            "SKIP",
            "PENDING-REAL-APP",
        ), f"Invalid oracle_verdict '{r['oracle_verdict']}' in {r['id']}"
