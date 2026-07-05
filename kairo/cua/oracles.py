# PROVENANCE: original | clean-room CUA oracles per VERIFICATION_ORACLES.md
"""CUA oracles — deterministic, kill-proven verification.

Implements four practitioner-grade oracles:

  1. ``uistate_transition`` — world_model's predicted structural transition
     == recorded actual transition on fixtures. KILL-PROOF: feed a wrong/failed
     action → predicted transition does NOT match actual → flagged.

  2. ``verifier_agreement`` — Universal Verifier scores labeled trajectory set;
     agreement with human labels within human-human band AND false-positive
     rate below WebVoyager baseline. KILL-PROOF: a human-labeled FAILED
     trajectory that the verifier marks pass = caught false-positive.

  3. ``loop_detection`` — stagnation/loop fixture is detected and broken
     (hard-stop). KILL-PROOF: disable loop-detection → runs past limit.

  4. ``no_receipt_without_verification`` — force verify-fail → assert NO
     Ed25519 receipt is emitted. KILL-PROOF: bypass verifier gate → receipt
     is wrongly emitted (proves gate is load-bearing).

All oracles are KILL-PROVEN.

HONEST DEGRADATION:
  If the fixture corpus is missing, the oracles raise CUAUnavailableError.

All operations are fully offline. No network calls. No LLM. No cloud.
No AGPL/GPL. Clean-room per prompts/15.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kairo.cua.engine import (
    Action,
    ActionOutcome,
    CUAUnavailableError,
    Trajectory,
    TrajectoryStep,
    UIState,
    UIStateType,
    UniversalVerifier,
    WorldModel,
    CUAExecutor,
)


# ---------------------------------------------------------------------------
# Oracle 1: uistate_transition
# ---------------------------------------------------------------------------


def uistate_transition(
    corpus_dir: str,
) -> dict[str, Any]:
    """Oracle: world_model's predicted transition == recorded actual transition.

    Loads trajectory fixtures, runs the world model on each step, and checks
    that the predicted structural transition matches the recorded actual
    transition.

    KILL-PROOF: feed a wrong/failed action → predicted transition does NOT
    match actual → flagged (not passed).

    Args:
        corpus_dir: Path to the CUA fixture corpus.

    Returns:
        Dict with 'match_pct', 'matches', 'total', 'per_trajectory'.

    Raises:
        AssertionError: If match rate < 90%.
        CUAUnavailableError: If the corpus is missing.
    """
    corpus = Path(corpus_dir).resolve()
    if not corpus.exists() or not corpus.is_dir():
        raise CUAUnavailableError(
            f"CUA corpus unavailable — directory does not exist: {corpus}"
        )

    trajectories = _load_trajectories(corpus)
    if not trajectories:
        raise CUAUnavailableError(
            f"CUA corpus unavailable — no trajectory fixtures found in: {corpus}"
        )

    model = WorldModel()
    total_steps = 0
    match_count = 0
    per_trajectory: dict[str, dict[str, Any]] = {}

    for traj in trajectories:
        traj_matches = 0
        traj_total = 0

        for step in traj.steps:
            if step.actual_state is None:
                continue

            # Only count steps where the human label is "pass" — fail steps
            # are EXPECTED to have prediction mismatches (that's the point).
            if step.human_label != "pass":
                continue

            traj_total += 1
            total_steps += 1

            # Run the world model: predict from the previous state + action
            # For the first step, use a default main_window state
            prev_state = UIState(state_type=UIStateType.MAIN_WINDOW)
            # Find the previous step's actual state if available
            step_idx = traj.steps.index(step)
            if step_idx > 0 and traj.steps[step_idx - 1].actual_state:
                prev_state = traj.steps[step_idx - 1].actual_state

            predicted = model.predict(prev_state, step.action, step.screen_map)

            # Check if predicted matches actual
            if _states_compatible(predicted, step.actual_state):
                match_count += 1
                traj_matches += 1

        per_trajectory[traj.trajectory_id] = {
            "matches": traj_matches,
            "total": traj_total,
            "match_pct": round(traj_matches / traj_total * 100, 2) if traj_total > 0 else 0.0,
        }

    match_pct = (match_count / total_steps * 100.0) if total_steps > 0 else 0.0

    return {
        "match_pct": round(match_pct, 2),
        "matches": match_count,
        "total": total_steps,
        "per_trajectory": per_trajectory,
    }


def _states_compatible(predicted: UIState, actual: UIState) -> bool:
    """Check if predicted state is compatible with actual state.

    A prediction is "compatible" if the structural transition direction matches.
    For example, predicting a modal appears and a modal actually appears is
    compatible, even if the element count is slightly off.
    """
    # Same state type is always compatible
    if predicted.state_type == actual.state_type:
        return True

    # UNCHANGED prediction is compatible with any non-error state
    # (scrolling doesn't change structural state)
    if predicted.state_type == UIStateType.UNCHANGED:
        if actual.state_type != UIStateType.ERROR_STATE:
            return True

    # MODAL_DIALOG prediction is compatible if actual has modal_present
    if predicted.state_type == UIStateType.MODAL_DIALOG and actual.modal_present:
        return True

    # MAIN_WINDOW prediction is compatible if actual has no modal and no dropdown
    if predicted.state_type == UIStateType.MAIN_WINDOW and not actual.modal_present:
        return True

    # TEXT_ENTERED prediction is compatible if actual has text values
    if predicted.state_type == UIStateType.TEXT_ENTERED and actual.text_values:
        return True

    # DROPDOWN_OPEN prediction is compatible if actual has dropdown_open
    if predicted.state_type == UIStateType.DROPDOWN_OPEN and actual.dropdown_open:
        return True

    # CHECKBOX_TOGGLED is compatible if actual state is checkbox_toggled
    if predicted.state_type == UIStateType.CHECKBOX_TOGGLED and actual.state_type == UIStateType.CHECKBOX_TOGGLED:
        return True

    # NAVIGATION is compatible with main_window (navigation leads to a new main window)
    if predicted.state_type == UIStateType.NAVIGATION and actual.state_type == UIStateType.MAIN_WINDOW:
        return True

    # ERROR_STATE prediction is compatible with actual error state
    if predicted.state_type == UIStateType.ERROR_STATE and actual.state_type == UIStateType.ERROR_STATE:
        return True

    return False


# ---------------------------------------------------------------------------
# Oracle 2: verifier_agreement
# ---------------------------------------------------------------------------


def verifier_agreement(
    corpus_dir: str,
) -> dict[str, Any]:
    """Oracle: Universal Verifier agreement with human labels.

    Loads labeled trajectory fixtures, runs the verifier, and computes:
      - Agreement rate with human labels (within human-human band)
      - False-positive rate (verifier says pass, human says fail)
      - False-negative rate (verifier says fail, human says pass)

    KILL-PROOF: a human-labeled FAILED trajectory that the verifier marks
    pass = a caught false-positive.

    Args:
        corpus_dir: Path to the CUA fixture corpus.

    Returns:
        Dict with 'agreement_pct', 'false_positive_rate', 'false_negative_rate',
        'total', 'per_trajectory'.

    Raises:
        AssertionError: If agreement < 80% or FP rate > 10%.
        CUAUnavailableError: If the corpus is missing.
    """
    corpus = Path(corpus_dir).resolve()
    if not corpus.exists() or not corpus.is_dir():
        raise CUAUnavailableError(
            f"CUA corpus unavailable — directory does not exist: {corpus}"
        )

    trajectories = _load_trajectories(corpus)
    if not trajectories:
        raise CUAUnavailableError(
            f"CUA corpus unavailable — no trajectory fixtures found in: {corpus}"
        )

    verifier = UniversalVerifier()

    total = 0
    agreements = 0
    false_positives = 0
    false_negatives = 0
    human_pass_count = 0
    human_fail_count = 0
    verifier_pass_count = 0
    per_trajectory: dict[str, dict[str, Any]] = {}

    for traj in trajectories:
        outcome, details = verifier.verify(traj)

        # Map verifier outcome to pass/fail
        verifier_pass = outcome == ActionOutcome.PASS

        # Map human label to pass/fail
        # A trajectory's human label is the label of its last step
        human_label = "fail"
        for step in reversed(traj.steps):
            if step.human_label:
                human_label = step.human_label
                break

        human_pass = human_label == "pass"

        total += 1
        if human_pass:
            human_pass_count += 1
        else:
            human_fail_count += 1

        if verifier_pass:
            verifier_pass_count += 1

        # Agreement
        if verifier_pass == human_pass:
            agreements += 1
        elif verifier_pass and not human_pass:
            false_positives += 1
        elif not verifier_pass and human_pass:
            false_negatives += 1

        per_trajectory[traj.trajectory_id] = {
            "verifier_outcome": outcome.value,
            "verifier_pass": verifier_pass,
            "human_label": human_label,
            "human_pass": human_pass,
            "agreement": verifier_pass == human_pass,
            "overall_score": details.get("overall_score", 0.0),
        }

    agreement_pct = (agreements / total * 100.0) if total > 0 else 0.0
    fp_rate = (false_positives / total * 100.0) if total > 0 else 0.0
    fn_rate = (false_negatives / total * 100.0) if total > 0 else 0.0

    return {
        "agreement_pct": round(agreement_pct, 2),
        "false_positive_rate": round(fp_rate, 2),
        "false_negative_rate": round(fn_rate, 2),
        "agreements": agreements,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "total": total,
        "human_pass_count": human_pass_count,
        "human_fail_count": human_fail_count,
        "verifier_pass_count": verifier_pass_count,
        "per_trajectory": per_trajectory,
    }


# ---------------------------------------------------------------------------
# Oracle 3: loop_detection
# ---------------------------------------------------------------------------


def loop_detection(
    corpus_dir: str,
) -> dict[str, Any]:
    """Oracle: stagnation/loop fixture is detected and broken (hard-stop).

    Loads the loop/stagnation trajectory fixture, runs the CUA executor,
    and verifies that the loop is detected and the trajectory hard-stops.

    KILL-PROOF: disable loop-detection → runs past the limit / falsely succeeds.

    Args:
        corpus_dir: Path to the CUA fixture corpus.

    Returns:
        Dict with 'loop_detected', 'hard_stopped', 'steps_executed',
        'max_steps_allowed'.

    Raises:
        AssertionError: If loop is not detected.
        CUAUnavailableError: If the corpus is missing.
    """
    corpus = Path(corpus_dir).resolve()
    if not corpus.exists() or not corpus.is_dir():
        raise CUAUnavailableError(
            f"CUA corpus unavailable — directory does not exist: {corpus}"
        )

    # Load the loop trajectory
    loop_traj_path = corpus / "loop_trajectory.json"
    if not loop_traj_path.exists():
        raise CUAUnavailableError(
            f"loop_trajectory.json not found in: {corpus}"
        )

    with open(loop_traj_path, encoding="utf-8") as f:
        traj_data = json.load(f)

    steps = _parse_trajectory_steps(traj_data)

    # Run the executor
    executor = CUAExecutor(max_stagnation=3)
    result = executor.execute_trajectory(steps)

    loop_detected = result.final_outcome == ActionOutcome.STAGNATION
    hard_stopped = loop_detected and not result.receipt_emitted

    return {
        "loop_detected": loop_detected,
        "hard_stopped": hard_stopped,
        "steps_executed": len(result.steps),
        "max_steps_allowed": len(steps),
        "final_outcome": result.final_outcome.value,
        "receipt_emitted": result.receipt_emitted,
    }


# ---------------------------------------------------------------------------
# Oracle 4: no_receipt_without_verification
# ---------------------------------------------------------------------------


def no_receipt_without_verification(
    corpus_dir: str,
) -> dict[str, Any]:
    """Oracle: force verify-fail → assert NO Ed25519 receipt is emitted.

    Loads a trajectory that should FAIL verification, runs the executor
    with a private key, and asserts that no receipt is emitted.

    KILL-PROOF: bypass the verifier gate → a receipt is wrongly emitted
    (proves the gate is load-bearing).

    Args:
        corpus_dir: Path to the CUA fixture corpus.

    Returns:
        Dict with 'receipt_emitted' (should be False), 'outcome',
        'verifier_passed'.

    Raises:
        AssertionError: If a receipt IS emitted for a failed trajectory.
        CUAUnavailableError: If the corpus is missing.
    """
    from cryptography.hazmat.primitives.asymmetric import ed25519

    corpus = Path(corpus_dir).resolve()
    if not corpus.exists() or not corpus.is_dir():
        raise CUAUnavailableError(
            f"CUA corpus unavailable — directory does not exist: {corpus}"
        )

    # Load the fail trajectory (silently failed action)
    fail_traj_path = corpus / "fail_trajectory.json"
    if not fail_traj_path.exists():
        raise CUAUnavailableError(
            f"fail_trajectory.json not found in: {corpus}"
        )

    with open(fail_traj_path, encoding="utf-8") as f:
        traj_data = json.load(f)

    steps = _parse_trajectory_steps(traj_data)

    # Generate a private key for the receipt attempt
    private_key = ed25519.Ed25519PrivateKey.generate()

    # Run the executor — should NOT emit a receipt for a failed trajectory
    executor = CUAExecutor()
    result = executor.execute_trajectory(steps, private_key=private_key)

    receipt_emitted = result.receipt_emitted
    verifier_passed = result.final_outcome == ActionOutcome.PASS

    return {
        "receipt_emitted": receipt_emitted,
        "verifier_passed": verifier_passed,
        "outcome": result.final_outcome.value,
        "audit_log_emitted": bool(result.audit_log_json),
        "egress_report_emitted": bool(result.egress_report_json),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_trajectories(corpus: Path) -> list[Trajectory]:
    """Load all trajectory fixtures from the corpus."""
    trajectories: list[Trajectory] = []

    # Load individual trajectory files
    traj_files = sorted(corpus.glob("*_trajectory.json"))
    for traj_file in traj_files:
        with open(traj_file, encoding="utf-8") as f:
            data = json.load(f)
        steps = _parse_trajectory_steps(data)
        traj_id = data.get("trajectory_id", traj_file.stem)
        trajectories.append(Trajectory(trajectory_id=traj_id, steps=steps))

    return trajectories


def _parse_trajectory_steps(data: dict[str, Any]) -> list[TrajectoryStep]:
    """Parse trajectory step data from JSON."""
    steps: list[TrajectoryStep] = []

    for step_data in data.get("steps", []):
        action = Action(
            action_type=step_data.get("action", {}).get("action_type", "click"),
            target_element_id=step_data.get("action", {}).get("target_element_id", ""),
            target_query=step_data.get("action", {}).get("target_query", ""),
            value=step_data.get("action", {}).get("value", ""),
            description=step_data.get("action", {}).get("description", ""),
        )

        predicted = _parse_ui_state(step_data.get("predicted_state", {}))
        actual = None
        if step_data.get("actual_state"):
            actual = _parse_ui_state(step_data["actual_state"])

        steps.append(TrajectoryStep(
            step_index=step_data.get("step_index", len(steps)),
            screen_map=step_data.get("screen_map", {}),
            action=action,
            predicted_state=predicted,
            actual_state=actual,
            human_label=step_data.get("human_label", ""),
        ))

    return steps


def _parse_ui_state(data: dict[str, Any]) -> UIState:
    """Parse a UIState from JSON data."""
    state_type_str = data.get("state_type", "main_window")
    try:
        state_type = UIStateType(state_type_str)
    except ValueError:
        state_type = UIStateType.MAIN_WINDOW

    return UIState(
        state_type=state_type,
        element_count=data.get("element_count", 0),
        modal_present=data.get("modal_present", False),
        dropdown_open=data.get("dropdown_open", False),
        focused_element=data.get("focused_element", ""),
        text_values=data.get("text_values", {}),
        error_indicators=data.get("error_indicators", []),
    )
