"""
test_fix_loop.py — Temporal Test-Fix-Test Loop for autonomous Kairo Phantom repairs.

Enforces 4 critical security guardrails:
  1. Protected Paths      — fixer may NOT edit security stack / oracles / CI gates
  2. Oracle Immutability  — verify oracles.py Ed25519 signature before every attempt
  3. Regression Gate      — every fix re-runs the full passing test set
  4. Convergence/Oscillation Detection — duplicate diff hashes → QUARANTINE

Terminal states:
  PASS       → reward +1.0
  QUARANTINE → reward -1.0  + auto-ticket JSON in target/quarantine_tickets/
  ESCALATE   → reward -2.0  (protected path touched — halt immediately)
"""

import os
import time
import json
import hashlib
import logging
import dataclasses
from typing import Dict, Any, List, Set, Tuple, Callable, Optional

log = logging.getLogger("kairo.fix_loop")


ORACLES_PUBLIC_KEY_PEM = (
    b"-----BEGIN PUBLIC KEY-----\n"
    b"MCowBQYDK2VwAyEAdN5sj0iAlSqs4nIniU+utRMrwm70c4yfZzgR0MCv/+8=\n"
    b"-----END PUBLIC KEY-----\n"
)

# ── Reward constants ──────────────────────────────────────────────────────────
REWARD_PASS = 1.0
REWARD_QUARANTINE = -1.0
REWARD_ESCALATE = -2.0


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclasses.dataclass
class AttemptRecord:
    """One iteration of the fix loop."""

    attempt: int
    timestamp: float  # epoch seconds
    patch_hash: str  # SHA-256 of the diff string
    guardrails_checked: List[str]
    test_result: str  # "PASS" | "FAIL" | "ERROR"
    action_taken: str  # "APPLY_PATCH" | "ROLLBACK" | "ESCALATE" | "QUARANTINE"
    elapsed_ms: float


@dataclasses.dataclass
class LoopResult:
    """Full result of a TestFixLoop.run_loop() call."""

    scenario_id: str
    terminal_state: str  # "PASS" | "QUARANTINE" | "ESCALATE"
    reward: float
    attempts_used: int
    elapsed_s: float
    audit_trail: List[AttemptRecord]
    failure_reason: Optional[str] = None
    ticket_path: Optional[str] = None  # set if QUARANTINE ticket was written


# ── Exceptions ────────────────────────────────────────────────────────────────


class ProtectedPathViolation(Exception):
    """Raised when an auto-fix attempts to modify a protected security path."""

    pass


class OscillationDetected(Exception):
    """Raised when an auto-fix enters an infinite loop or repeats previous diffs."""

    pass


# ── Main class ────────────────────────────────────────────────────────────────


class TestFixLoop:
    """Orchestrates the temporal Test-Fix-Test loop under 4 safety guardrails."""

    PROTECTED_PATHS = {
        "phantom-core/src/response_validator.rs",
        "phantom-core/src/sentinel.rs",
        "phantom-core/src/guardrails.rs",
        "phantom-core/src/prompt_injection_firewall.rs",
        "kairo-sidecar/sidecar/oracles.py",
        "kairo-sidecar/sidecar/oracles.py.sig",
        "kairo-sidecar/sidecar/oracles.py.pub",
        "kairo-sidecar/sidecar/test_fix_loop.py",
        "scripts/ci/sbom_gate.py",
        "scripts/ci/eval_integrity_guard.py",
        "scripts/ci/no_skip_gates.py",
    }

    def __init__(
        self,
        workspace_root: str,
        budget_attempts: int = 5,
        budget_seconds: float = 300.0,
    ):
        self.workspace_root = workspace_root
        self.budget_attempts = budget_attempts
        self.budget_seconds = budget_seconds
        self.diff_history: List[str] = []

    # ── Guardrail 1 ───────────────────────────────────────────────────────────

    def verify_patch_safety(self, modified_files: Set[str]) -> None:
        """Enforce Guardrail 1: Protected Paths."""
        for file in modified_files:
            abs_path_unix = os.path.abspath(os.path.join(self.workspace_root, file)).replace(
                "\\", "/"
            )
            for protected in self.PROTECTED_PATHS:
                protected_unix = protected.replace("\\", "/")
                if abs_path_unix.endswith("/" + protected_unix) or abs_path_unix == protected_unix:
                    raise ProtectedPathViolation(f"Unauthorized edit: '{file}' is protected!")
                if protected_unix.startswith("kairo-sidecar/"):
                    short_protected = protected_unix[len("kairo-sidecar/") :]
                    if (
                        abs_path_unix.endswith("/" + short_protected)
                        or abs_path_unix == short_protected
                    ):
                        raise ProtectedPathViolation(f"Unauthorized edit: '{file}' is protected!")

    # ── Guardrail 2 ───────────────────────────────────────────────────────────

    def verify_oracles_signature(self) -> None:
        """Enforce Guardrail 2: Oracle Immutability — verify oracles.py Ed25519 signature."""
        dir_path = os.path.dirname(os.path.abspath(__file__))
        oracles_path = os.path.normpath(os.path.join(dir_path, "oracles.py"))
        pub_path = os.path.normpath(os.path.join(dir_path, "oracles.py.pub"))
        sig_path = os.path.normpath(os.path.join(dir_path, "oracles.py.sig"))

        if not os.path.exists(oracles_path):
            raise PermissionError("Module oracles.py is missing!")
        if not os.path.exists(sig_path):
            raise PermissionError("Signature oracles.py.sig is missing!")

        if os.path.exists(pub_path):
            with open(pub_path, "rb") as f:
                disk_pub_bytes = f.read()
            if (
                disk_pub_bytes.replace(b"\r\n", b"\n").strip()
                != ORACLES_PUBLIC_KEY_PEM.replace(b"\r\n", b"\n").strip()
            ):
                raise PermissionError("Public key on disk does not match pinned public key!")

        try:
            from cryptography.hazmat.primitives import serialization

            with open(sig_path, "rb") as f:
                sig_bytes = f.read()
            with open(oracles_path, "rb") as f:
                oracles_bytes = f.read()

            public_key = serialization.load_pem_public_key(ORACLES_PUBLIC_KEY_PEM)
            public_key.verify(sig_bytes, oracles_bytes)
        except Exception as e:
            raise PermissionError(f"Signature verification failed for oracles.py: {e}")

    # ── Guardrail 4 ───────────────────────────────────────────────────────────

    def check_convergence(self, patch_diff: str) -> None:
        """Enforce Guardrail 4: Convergence / Oscillation Detection."""
        patch_hash = hashlib.sha256(patch_diff.encode("utf-8")).hexdigest()
        if patch_hash in self.diff_history:
            raise OscillationDetected("Auto-fix loop detected oscillation/duplicate diff.")
        self.diff_history.append(patch_hash)

    # ── Auto-ticket ──────────────────────────────────────────────────────────

    def _write_quarantine_ticket(
        self,
        scenario_id: str,
        failure_reason: str,
        audit_trail: List[AttemptRecord],
    ) -> str:
        """Write a quarantine ticket JSON and return its path."""
        ts = int(time.time())
        ticket_dir = os.path.join(self.workspace_root, "target", "quarantine_tickets")
        os.makedirs(ticket_dir, exist_ok=True)
        ticket_path = os.path.join(ticket_dir, f"{scenario_id}_{ts}.json")
        ticket = {
            "scenario_id": scenario_id,
            "terminal_state": "QUARANTINE",
            "failure_reason": failure_reason,
            "timestamp": ts,
            "attempts": [dataclasses.asdict(a) for a in audit_trail],
        }
        with open(ticket_path, "w", encoding="utf-8") as fh:
            json.dump(ticket, fh, indent=2)
        log.info(f"[Fix Loop] Quarantine ticket written: {ticket_path}")
        return ticket_path

    # ── Argilla queue append ──────────────────────────────────────────────────

    def _append_argilla_queue(
        self,
        scenario_id: str,
        terminal_state: str,
        failure_reason: str,
        audit_trail: List[AttemptRecord],
    ) -> None:
        """Append a pending human-review record to target/argilla_queue.jsonl."""
        import uuid as _uuid

        queue_path = os.path.join(self.workspace_root, "target", "argilla_queue.jsonl")
        os.makedirs(os.path.dirname(queue_path), exist_ok=True)
        record = {
            "id": str(_uuid.uuid4()),
            "scenario_id": scenario_id,
            "terminal_state": terminal_state,
            "failure_reason": failure_reason,
            "attempt_log": [dataclasses.asdict(a) for a in audit_trail],
            "label": None,
            "reviewed_at": None,
            "created_at": time.time(),
        }
        with open(queue_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        log.info(f"[Fix Loop] Argilla queue record appended for {scenario_id}.")

    # ── MLflow logging ────────────────────────────────────────────────────────

    def _log_mlflow(self, result: LoopResult) -> None:
        """Log loop result to MLflow (graceful degradation if not installed)."""
        try:
            import mlflow

            state_code = {"PASS": 0, "QUARANTINE": 1, "ESCALATE": 2}.get(result.terminal_state, -1)
            ts = int(time.time())
            run_name = f"fix_loop_{result.scenario_id}_{ts}"
            tracking_uri = os.path.join(self.workspace_root, "mlruns")
            mlflow.set_tracking_uri(f"file://{tracking_uri}")
            mlflow.set_experiment("kairo_fix_loop")
            with mlflow.start_run(run_name=run_name):
                mlflow.log_params(
                    {
                        "scenario_id": result.scenario_id,
                        "budget_attempts": self.budget_attempts,
                        "budget_seconds": self.budget_seconds,
                    }
                )
                mlflow.log_metrics(
                    {
                        "reward": result.reward,
                        "attempts_used": float(result.attempts_used),
                        "elapsed_s": result.elapsed_s,
                        "terminal_state_code": float(state_code),
                    }
                )
                if result.ticket_path and os.path.exists(result.ticket_path):
                    mlflow.log_artifact(result.ticket_path)
            log.info(f"[Fix Loop] MLflow run '{run_name}' logged.")
        except ImportError:
            log.warning("[Fix Loop] mlflow not installed — skipping MLflow logging.")
        except Exception as e:
            log.warning(f"[Fix Loop] MLflow logging failed (non-fatal): {e}")

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run_loop(
        self,
        scenario_id: str,
        initial_fail_result: Dict[str, Any],
        run_tests_fn: Callable[[], bool],
        generate_fix_fn: Callable[[Dict[str, Any]], Tuple[str, Set[str]]],
        apply_patch_fn: Callable[[str], None],
        rollback_fn: Callable[[], None],
        log_to_store: bool = True,
    ) -> LoopResult:
        """
        Execute the temporal Test-Fix-Test loop.

        Returns a LoopResult with terminal_state in {PASS, QUARANTINE, ESCALATE}
        and reward +1.0 / -1.0 / -2.0 respectively.
        """
        log.info(
            f"[Fix Loop] Starting repair loop for scenario {scenario_id} "
            f"(budget: {self.budget_attempts} attempts / {self.budget_seconds}s)..."
        )
        self.verify_oracles_signature()
        self.diff_history.clear()

        audit_trail: List[AttemptRecord] = []
        start_time = time.monotonic()
        current_failure = initial_fail_result
        terminal_state = "QUARANTINE"
        failure_reason = "Budget exhausted"

        for attempt in range(1, self.budget_attempts + 1):
            attempt_start = time.monotonic()
            elapsed_so_far = attempt_start - start_time

            # Time-budget check
            if elapsed_so_far >= self.budget_seconds:
                failure_reason = (
                    f"Wall-clock budget of {self.budget_seconds}s exceeded "
                    f"after {attempt - 1} attempt(s)."
                )
                log.warning(f"[Fix Loop] Time budget exceeded: {elapsed_so_far:.1f}s")
                break

            log.info(
                f"[Fix Loop] Attempt {attempt}/{self.budget_attempts} "
                f"(elapsed {elapsed_so_far:.1f}s / {self.budget_seconds}s)..."
            )
            self.verify_oracles_signature()

            guardrails_checked: List[str] = ["oracle_immutability"]
            patch_hash = ""
            test_result_str = "ERROR"
            action_taken = "ROLLBACK"

            try:
                # 1. Generate fix patch
                patch_diff, modified_files = generate_fix_fn(current_failure)
                patch_hash = hashlib.sha256(patch_diff.encode("utf-8")).hexdigest()

                # 2. Guardrail 1: Protected Paths
                guardrails_checked.append("protected_paths")
                self.verify_patch_safety(modified_files)

                # 3. Guardrail 4: Convergence
                guardrails_checked.append("convergence")
                self.check_convergence(patch_diff)

                # 4. Apply patch
                apply_patch_fn(patch_diff)
                action_taken = "APPLY_PATCH"

                # 5. Guardrail 3: Regression Gate
                guardrails_checked.append("regression_gate")
                log.info("[Fix Loop] Running regression gate...")
                tests_passed = run_tests_fn()
                test_result_str = "PASS" if tests_passed else "FAIL"

                if tests_passed:
                    elapsed_attempt = (time.monotonic() - attempt_start) * 1000
                    audit_trail.append(
                        AttemptRecord(
                            attempt=attempt,
                            timestamp=time.time(),
                            patch_hash=patch_hash,
                            guardrails_checked=guardrails_checked,
                            test_result=test_result_str,
                            action_taken="APPLY_PATCH",
                            elapsed_ms=elapsed_attempt,
                        )
                    )
                    terminal_state = "PASS"
                    failure_reason = None
                    log.info(f"✅ [Fix Loop] Scenario {scenario_id} PASS on attempt {attempt}.")
                    break
                else:
                    log.warning("[Fix Loop] Tests failed after patch — rolling back.")
                    rollback_fn()
                    action_taken = "ROLLBACK"
                    current_failure = {
                        "attempt": attempt,
                        "status": "FAIL",
                        "reason": "Tests failed after patch application",
                    }

            except ProtectedPathViolation as e:
                log.critical(f"🛑 [Fix Loop] ESCALATE — protected path: {e}")
                rollback_fn()
                terminal_state = "ESCALATE"
                failure_reason = str(e)
                action_taken = "ESCALATE"
                test_result_str = "ERROR"
                elapsed_attempt = (time.monotonic() - attempt_start) * 1000
                audit_trail.append(
                    AttemptRecord(
                        attempt=attempt,
                        timestamp=time.time(),
                        patch_hash=patch_hash,
                        guardrails_checked=guardrails_checked,
                        test_result=test_result_str,
                        action_taken=action_taken,
                        elapsed_ms=elapsed_attempt,
                    )
                )
                break  # No further attempts on ESCALATE

            except OscillationDetected as e:
                log.warning(f"⚠️  [Fix Loop] QUARANTINE — oscillation: {e}")
                rollback_fn()
                terminal_state = "QUARANTINE"
                failure_reason = str(e)
                action_taken = "QUARANTINE"
                test_result_str = "ERROR"
                elapsed_attempt = (time.monotonic() - attempt_start) * 1000
                audit_trail.append(
                    AttemptRecord(
                        attempt=attempt,
                        timestamp=time.time(),
                        patch_hash=patch_hash,
                        guardrails_checked=guardrails_checked,
                        test_result=test_result_str,
                        action_taken=action_taken,
                        elapsed_ms=elapsed_attempt,
                    )
                )
                break

            except Exception as e:
                log.error(f"[Fix Loop] Attempt {attempt} error: {e}")
                rollback_fn()
                test_result_str = "ERROR"
                action_taken = "ROLLBACK"

            elapsed_attempt = (time.monotonic() - attempt_start) * 1000
            audit_trail.append(
                AttemptRecord(
                    attempt=attempt,
                    timestamp=time.time(),
                    patch_hash=patch_hash,
                    guardrails_checked=guardrails_checked,
                    test_result=test_result_str,
                    action_taken=action_taken,
                    elapsed_ms=elapsed_attempt,
                )
            )

        total_elapsed = time.monotonic() - start_time
        reward_map = {
            "PASS": REWARD_PASS,
            "QUARANTINE": REWARD_QUARANTINE,
            "ESCALATE": REWARD_ESCALATE,
        }
        reward = reward_map.get(terminal_state, REWARD_QUARANTINE)

        ticket_path: Optional[str] = None

        # Emit quarantine ticket for QUARANTINE and ESCALATE
        if terminal_state in ("QUARANTINE", "ESCALATE"):
            ticket_path = self._write_quarantine_ticket(
                scenario_id, failure_reason or "Unknown", audit_trail
            )
            self._append_argilla_queue(
                scenario_id, terminal_state, failure_reason or "Unknown", audit_trail
            )

        result = LoopResult(
            scenario_id=scenario_id,
            terminal_state=terminal_state,
            reward=reward,
            attempts_used=len(audit_trail),
            elapsed_s=total_elapsed,
            audit_trail=audit_trail,
            failure_reason=failure_reason,
            ticket_path=ticket_path,
        )

        # Log to DuckDB outcome store
        if log_to_store:
            try:
                from sidecar.outcome_store import OutcomeStore

                store = OutcomeStore()
                store.log_loop_result(result)
            except Exception as e:
                log.warning(f"[Fix Loop] DuckDB store logging failed (non-fatal): {e}")

        # MLflow
        self._log_mlflow(result)

        log.info(
            f"[Fix Loop] DONE — scenario={scenario_id} "
            f"state={terminal_state} reward={reward:+.1f} "
            f"attempts={len(audit_trail)} elapsed={total_elapsed:.2f}s"
        )
        return result
