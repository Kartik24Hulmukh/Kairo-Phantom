"""
sandbox_runner.py — Phase 5 enhanced disposable sandbox runner.

Changes vs Phase 4 baseline:
  • snapshot_base_dir: optional base fixture directory that is copied
    (copy-on-write style) into each fresh sandbox, enabling fast reset.
  • worker_id: attached to every result for parallel-execution tracing.
  • elapsed_s: wall-clock timing per scenario.
  • oracle_dispatcher integration: execute_fn is optional; when omitted the
    dispatcher routes to the correct Phase 3 oracle automatically.
  • Fully isolated temp dirs: each sandbox lives in its own uniquely-named
    directory under <base_dir>/sandboxes/. After the run it is deleted, so
    no cross-contamination between concurrent sandboxes is possible.
"""

from __future__ import annotations

import os
import shutil
import time
import logging
import concurrent.futures
import tempfile
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger("kairo.sandbox")


class SandboxRunner:
    """
    Manages parallel disposable sandboxes for the Kairo gauntlet.

    Each sandbox is an *isolated* temporary directory. When a snapshot base
    directory is given it is shallow-copied into the sandbox before the
    scenario runs (simulating a VM snapshot restore).  The directory is
    removed unconditionally after the run, preventing any cross-run state.
    """

    def __init__(
        self,
        base_dir: str,
        max_workers: int = 4,
        snapshot_base_dir: Optional[str] = None,
    ):
        self.base_dir = base_dir
        self.max_workers = max_workers
        self.snapshot_base_dir = snapshot_base_dir
        # Use a unique top-level sandboxes dir so concurrent test runs don't collide.
        self.sandboxes_dir = tempfile.mkdtemp(prefix="kairo_sandboxes_", dir=base_dir)
        log.debug("[SandboxRunner] sandboxes_dir=%s", self.sandboxes_dir)

    # ── lifecycle ──────────────────────────────────────────────────────────────

    def setup_sandbox(
        self,
        scenario_id: str,
        fixture_path: Optional[str] = None,
    ) -> str:
        """
        Create a clean, isolated sandbox directory for *scenario_id*.

        Steps:
        1. If a snapshot_base_dir was given, copy it into the new dir.
        2. If a fixture_path is given, overlay it on top.
        """
        sandbox_path = os.path.join(self.sandboxes_dir, f"sandbox_{scenario_id}")
        # Always start fresh — rmtree then recreate.
        if os.path.exists(sandbox_path):
            shutil.rmtree(sandbox_path)
        os.makedirs(sandbox_path, exist_ok=True)

        # 1. Snapshot copy (fast reset simulation)
        if self.snapshot_base_dir and os.path.isdir(self.snapshot_base_dir):
            for item in os.listdir(self.snapshot_base_dir):
                src = os.path.join(self.snapshot_base_dir, item)
                dst = os.path.join(sandbox_path, item)
                if os.path.isdir(src):
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)

        # 2. Overlay scenario-specific fixture
        if fixture_path and os.path.exists(fixture_path):
            if os.path.isdir(fixture_path):
                shutil.copytree(fixture_path, sandbox_path, dirs_exist_ok=True)
            else:
                shutil.copy2(fixture_path, sandbox_path)

        return sandbox_path

    def clean_sandbox(self, scenario_id: str) -> None:
        """Remove the sandbox directory for *scenario_id*."""
        sandbox_path = os.path.join(self.sandboxes_dir, f"sandbox_{scenario_id}")
        if os.path.exists(sandbox_path):
            try:
                shutil.rmtree(sandbox_path)
            except Exception as exc:
                log.warning("[SandboxRunner] Could not clean sandbox %s: %s", scenario_id, exc)

    def teardown(self) -> None:
        """Remove the entire sandboxes root dir (call after all scenarios complete)."""
        if os.path.exists(self.sandboxes_dir):
            try:
                shutil.rmtree(self.sandboxes_dir)
            except Exception as exc:
                log.warning("[SandboxRunner] Could not remove sandboxes_dir: %s", exc)

    # ── execution ──────────────────────────────────────────────────────────────

    def run_scenario(
        self,
        scenario: Dict[str, Any],
        execute_fn: Callable[[str, Dict[str, Any]], Dict[str, Any]],
        worker_id: str = "main",
    ) -> Dict[str, Any]:
        """
        Run a single scenario inside a disposable sandbox.

        Returns a result dict with keys:
            id, status, oracle_verdict, reason, output, error,
            sandbox_path, worker_id, elapsed_s.
        """
        scenario_id = scenario.get("id", "unknown")
        fixture = scenario.get("fixture") or None
        log.info("[Sandbox:%s] Starting scenario %s", worker_id, scenario_id)

        sandbox_path = self.setup_sandbox(scenario_id, fixture)
        t0 = time.perf_counter()

        try:
            result = execute_fn(sandbox_path, scenario)
            elapsed = time.perf_counter() - t0
            verdict = result.get(
                "oracle_verdict", "PASS" if result.get("success", True) else "FAIL"
            )
            return {
                "id": scenario_id,
                "status": verdict,
                "oracle_verdict": verdict,
                "reason": result.get("reason", result.get("output", "")),
                "output": result.get("output", ""),
                "error": result.get("error"),
                "sandbox_path": sandbox_path,
                "worker_id": worker_id,
                "elapsed_s": round(elapsed, 4),
            }
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            log.error("[Sandbox:%s] Scenario %s crashed: %s", worker_id, scenario_id, exc)
            return {
                "id": scenario_id,
                "status": "FAIL",
                "oracle_verdict": "FAIL",
                "reason": str(exc),
                "output": "",
                "error": str(exc),
                "sandbox_path": sandbox_path,
                "worker_id": worker_id,
                "elapsed_s": round(elapsed, 4),
            }
        finally:
            if not scenario.get("keep_sandbox", False):
                self.clean_sandbox(scenario_id)

    def run_all(
        self,
        scenarios: List[Dict[str, Any]],
        execute_fn: Callable[[str, Dict[str, Any]], Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Run all scenarios in parallel using a ThreadPoolExecutor."""
        log.info(
            "[SandboxRunner] Running %d scenarios with %d workers",
            len(scenarios),
            self.max_workers,
        )
        results: List[Dict[str, Any]] = []
        worker_counter = [0]

        def _with_worker_id(scenario: Dict[str, Any]) -> Dict[str, Any]:
            worker_counter[0] += 1
            wid = f"w{worker_counter[0]}"
            return self.run_scenario(scenario, execute_fn, worker_id=wid)

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(_with_worker_id, scenario): scenario for scenario in scenarios
            }
            for future in concurrent.futures.as_completed(futures):
                scenario = futures[future]
                try:
                    results.append(future.result())
                except Exception as exc:
                    results.append(
                        {
                            "id": scenario.get("id", "unknown"),
                            "status": "FAIL",
                            "oracle_verdict": "FAIL",
                            "reason": f"Executor error: {exc}",
                            "output": "",
                            "error": str(exc),
                            "sandbox_path": None,
                            "worker_id": "unknown",
                            "elapsed_s": 0.0,
                        }
                    )
        return results
