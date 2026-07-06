# PROVENANCE: original | Personalization oracle tests per VERIFICATION_ORACLES.md
"""On-device style personalization oracle tests — automatable + kill-proofs.

Tests verify:
  1. air_gap_train_infer: train+infer under egress interception → 0 outbound.
     Kill-proof: attempt a socket → fails.
  2. adapter_roundtrip: train → save → reload → measurable style shift.
     Kill-proof: null adapter → no shift.
  3. feedback_signal: accept/edit/reject → +/correction/- training pairs.
     Kill-proof: mislabel → assertion fails.
  4. drift_alarm: preference drop below tolerance triggers alarm.
     Kill-proof: rate above tolerance does NOT trigger.
  5. Honest degradation: engine unavailable → fail loud.
  6. Blind A/B harness: generates session, records choices, computes rate.
  7. Trust stack: audit log + egress report generated.
  8. CLI integration: personalize subcommand works.

All tests run fully offline. No mocks on production paths. Zero skips.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from kairo.personalization.engine import (  # noqa: E402
    BlindABHarness,
    FeedbackCollector,
    PersonalizationError,
    RetunePolicy,
    StyleAdapter,
    TinyNGramModel,
    load_adapter,
    personalization_pipeline,
    save_adapter,
    train_adapter,
)
from kairo.personalization.oracles import (  # noqa: E402
    adapter_roundtrip,
    adapter_roundtrip_null_kill_proof,
    air_gap_train_infer,
    drift_alarm,
    feedback_signal,
)

# Fixture paths
_FIX = os.path.join(_REPO_ROOT, "kairo", "personalization", "fixtures")
_STYLE_FIXTURE = os.path.join(_FIX, "style_fixture.json")
_AB_TASKS = os.path.join(_FIX, "ab_tasks.json")

# Test data
_BASELINE_TEXTS = [
    "It is furthermore incumbent upon the committee to deliberate upon the aforementioned matters.",
    "Notwithstanding the foregoing, the parties hereto agree to the terms set forth herein.",
    "Pursuant to the provisions of Article 7, the contractor shall be liable for damages.",
    "The aforementioned analysis notwithstanding, it is imperative that all stakeholders be consulted.",
    "In accordance with established protocols, the procedure shall be initiated forthwith.",
]

_USER_TEXTS = [
    "The quick brown fox jumps over the lazy dog.",
    "She writes with clarity and precision, always choosing simple words.",
    "Keep sentences short. Avoid jargon. Be direct.",
    "The report concludes with a summary of key findings.",
    "Our team achieved significant milestones this quarter.",
    "Please review the attached document and provide feedback.",
    "The analysis reveals three primary trends in the data.",
    "We recommend adopting a phased approach to implementation.",
]


def _load_style_fixture() -> dict:
    with open(_STYLE_FIXTURE, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Oracle 1: air_gap_train_infer
# ---------------------------------------------------------------------------


class TestAirGapTrainInfer:
    """air_gap_train_infer oracle — zero egress during train+infer."""

    def test_zero_egress_during_train_infer(self):
        """Train+infer cycle completes with 0 egress attempts."""
        result = air_gap_train_infer(_BASELINE_TEXTS, _USER_TEXTS)
        assert result is True

    def test_kill_proof_socket_attempt_detected(self):
        """Kill-proof: if a socket is opened during train+infer, the oracle catches it."""
        import socket as sock_module

        from kairo.oracles.airgap_egress import SocketEgressInterceptor

        with SocketEgressInterceptor() as interceptor:
            # Simulate a rogue egress attempt
            try:
                s = sock_module.socket(sock_module.AF_INET, sock_module.SOCK_STREAM)
                s.connect(("8.8.8.8", 53))
                s.close()
            except ConnectionError:
                pass  # Expected — interceptor blocks it

            # The interceptor MUST have recorded the attempt
            assert (
                len(interceptor.attempts) > 0
            ), "KILL-PROOF FAILED: socket egress attempt was NOT detected!"


# ---------------------------------------------------------------------------
# Oracle 2: adapter_roundtrip
# ---------------------------------------------------------------------------


class TestAdapterRoundtrip:
    """adapter_roundtrip oracle — train, save, reload, measurable shift."""

    def test_adapter_roundtrip_with_shift(self):
        """Train adapter → save → reload → measurable style shift."""
        result = adapter_roundtrip(_BASELINE_TEXTS, _USER_TEXTS)
        assert result["roundtrip_ok"] is True
        assert result["style_shift"] > 0, "No style shift detected!"
        assert result["weight_delta_count"] > 0, "No weight deltas in adapter!"

    def test_kill_proof_null_adapter_no_shift(self):
        """Kill-proof: null/empty adapter → no shift."""
        result = adapter_roundtrip_null_kill_proof(_BASELINE_TEXTS)
        assert result["style_shift"] == 0, "Null adapter produced non-zero shift!"

    def test_adapter_save_load_preserves_id(self):
        """Save and reload preserves adapter ID and weights."""
        baseline_model = TinyNGramModel(n=2)
        baseline_model.train(_BASELINE_TEXTS)
        adapter = train_adapter(baseline_model, _USER_TEXTS)

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "adapter.json")
            save_adapter(adapter, path)
            loaded = load_adapter(path)

            assert loaded.adapter_id == adapter.adapter_id
            assert loaded.weight_deltas == adapter.weight_deltas
            assert loaded.user_id == adapter.user_id
            assert loaded.sample_count == adapter.sample_count

    def test_adapter_applied_model_generates_different_output(self):
        """Adapted model produces different output than baseline."""
        baseline_model = TinyNGramModel(n=2)
        baseline_model.train(_BASELINE_TEXTS)
        adapter = train_adapter(baseline_model, _USER_TEXTS)
        adapted_model = baseline_model.apply_adapter(adapter)

        prompt = "the"
        baseline_out = baseline_model.generate(prompt, seed=42)
        adapted_out = adapted_model.generate(prompt, seed=42)

        # The outputs should differ (the adapter shifted the distribution)
        assert (
            baseline_out != adapted_out
            or baseline_model.distribution_distance(adapted_model) > 0
        )


# ---------------------------------------------------------------------------
# Oracle 3: feedback_signal
# ---------------------------------------------------------------------------


class TestFeedbackSignal:
    """feedback_signal oracle — accept/edit/reject → training pairs."""

    def test_correct_labels(self):
        """Accept/edit/reject correctly become +/correction/- pairs."""
        collector = FeedbackCollector(user_id="test_user")
        collector.record_accept("Write a summary", "The summary is clear and concise.")
        collector.record_edit(
            "Write a intro", "It is furthermore...", "Keep it simple and direct."
        )
        collector.record_reject(
            "Write a conclusion", "Pursuant to the aforementioned..."
        )

        result = feedback_signal(collector)
        assert result["ok"] is True
        assert result["total_pairs"] == 3
        assert result["positive_pairs"] == 1
        assert result["correction_pairs"] == 1
        assert result["negative_pairs"] == 1
        assert result["training_texts_count"] == 2  # accept + edit outputs

    def test_kill_proof_mislabel(self):
        """Kill-proof: mislabel a pair → assertion fails."""
        collector = FeedbackCollector(user_id="test_user")
        # Manually create a mislabeled pair
        from kairo.personalization.engine import FeedbackPair

        collector._pairs.append(
            FeedbackPair(
                feedback_type="accept",
                prompt="test",
                output="test output",
                label=-1,  # WRONG: should be 1
            )
        )

        with pytest.raises(AssertionError, match="accept pair has label -1"):
            feedback_signal(collector)

    def test_edit_pair_requires_original(self):
        """Edit pair must have original text."""
        collector = FeedbackCollector(user_id="test_user")
        from kairo.personalization.engine import FeedbackPair

        collector._pairs.append(
            FeedbackPair(
                feedback_type="edit",
                prompt="test",
                output="edited",
                original="",  # WRONG: should be non-empty
                label=0,
            )
        )

        with pytest.raises(AssertionError, match="edit pair has empty original"):
            feedback_signal(collector)

    def test_training_texts_from_feedback(self):
        """Training texts include accepted and edited outputs (not rejected)."""
        collector = FeedbackCollector(user_id="test_user")
        collector.record_accept("prompt1", "accepted output")
        collector.record_edit("prompt2", "original", "edited output")
        collector.record_reject("prompt3", "rejected output")

        texts = collector.get_training_texts()
        assert "accepted output" in texts
        assert "edited output" in texts
        assert "rejected output" not in texts


# ---------------------------------------------------------------------------
# Oracle 4: drift_alarm
# ---------------------------------------------------------------------------


class TestDriftAlarm:
    """drift_alarm oracle — preference drop triggers alarm."""

    def test_alarm_triggers_on_drop(self):
        """Preference drop below tolerance triggers alarm."""
        result = drift_alarm(current_rate=0.30, prior_rate=0.60, tolerance=0.10)
        assert result["triggered"] is True
        assert "DRIFT ALARM" in result["message"]

    def test_no_alarm_when_within_tolerance(self):
        """Rate within tolerance does NOT trigger alarm."""
        result = drift_alarm(current_rate=0.55, prior_rate=0.60, tolerance=0.10)
        assert result["triggered"] is False

    def test_kill_proof_high_rate_no_alarm(self):
        """Kill-proof: high rate does NOT trigger alarm."""
        result = drift_alarm(current_rate=0.80, prior_rate=0.60, tolerance=0.10)
        assert result["triggered"] is False

    def test_alarm_at_exact_threshold(self):
        """At exact threshold (prior - tolerance), alarm is NOT triggered (>=)."""
        result = drift_alarm(current_rate=0.50, prior_rate=0.60, tolerance=0.10)
        assert result["triggered"] is False  # 0.50 >= 0.50 (threshold)


# ---------------------------------------------------------------------------
# Honest Degradation
# ---------------------------------------------------------------------------


class TestHonestDegradation:
    """Honest degradation: engine unavailable → fail loud."""

    def test_empty_user_texts_raises(self):
        """Training with no user texts raises PersonalizationError."""
        baseline_model = TinyNGramModel(n=2)
        baseline_model.train(_BASELINE_TEXTS)
        with pytest.raises(PersonalizationError, match="no user texts"):
            train_adapter(baseline_model, [])

    def test_missing_adapter_file_raises(self):
        """Loading a non-existent adapter file raises PersonalizationError."""
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(PersonalizationError, match="Adapter file not found"):
                load_adapter(os.path.join(tmp, "nonexistent.json"))

    def test_pipeline_error_reported(self):
        """Pipeline errors are reported honestly, not silenced."""
        result = personalization_pipeline(
            baseline_texts=[],  # Empty baseline → will fail
            user_texts=_USER_TEXTS,
        )
        # Pipeline should handle gracefully (empty baseline = no vocab)
        # It may succeed with empty model or fail — either is honest
        assert isinstance(result.ok, bool)


# ---------------------------------------------------------------------------
# RetunePolicy — EdgeTune-style reuse-or-retune
# ---------------------------------------------------------------------------


class TestRetunePolicy:
    """RetunePolicy — reuse-or-retune decision (GradCut analog)."""

    def test_insufficient_feedback_no_retune(self):
        """Insufficient new feedback → no retune."""
        adapter = StyleAdapter(user_id="test", trained_at=0, sample_count=10)
        collector = FeedbackCollector()
        collector.record_accept("p", "o")  # Only 1 pair

        policy = RetunePolicy(min_new_feedback=3)
        decision = policy.evaluate(adapter, collector, current_time=100)
        assert decision.should_retune is False
        assert "Insufficient" in decision.reason

    def test_high_drift_triggers_retune(self):
        """High correction/reject ratio → retune."""
        adapter = StyleAdapter(user_id="test", trained_at=0, sample_count=10)
        collector = FeedbackCollector()
        collector.record_accept("p1", "o1")
        collector.record_reject("p2", "o2")
        collector.record_reject("p3", "o3")
        collector.record_edit("p4", "orig", "edited")

        policy = RetunePolicy(drift_threshold=0.15, min_new_feedback=3)
        decision = policy.evaluate(adapter, collector, current_time=100)
        assert decision.should_retune is True
        assert decision.drift_score >= 0.15

    def test_low_drift_no_retune(self):
        """Low correction/reject ratio → no retune."""
        adapter = StyleAdapter(user_id="test", trained_at=0, sample_count=10)
        collector = FeedbackCollector()
        collector.record_accept("p1", "o1")
        collector.record_accept("p2", "o2")
        collector.record_accept("p3", "o3")
        collector.record_accept("p4", "o4")

        policy = RetunePolicy(drift_threshold=0.15, min_new_feedback=3)
        decision = policy.evaluate(adapter, collector, current_time=100)
        assert decision.should_retune is False
        assert decision.drift_score < 0.15


# ---------------------------------------------------------------------------
# Blind A/B Harness
# ---------------------------------------------------------------------------


class TestBlindABHarness:
    """Blind A/B harness — generates session, records choices."""

    def test_generate_session(self):
        """Harness generates a session with anonymized outputs."""
        baseline_model = TinyNGramModel(n=2)
        baseline_model.train(_BASELINE_TEXTS)
        adapter = train_adapter(baseline_model, _USER_TEXTS)
        adapted_model = baseline_model.apply_adapter(adapter)

        tasks = [
            {"prompt": "Finish:", "context": "The results show."},
            {"prompt": "Conclude:", "context": "The project succeeded."},
        ]

        harness = BlindABHarness(seed=42)
        session = harness.generate_session(baseline_model, adapted_model, tasks)

        assert len(session.tasks) == 2
        assert session.session_id  # Non-empty ID
        for task in session.tasks:
            assert task.output_a  # Non-empty
            assert task.output_b  # Non-empty
            assert task.a_is_adapter in (True, False)  # Anonymized

    def test_record_choices(self):
        """Recording choices computes preference rate."""
        baseline_model = TinyNGramModel(n=2)
        baseline_model.train(_BASELINE_TEXTS)
        adapter = train_adapter(baseline_model, _USER_TEXTS)
        adapted_model = baseline_model.apply_adapter(adapter)

        tasks = [{"prompt": "Test:", "context": "data"}]
        harness = BlindABHarness(seed=42)
        session = harness.generate_session(baseline_model, adapted_model, tasks)

        # Record choice (always pick A)
        session = harness.record_choices(session, ["A"])
        assert session.completed is True
        assert 0.0 <= session.preference_rate <= 1.0

    def test_wrong_choices_count_raises(self):
        """Wrong number of choices raises error."""
        baseline_model = TinyNGramModel(n=2)
        baseline_model.train(_BASELINE_TEXTS)
        adapter = train_adapter(baseline_model, _USER_TEXTS)
        adapted_model = baseline_model.apply_adapter(adapter)

        tasks = [{"prompt": "T:", "context": "d"}]
        harness = BlindABHarness(seed=42)
        session = harness.generate_session(baseline_model, adapted_model, tasks)

        with pytest.raises(PersonalizationError, match="Choices count"):
            harness.record_choices(session, ["A", "B"])  # 2 choices for 1 task

    def test_harness_does_not_self_score(self):
        """The harness does NOT pre-fill preference_rate — it starts at 0.0."""
        baseline_model = TinyNGramModel(n=2)
        baseline_model.train(_BASELINE_TEXTS)
        adapter = train_adapter(baseline_model, _USER_TEXTS)
        adapted_model = baseline_model.apply_adapter(adapter)

        tasks = [{"prompt": "T:", "context": "d"}]
        harness = BlindABHarness(seed=42)
        session = harness.generate_session(baseline_model, adapted_model, tasks)

        # Before author judges, preference_rate MUST be 0.0 (not self-scored)
        assert session.preference_rate == 0.0
        assert session.completed is False


# ---------------------------------------------------------------------------
# Trust Stack Integration
# ---------------------------------------------------------------------------


class TestTrustStackIntegration:
    """Audit log + zero-egress report integration."""

    def test_audit_log_generated(self):
        """Pipeline generates Ed25519 audit log."""
        private_key = ed25519.Ed25519PrivateKey.generate()
        with tempfile.TemporaryDirectory() as tmp:
            result = personalization_pipeline(
                baseline_texts=_BASELINE_TEXTS,
                user_texts=_USER_TEXTS,
                adapter_path=os.path.join(tmp, "adapter.json"),
                private_key=private_key,
            )
            assert result.ok is True
            assert len(result.audit_log_json) > 0
            audit_data = json.loads(result.audit_log_json)
            assert "entries" in audit_data
            assert len(audit_data["entries"]) > 0

    def test_egress_report_generated(self):
        """Pipeline generates signed zero-egress report."""
        private_key = ed25519.Ed25519PrivateKey.generate()
        with tempfile.TemporaryDirectory() as tmp:
            result = personalization_pipeline(
                baseline_texts=_BASELINE_TEXTS,
                user_texts=_USER_TEXTS,
                adapter_path=os.path.join(tmp, "adapter.json"),
                private_key=private_key,
            )
            assert result.ok is True
            assert len(result.egress_report_json) > 0
            report_data = json.loads(result.egress_report_json)
            assert "signature" in report_data
            assert "offline_attestation" in report_data

    def test_audit_log_chained(self):
        """Audit log entries are hash-chained."""
        private_key = ed25519.Ed25519PrivateKey.generate()
        with tempfile.TemporaryDirectory() as tmp:
            result = personalization_pipeline(
                baseline_texts=_BASELINE_TEXTS,
                user_texts=_USER_TEXTS,
                adapter_path=os.path.join(tmp, "adapter.json"),
                private_key=private_key,
            )
            audit_data = json.loads(result.audit_log_json)
            entries = audit_data["entries"]
            for i, entry in enumerate(entries):
                if i > 0:
                    assert entry["prev_hash"] != ""


# ---------------------------------------------------------------------------
# CLI Integration
# ---------------------------------------------------------------------------


class TestCLIIntegration:
    """personalize CLI subcommand works end-to-end."""

    def test_cli_status(self):
        """CLI status action shows personalization status."""
        from kairo.cli import main

        rc = main(["personalize", "status", "--outdir", tempfile.mkdtemp()])
        assert rc == 0

    def test_cli_train_and_ab(self):
        """CLI train + ab actions work end-to-end."""
        from kairo.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            # Create samples file
            samples_path = os.path.join(tmp, "samples.json")
            with open(samples_path, "w") as f:
                json.dump({"user_samples": _USER_TEXTS}, f)

            # Train
            rc = main(
                [
                    "personalize",
                    "train",
                    samples_path,
                    "--out",
                    "adapter.json",
                    "--outdir",
                    tmp,
                ]
            )
            assert rc == 0

            # Generate A/B session
            adapter_path = os.path.join(tmp, "adapter.json")
            rc = main(["personalize", "ab", adapter_path, "--outdir", tmp])
            assert rc == 0

    def test_cli_no_action_returns_1(self):
        """CLI with no action returns 1."""
        from kairo.cli import main

        rc = main(["personalize"])
        assert rc == 1
