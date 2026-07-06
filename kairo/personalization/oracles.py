# PROVENANCE: original | clean-room personalization oracles per VERIFICATION_ORACLES.md
"""On-device style personalization oracles — deterministic, kill-proven.

Implements four automatable oracles:

  1. ``air_gap_train_infer`` — during a minimal end-to-end train+infer on a
     tiny fixture model/dataset, the egress oracle asserts 0 outbound.
     KILL-PROOF: attempt a socket → fails.

  2. ``adapter_roundtrip`` — train a tiny adapter, save, reload, and it
     measurably shifts output toward the fixture style vs baseline.
     KILL-PROOF: load a null/empty adapter → no shift.

  3. ``feedback_signal`` — accept/edit/reject correctly become +/correction/-
     training pairs. KILL-PROOF: mislabel → assertion fails.

  4. ``drift_alarm`` — a simulated preference drop below tolerance triggers
     the alarm.

All oracles are KILL-PROVEN. All operations are fully offline.
No AGPL/GPL. Clean-room per specs/CLEANROOM_IP_PROTOCOL.md.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any

from kairo.personalization.engine import (
    FeedbackCollector,
    PersonalizationError,
    StyleAdapter,
    TinyNGramModel,
    check_drift,
    load_adapter,
    personalization_pipeline,
    save_adapter,
    train_adapter,
)


# ---------------------------------------------------------------------------
# Oracle 1: air_gap_train_infer
# ---------------------------------------------------------------------------


def air_gap_train_infer(
    baseline_texts: list[str],
    user_texts: list[str],
) -> bool:
    """Oracle: train+infer under egress interception → assert 0 outbound.

    KILL-PROOF: attempt a socket → the egress interceptor catches it and
    the oracle FAILS.

    Args:
        baseline_texts: Texts to train the baseline model.
        user_texts:     User's writing samples.

    Returns:
        True if the train+infer cycle completes with 0 egress attempts.

    Raises:
        AssertionError: If any egress attempt is detected.
        PersonalizationError: If the pipeline fails.
    """
    from kairo.oracles.airgap_egress import SocketEgressInterceptor

    with SocketEgressInterceptor() as interceptor:
        with tempfile.TemporaryDirectory() as tmp:
            adapter_path = os.path.join(tmp, "test_adapter.json")
            result = personalization_pipeline(
                baseline_texts=baseline_texts,
                user_texts=user_texts,
                adapter_path=adapter_path,
            )

            if not result.ok:
                raise PersonalizationError(f"Pipeline failed: {result.error}")

            # Assert zero egress
            if interceptor.attempts:
                raise AssertionError(
                    f"air_gap_train_infer FAILED: {len(interceptor.attempts)} "
                    f"egress attempts detected during train+infer:\n"
                    f"{[a.target for a in interceptor.attempts]}"
                )

            if interceptor.dns_lookups:
                raise AssertionError(
                    f"air_gap_train_infer FAILED: {len(interceptor.dns_lookups)} "
                    f"DNS lookups detected during train+infer"
                )

    return True


# ---------------------------------------------------------------------------
# Oracle 2: adapter_roundtrip
# ---------------------------------------------------------------------------


def adapter_roundtrip(
    baseline_texts: list[str],
    user_texts: list[str],
    tmpdir: str | None = None,
) -> dict[str, Any]:
    """Oracle: train adapter → save → reload → measurable style shift.

    KILL-PROOF: load a null/empty adapter → no shift (shift ≈ 0).

    Args:
        baseline_texts: Texts to train the baseline model.
        user_texts:     User's writing samples for adapter training.
        tmpdir:         Optional temp directory for adapter file.

    Returns:
        Dict with:
          - adapter_id: The trained adapter's ID.
          - style_shift: Distribution distance between baseline and adapted.
          - baseline_output: Sample output from baseline model.
          - adapted_output: Sample output from adapted model.
          - roundtrip_ok: True if save→reload preserves adapter.

    Raises:
        AssertionError: If adapter round-trip fails or no style shift.
    """
    # Train baseline
    baseline_model = TinyNGramModel(n=2)
    baseline_model.train(baseline_texts)

    # Train adapter
    adapter = train_adapter(baseline_model, user_texts)

    # Save and reload
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = tmpdir or tmp
        adapter_path = os.path.join(tmp_dir, "adapter.json")
        save_adapter(adapter, adapter_path)
        loaded = load_adapter(adapter_path)

        # Verify round-trip
        assert loaded.adapter_id == adapter.adapter_id, (
            f"adapter_roundtrip FAILED: adapter ID mismatch "
            f"({loaded.adapter_id} != {adapter.adapter_id})"
        )
        assert (
            loaded.weight_deltas == adapter.weight_deltas
        ), "adapter_roundtrip FAILED: weight deltas mismatch after reload"

    # Apply adapter and measure shift
    adapted_model = baseline_model.apply_adapter(adapter)
    style_shift = baseline_model.distribution_distance(adapted_model)

    # Generate sample outputs
    test_prompt = "the"
    baseline_output = baseline_model.generate(test_prompt, seed=42)
    adapted_output = adapted_model.generate(test_prompt, seed=42)

    # Assert measurable shift (must be > 0 for a real adapter)
    assert style_shift > 0, (
        f"adapter_roundtrip FAILED: no style shift detected (shift={style_shift}). "
        f"Adapter did not measurably change the model's output distribution."
    )

    return {
        "adapter_id": adapter.adapter_id,
        "style_shift": style_shift,
        "baseline_output": baseline_output,
        "adapted_output": adapted_output,
        "roundtrip_ok": True,
        "weight_delta_count": len(adapter.weight_deltas),
    }


def adapter_roundtrip_null_kill_proof(
    baseline_texts: list[str],
) -> dict[str, Any]:
    """Kill-proof: load a null/empty adapter → no shift.

    This proves the style-shift check is load-bearing: if a null adapter
    produced a shift, the oracle would be meaningless.
    """
    baseline_model = TinyNGramModel(n=2)
    baseline_model.train(baseline_texts)

    null_adapter = StyleAdapter.empty()
    adapted_model = baseline_model.apply_adapter(null_adapter)
    style_shift = baseline_model.distribution_distance(adapted_model)

    # Null adapter MUST produce zero shift
    assert style_shift == 0, (
        f"adapter_roundtrip KILL-PROOF FAILED: null adapter produced "
        f"non-zero shift ({style_shift}). The oracle is not load-bearing!"
    )

    return {
        "adapter_id": "null",
        "style_shift": style_shift,
        "roundtrip_ok": True,
    }


# ---------------------------------------------------------------------------
# Oracle 3: feedback_signal
# ---------------------------------------------------------------------------


def feedback_signal(
    collector: FeedbackCollector,
) -> dict[str, Any]:
    """Oracle: accept/edit/reject correctly become +/correction/- training pairs.

    KILL-PROOF: mislabel a pair → assertion fails.

    Args:
        collector: A FeedbackCollector with recorded feedback.

    Returns:
        Dict with pair counts and training texts.

    Raises:
        AssertionError: If any pair is mislabeled.
    """
    pairs = collector.pairs

    for pair in pairs:
        if pair.feedback_type == "accept":
            assert (
                pair.label == 1
            ), f"feedback_signal FAILED: accept pair has label {pair.label} (expected 1)"
        elif pair.feedback_type == "edit":
            assert (
                pair.label == 0
            ), f"feedback_signal FAILED: edit pair has label {pair.label} (expected 0)"
            assert (
                pair.original
            ), "feedback_signal FAILED: edit pair has empty original text"
        elif pair.feedback_type == "reject":
            assert (
                pair.label == -1
            ), f"feedback_signal FAILED: reject pair has label {pair.label} (expected -1)"
        else:
            raise AssertionError(
                f"feedback_signal FAILED: unknown feedback type '{pair.feedback_type}'"
            )

    training_texts = collector.get_training_texts()

    return {
        "total_pairs": len(pairs),
        "positive_pairs": len(collector.positive_pairs),
        "correction_pairs": len(collector.correction_pairs),
        "negative_pairs": len(collector.negative_pairs),
        "training_texts_count": len(training_texts),
        "ok": True,
    }


# ---------------------------------------------------------------------------
# Oracle 4: drift_alarm
# ---------------------------------------------------------------------------


def drift_alarm(
    current_rate: float,
    prior_rate: float,
    tolerance: float = 0.10,
) -> dict[str, Any]:
    """Oracle: a simulated preference drop below tolerance triggers the alarm.

    KILL-PROOF: a rate above tolerance does NOT trigger the alarm.

    Args:
        current_rate: Current author-preference rate (0.0–1.0).
        prior_rate:   Prior release's preference rate.
        tolerance:    Allowed drop from prior rate.

    Returns:
        Dict with alarm status.

    Raises:
        AssertionError: If the alarm state is incorrect.
    """
    alarm = check_drift(current_rate, prior_rate, tolerance)

    threshold = prior_rate - tolerance
    expected_triggered = current_rate < threshold

    assert alarm.triggered == expected_triggered, (
        f"drift_alarm FAILED: alarm.triggered={alarm.triggered} "
        f"but expected={expected_triggered} "
        f"(current={current_rate}, prior={prior_rate}, tolerance={tolerance})"
    )

    return {
        "triggered": alarm.triggered,
        "current_rate": alarm.current_rate,
        "prior_rate": alarm.prior_rate,
        "tolerance": alarm.tolerance,
        "message": alarm.message,
        "ok": True,
    }
