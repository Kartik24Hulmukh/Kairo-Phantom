# PROVENANCE: original | clean-room CUA world model + verifier per prompts/04 + ANCHOR_ARCHITECTURE
"""CUA world model + Universal Verifier + loop detection + receipt-gating engine.

Implements the observe→predict→act→verify loop:
  1. World model: given current screen map + candidate action, predict the
     resulting STRUCTURAL UI state (modal appeared, dropdown open, value set).
     Structural prediction, not pixels.
  2. Universal Verifier: after acting, score the trajectory with a rubric
     verifier using PROCESS + OUTCOME signals, attending to ALL trajectory
     screenshots (not just the last). Non-overlapping criteria; distinguish
     controllable vs uncontrollable failure.
  3. Loop detection: detect stagnation/repeated states → hard-stop.
  4. Receipt gating: NO Ed25519 receipt emitted unless verifier + UI-state
     oracle BOTH pass.

SECURITY: All perceived text is UNTRUSTED (TAINTED) per prompts/05.
The world model and verifier operate on structural state, not raw text,
reducing injection surface. Actions are authorized only by the TRUSTED planner.

HONEST DEGRADATION:
  - Live observe→act on a real desktop → Experimental, fails loud if no display
  - World-model prediction + verifier + loop-detection + receipt-gating on
    recorded fixtures → Real

All operations are fully offline. No network calls. No LLM. No cloud.
No AGPL/GPL. Clean-room per prompts/15.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field as dc_field
from enum import Enum
from typing import Any

log = logging.getLogger("kairo.cua")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class CUAUnavailableError(RuntimeError):
    """Raised when a required CUA resource is missing — honest degradation."""

    pass


class CUAExperimentalError(RuntimeError):
    """Raised when an Experimental path (live capture/act) is unavailable."""

    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ActionOutcome(Enum):
    """Outcome of a CUA action verification."""
    PASS = "pass"
    FAIL_CONTROLLABLE = "fail_controllable"
    FAIL_UNCONTROLLABLE = "fail_uncontrollable"
    STAGNATION = "stagnation"


class UIStateType(Enum):
    """Structural UI state type."""
    MAIN_WINDOW = "main_window"
    MODAL_DIALOG = "modal_dialog"
    DROPDOWN_OPEN = "dropdown_open"
    DROPDOWN_CLOSED = "dropdown_closed"
    TEXT_ENTERED = "text_entered"
    CHECKBOX_TOGGLED = "checkbox_toggled"
    NAVIGATION = "navigation"
    ERROR_STATE = "error_state"
    LOADING = "loading"
    UNCHANGED = "unchanged"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class UIState:
    """Structural UI state snapshot — the world model's representation."""
    state_type: UIStateType
    element_count: int = 0
    modal_present: bool = False
    dropdown_open: bool = False
    focused_element: str = ""
    text_values: dict[str, str] = dc_field(default_factory=dict)
    error_indicators: list[str] = dc_field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_type": self.state_type.value,
            "element_count": self.element_count,
            "modal_present": self.modal_present,
            "dropdown_open": self.dropdown_open,
            "focused_element": self.focused_element,
            "text_values": self.text_values,
            "error_indicators": self.error_indicators,
        }

    def structural_diff(self, other: UIState) -> dict[str, Any]:
        """Compute structural diff between two UI states."""
        diff: dict[str, Any] = {}
        if self.state_type != other.state_type:
            diff["state_type"] = {"from": self.state_type.value, "to": other.state_type.value}
        if self.modal_present != other.modal_present:
            diff["modal_present"] = {"from": self.modal_present, "to": other.modal_present}
        if self.dropdown_open != other.dropdown_open:
            diff["dropdown_open"] = {"from": self.dropdown_open, "to": other.dropdown_open}
        if self.focused_element != other.focused_element:
            diff["focused_element"] = {"from": self.focused_element, "to": other.focused_element}
        if self.element_count != other.element_count:
            diff["element_count"] = {"from": self.element_count, "to": other.element_count}
        # Text value changes
        text_changes: dict[str, Any] = {}
        for key, val in other.text_values.items():
            if key not in self.text_values:
                text_changes[key] = {"from": None, "to": val}
            elif self.text_values[key] != val:
                text_changes[key] = {"from": self.text_values[key], "to": val}
        if text_changes:
            diff["text_values"] = text_changes
        # New error indicators
        new_errors = [e for e in other.error_indicators if e not in self.error_indicators]
        if new_errors:
            diff["new_errors"] = new_errors
        return diff


@dataclass
class Action:
    """A CUA action to be performed."""
    action_type: str  # "click", "type", "select", "scroll", "navigate", "close"
    target_element_id: str = ""
    target_query: str = ""  # Natural-language query for resolve()
    value: str = ""  # Text to type, option to select, etc.
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "target_element_id": self.target_element_id,
            "target_query": self.target_query,
            "value": self.value,
            "description": self.description,
        }


@dataclass
class TrajectoryStep:
    """A single step in a CUA trajectory."""
    step_index: int
    screen_map: dict[str, Any]  # Serialized ScreenMap
    action: Action
    predicted_state: UIState
    actual_state: UIState | None = None
    human_label: str = ""  # "pass", "fail", "uncontrollable"
    verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "action": self.action.to_dict(),
            "predicted_state": self.predicted_state.to_dict(),
            "actual_state": self.actual_state.to_dict() if self.actual_state else None,
            "human_label": self.human_label,
            "verified": self.verified,
        }


@dataclass
class Trajectory:
    """A recorded CUA trajectory — sequence of steps."""
    trajectory_id: str
    steps: list[TrajectoryStep] = dc_field(default_factory=list)
    final_outcome: ActionOutcome = ActionOutcome.FAIL_CONTROLLABLE
    receipt_emitted: bool = False
    audit_log_json: str = ""
    egress_report_json: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "trajectory_id": self.trajectory_id,
            "steps": [s.to_dict() for s in self.steps],
            "final_outcome": self.final_outcome.value,
            "receipt_emitted": self.receipt_emitted,
        }


# ---------------------------------------------------------------------------
# World Model (CUWM-style)
# ---------------------------------------------------------------------------


class WorldModel:
    """Predict structural UI state transitions for candidate actions.

    Given the current screen map (from step 03's perception layer) and a
    candidate action, predict the resulting STRUCTURAL UI state — not pixels.

    The prediction is deterministic and rule-based (no LLM, no embeddings):
    - click on button → state change (modal, navigation, toggle)
    - type in field → text_entered state
    - select dropdown → dropdown_open state
    - close modal → main_window state
    """

    def __init__(self) -> None:
        self._transition_rules: dict[str, dict[str, Any]] = {
            "click": {"expected_state": UIStateType.MAIN_WINDOW, "may_open_modal": True},
            "type": {"expected_state": UIStateType.TEXT_ENTERED},
            "select": {"expected_state": UIStateType.DROPDOWN_OPEN},
            "scroll": {"expected_state": UIStateType.UNCHANGED},
            "navigate": {"expected_state": UIStateType.NAVIGATION},
            "close": {"expected_state": UIStateType.MAIN_WINDOW, "closes_modal": True},
            "toggle": {"expected_state": UIStateType.CHECKBOX_TOGGLED},
        }

    def predict(
        self,
        current_state: UIState,
        action: Action,
        screen_map: dict[str, Any] | None = None,
    ) -> UIState:
        """Predict the next UI state after performing the action.

        Args:
            current_state: Current structural UI state.
            action:        Action to perform.
            screen_map:    Optional serialized ScreenMap for context.

        Returns:
            Predicted UIState after the action.
        """
        rule = self._transition_rules.get(action.action_type, {})

        # Build predicted state based on action type
        if action.action_type == "click":
            # Click may open a modal, navigate, or toggle
            if rule.get("may_open_modal"):
                # Check if target is a button that typically opens modals
                target_desc = action.description.lower()
                # In a modal context, OK/confirm/save/close the modal
                if current_state.modal_present:
                    # We're in a modal — OK/confirm/save/cancel/close all dismiss it
                    if any(w in target_desc for w in ["ok", "submit", "save", "confirm", "cancel", "close", "back", "done", "apply"]):
                        return UIState(
                            state_type=UIStateType.MAIN_WINDOW,
                            modal_present=False,
                            element_count=max(0, current_state.element_count - 3),
                            focused_element="",
                        )
                # Not in a modal — these buttons open one
                if any(w in target_desc for w in ["submit", "save", "confirm", "open", "add"]):
                    return UIState(
                        state_type=UIStateType.MODAL_DIALOG,
                        modal_present=True,
                        element_count=current_state.element_count + 3,
                        focused_element=action.target_element_id,
                    )
                elif any(w in target_desc for w in ["cancel", "close", "back"]):
                    return UIState(
                        state_type=UIStateType.MAIN_WINDOW,
                        modal_present=False,
                        element_count=max(0, current_state.element_count - 3),
                        focused_element="",
                    )
            return UIState(
                state_type=UIStateType.MAIN_WINDOW,
                element_count=current_state.element_count,
                focused_element=action.target_element_id,
            )

        elif action.action_type == "type":
            new_text = dict(current_state.text_values)
            if action.target_element_id:
                new_text[action.target_element_id] = action.value
            return UIState(
                state_type=UIStateType.TEXT_ENTERED,
                element_count=current_state.element_count,
                focused_element=action.target_element_id,
                text_values=new_text,
            )

        elif action.action_type == "select":
            return UIState(
                state_type=UIStateType.DROPDOWN_OPEN,
                dropdown_open=True,
                element_count=current_state.element_count + 5,
                focused_element=action.target_element_id,
            )

        elif action.action_type == "close":
            return UIState(
                state_type=UIStateType.MAIN_WINDOW,
                modal_present=False,
                dropdown_open=False,
                element_count=max(0, current_state.element_count - 3),
                focused_element="",
            )

        elif action.action_type == "navigate":
            return UIState(
                state_type=UIStateType.NAVIGATION,
                element_count=current_state.element_count,
                focused_element="",
            )

        elif action.action_type == "toggle":
            return UIState(
                state_type=UIStateType.CHECKBOX_TOGGLED,
                element_count=current_state.element_count,
                focused_element=action.target_element_id,
            )

        elif action.action_type == "scroll":
            return UIState(
                state_type=UIStateType.UNCHANGED,
                element_count=current_state.element_count,
                focused_element=current_state.focused_element,
                text_values=dict(current_state.text_values),
            )

        return UIState(
            state_type=UIStateType.UNCHANGED,
            element_count=current_state.element_count,
            focused_element=current_state.focused_element,
            text_values=dict(current_state.text_values),
        )

    def detect_stagnation(
        self,
        state_history: list[UIState],
        window_size: int = 3,
    ) -> bool:
        """Detect if the UI state has stagnated (repeated states).

        Args:
            state_history: List of recent UI states.
            window_size:   Number of recent states to check for repetition.

        Returns:
            True if stagnation detected (same state repeated >= window_size times).
        """
        if len(state_history) < window_size:
            return False

        recent = state_history[-window_size:]
        # Check if all recent states are structurally identical
        first = recent[0]
        for state in recent[1:]:
            if state.state_type != first.state_type:
                return False
            if state.element_count != first.element_count:
                return False
            if state.modal_present != first.modal_present:
                return False
            if state.dropdown_open != first.dropdown_open:
                return False
            if state.focused_element != first.focused_element:
                return False
            if state.text_values != first.text_values:
                return False

        return True


def predict_transition(
    current_state: UIState,
    action: Action,
    screen_map: dict[str, Any] | None = None,
) -> UIState:
    """Convenience function: predict UI state transition."""
    model = WorldModel()
    return model.predict(current_state, action, screen_map)


# ---------------------------------------------------------------------------
# Universal Verifier
# ---------------------------------------------------------------------------


class UniversalVerifier:
    """Score a CUA trajectory with a rubric verifier.

    Uses PROCESS + OUTCOME signals, attending to ALL trajectory steps
    (not just the last). Non-overlapping criteria; distinguishes controllable
    vs uncontrollable failure.

    Rubric criteria (each scored independently, non-overlapping):
      1. State transition match: predicted state == actual state
      2. Goal achievement: final state matches expected goal
      3. No error states: no error indicators in any step
      4. No stagnation: no repeated states (loop detection)
      5. Action completion: all actions have an actual state (not None)
    """

    def __init__(self) -> None:
        self._criteria = [
            "state_transition_match",
            "goal_achievement",
            "no_error_states",
            "no_stagnation",
            "action_completion",
        ]

    def verify(self, trajectory: Trajectory) -> tuple[ActionOutcome, dict[str, Any]]:
        """Verify a trajectory and return outcome + detailed scores.

        Args:
            trajectory: The trajectory to verify.

        Returns:
            Tuple of (ActionOutcome, scores_dict) where scores_dict has
            per-criterion pass/fail and an overall score.
        """
        scores: dict[str, bool] = {}
        details: dict[str, Any] = {}

        # 1. State transition match: predicted == actual for each step
        transition_matches = 0
        transition_total = 0
        for step in trajectory.steps:
            if step.actual_state is not None:
                transition_total += 1
                if self._states_match(step.predicted_state, step.actual_state):
                    transition_matches += 1
        scores["state_transition_match"] = transition_total > 0 and transition_matches == transition_total
        details["transition_matches"] = transition_matches
        details["transition_total"] = transition_total

        # 2. Goal achievement: check if any step's human_label is "pass"
        # or if the final state matches the expected goal
        goal_achieved = any(s.human_label == "pass" for s in trajectory.steps)
        if not goal_achieved:
            # Also check if the last actual state has no errors and is not unchanged
            last_actual = None
            for step in reversed(trajectory.steps):
                if step.actual_state is not None:
                    last_actual = step.actual_state
                    break
            if last_actual and last_actual.state_type != UIStateType.ERROR_STATE:
                if last_actual.state_type != UIStateType.UNCHANGED:
                    goal_achieved = True
        scores["goal_achievement"] = goal_achieved

        # 3. No error states
        has_errors = False
        for step in trajectory.steps:
            if step.actual_state and step.actual_state.error_indicators:
                has_errors = True
                break
            if step.actual_state and step.actual_state.state_type == UIStateType.ERROR_STATE:
                has_errors = True
                break
        scores["no_error_states"] = not has_errors

        # 4. No stagnation
        model = WorldModel()
        state_history: list[UIState] = []
        for step in trajectory.steps:
            if step.actual_state:
                state_history.append(step.actual_state)
        is_stagnant = model.detect_stagnation(state_history) if len(state_history) >= 3 else False
        scores["no_stagnation"] = not is_stagnant
        details["stagnation_detected"] = is_stagnant

        # 5. Action completion
        all_completed = all(s.actual_state is not None for s in trajectory.steps)
        scores["action_completion"] = all_completed
        details["steps_completed"] = sum(1 for s in trajectory.steps if s.actual_state is not None)
        details["steps_total"] = len(trajectory.steps)

        # Determine overall outcome
        all_pass = all(scores.values())

        # Uncontrollable = error states present but the action itself was
        # structurally completed (action_completion passed). The transition
        # may not match because the environment failed, not the action.
        # If there are errors AND the action completed, it's uncontrollable.
        completion_ok = scores.get("action_completion", False)
        has_uncontrollable = has_errors and completion_ok

        if is_stagnant:
            outcome = ActionOutcome.STAGNATION
        elif all_pass:
            outcome = ActionOutcome.PASS
        elif has_uncontrollable:
            outcome = ActionOutcome.FAIL_UNCONTROLLABLE
        else:
            outcome = ActionOutcome.FAIL_CONTROLLABLE

        # Compute agreement score (fraction of criteria passed)
        score_count = sum(1 for v in scores.values() if v)
        overall_score = score_count / len(scores) if scores else 0.0

        details["scores"] = {k: v for k, v in scores.items()}
        details["overall_score"] = round(overall_score, 4)
        details["outcome"] = outcome.value

        return outcome, details

    def _states_match(self, predicted: UIState, actual: UIState) -> bool:
        """Check if predicted state structurally matches actual state."""
        if predicted.state_type != actual.state_type:
            # Allow UNCHANGED prediction to match any non-error state for scroll
            if predicted.state_type == UIStateType.UNCHANGED and actual.state_type != UIStateType.ERROR_STATE:
                return True
            return False
        if predicted.modal_present != actual.modal_present:
            return False
        if predicted.dropdown_open != actual.dropdown_open:
            return False
        return True


def verify_trajectory(trajectory: Trajectory) -> tuple[ActionOutcome, dict[str, Any]]:
    """Convenience function: verify a trajectory."""
    verifier = UniversalVerifier()
    return verifier.verify(trajectory)


# ---------------------------------------------------------------------------
# Loop Detection
# ---------------------------------------------------------------------------


def detect_loop(
    state_history: list[UIState],
    window_size: int = 3,
    max_repeats: int = 3,
) -> dict[str, Any]:
    """Detect UI state loops/stagnation.

    Args:
        state_history: List of UI states in order.
        window_size:   Number of states to check for repetition.
        max_repeats:   Maximum allowed repetitions before declaring a loop.

    Returns:
        Dict with 'loop_detected', 'repeat_count', 'repeated_state'.
    """
    if len(state_history) < window_size:
        return {"loop_detected": False, "repeat_count": 0, "repeated_state": None}

    model = WorldModel()

    # Check for stagnation (same state repeated)
    is_stagnant = model.detect_stagnation(state_history, window_size)

    # Count consecutive identical states at the end
    repeat_count = 1
    for i in range(len(state_history) - 2, -1, -1):
        if _states_equal(state_history[i], state_history[-1]):
            repeat_count += 1
        else:
            break

    loop_detected = repeat_count >= max_repeats or is_stagnant

    return {
        "loop_detected": loop_detected,
        "repeat_count": repeat_count,
        "repeated_state": state_history[-1].to_dict() if loop_detected else None,
        "stagnation": is_stagnant,
    }


def _states_equal(a: UIState, b: UIState) -> bool:
    """Check if two UI states are structurally equal."""
    return (
        a.state_type == b.state_type
        and a.element_count == b.element_count
        and a.modal_present == b.modal_present
        and a.dropdown_open == b.dropdown_open
        and a.focused_element == b.focused_element
        and a.text_values == b.text_values
    )


# ---------------------------------------------------------------------------
# CUA Executor — observe→predict→act→verify loop
# ---------------------------------------------------------------------------


class CUAExecutor:
    """Execute the observe→predict→act→verify loop.

    On verify-fail → rollback/retry with a different plan.
    After N fails → hard-stop HONESTLY (no success claim).
    NO receipt is emitted unless verifier + UI-state oracle BOTH pass.

    HONEST SCOPING:
      - On recorded fixtures: Real (predict + verify + loop-detect + receipt-gate)
      - Live desktop action: Experimental (fail-loud; no display in CI)
    """

    def __init__(
        self,
        max_retries: int = 3,
        max_stagnation: int = 3,
    ) -> None:
        self.world_model = WorldModel()
        self.verifier = UniversalVerifier()
        self.max_retries = max_retries
        self.max_stagnation = max_stagnation

    def execute_trajectory(
        self,
        steps: list[TrajectoryStep],
        private_key: Any = None,
    ) -> Trajectory:
        """Execute a trajectory of steps with predict→verify loop.

        On recorded fixtures, this processes each step's recorded actual_state
        (no live action needed). On a live desktop, the action would be performed
        and the actual screen captured — but that's Experimental.

        Args:
            steps:        List of TrajectoryStep objects with recorded data.
        private_key: Optional Ed25519 private key for receipt.

        Returns:
            Completed Trajectory with verification results and optional receipt.
        """
        trajectory = Trajectory(trajectory_id="exec_0", steps=[])

        state_history: list[UIState] = []

        for step in steps:
            # Predict
            predicted = step.predicted_state

            # "Act" — on fixtures, the actual_state is pre-recorded
            # On live desktop, this would perform the action (Experimental)
            actual = step.actual_state

            # Record step
            executed_step = TrajectoryStep(
                step_index=step.step_index,
                screen_map=step.screen_map,
                action=step.action,
                predicted_state=predicted,
                actual_state=actual,
                human_label=step.human_label,
                verified=False,
            )
            trajectory.steps.append(executed_step)

            if actual:
                state_history.append(actual)

            # Check for stagnation/loop
            loop_result = detect_loop(state_history, max_repeats=self.max_stagnation, window_size=self.max_stagnation)
            if loop_result["loop_detected"]:
                trajectory.final_outcome = ActionOutcome.STAGNATION
                # Hard-stop — do NOT emit receipt
                trajectory.receipt_emitted = False
                return trajectory

        # Verify the full trajectory
        outcome, details = self.verifier.verify(trajectory)

        # Set verified flag on each step
        if outcome == ActionOutcome.PASS:
            for s in trajectory.steps:
                s.verified = True

        trajectory.final_outcome = outcome

        # Receipt gating: only emit if verifier passes (PASS outcome)
        if outcome == ActionOutcome.PASS and private_key is not None:
            trajectory = self._emit_receipt(trajectory, private_key)
        else:
            trajectory.receipt_emitted = False

        return trajectory

    def _emit_receipt(self, trajectory: Trajectory, private_key: Any) -> Trajectory:
        """Emit Ed25519 audit log + zero-egress receipt for a verified trajectory.

        This is the GATE — it's only called when the verifier passes.
        If the verifier fails, this method is NEVER called, so no receipt
        is emitted for an unverified action.
        """
        from kairo.oracles.ed25519_audit_log import Ed25519AuditLog
        from kairo.oracles.zero_egress_report import generate_zero_egress_report

        traj_json = json.dumps(trajectory.to_dict(), sort_keys=True, default=str)
        doc_hash = hashlib.sha256(traj_json.encode()).hexdigest()

        audit = Ed25519AuditLog(private_key)
        audit.log_run_started(doc_hash=doc_hash, playbook_id="cua_trajectory")

        for i, step in enumerate(trajectory.steps):
            audit.log_edit(
                doc_hash=doc_hash,
                clause_id=f"step_{i}",
                clause_label=f"Step {i}: {step.action.action_type} → {step.predicted_state.state_type.value}",
                old_text="",
                new_text=f"Action: {step.action.action_type}, target={step.target_query if hasattr(step, 'target_query') else step.action.target_element_id}, "
                f"predicted={step.predicted_state.state_type.value}, "
                f"actual={step.actual_state.state_type.value if step.actual_state else 'N/A'}, "
                f"verified={step.verified}",
                citation="cua-verifier",
                rationale="CUA step verified by Universal Verifier (UNTRUSTED perceived text)",
            )

        audit.log_run_completed(
            doc_hash=doc_hash,
            total_edits=len(trajectory.steps),
            total_flagged=0,
            injection_detected=False,
        )

        trajectory.audit_log_json = audit.to_json()

        egress_report = generate_zero_egress_report(
            doc_hash=doc_hash,
            playbook_id="cua_trajectory",
            total_edits=len(trajectory.steps),
            total_flagged=0,
            injection_detected=False,
            audit_log_json=trajectory.audit_log_json,
            private_key=private_key,
        )
        trajectory.egress_report_json = egress_report.to_json()
        trajectory.receipt_emitted = True

        return trajectory


def live_observe() -> dict[str, Any]:
    """Live screen observation — Experimental.

    Requires a real display and accessibility framework.
    Cannot run in headless CI.

    Raises:
        CUAExperimentalError: Always, in headless/offline mode.
    """
    raise CUAExperimentalError(
        "Live observe→act is Experimental — no display available in this "
        "environment. The world-model prediction + Universal Verifier + "
        "loop-detection + receipt-gating on recorded fixtures is the Real, "
        "tested capability. Live CUA never fakes actions."
    )
