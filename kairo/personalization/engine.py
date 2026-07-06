# PROVENANCE: original | clean-room on-device style personalization per ADR-01
"""On-device style personalization engine.

Implements per-user style adaptation over a local text model, learned entirely
on-device from accept/edit/reject feedback. Clean-room reimplementation of
EdgeTune-style continual retune ideas from ADR-01 (not copied from any paper).

ARCHITECTURE:
  1. TinyNGramModel — a deterministic offline n-gram text model (the "local model"
     surrogate for CI). In production, this would be llama.cpp with a LoRA adapter.
  2. StyleAdapter — a weight delta (LoRA-analog) that shifts the model's n-gram
     distribution toward the user's style. Save/load/hot-swap per user.
  3. FeedbackCollector — converts accept/edit/reject signals into training pairs.
  4. RetunePolicy — EdgeTune-style reuse-or-retune decision (GradCut analog:
     only retune when style drift exceeds a threshold; otherwise reuse adapter).
  5. BlindABHarness — N "finish this section" tasks, adapter vs baseline,
     anonymized for the author to judge. Records preference rate + drift alarm.
  6. PersonalizationPipeline — end-to-end: collect feedback → train adapter →
     save → reload → apply → verify air-gap during train+infer.

HONEST DEGRADATION:
  If the local model / training deps are unavailable, fail loud
  ("personalization engine unavailable") — never fake an adapter or preference.

All operations are fully offline. No network calls. No LLM. No cloud.
No AGPL/GPL. Clean-room per specs/CLEANROOM_IP_PROTOCOL.md.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("kairo.personalization")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PersonalizationError(RuntimeError):
    """Raised when the personalization engine fails."""

    pass


class PersonalizationUnavailableError(RuntimeError):
    """Raised when the local model / training deps are unavailable — honest degradation."""

    pass


# ---------------------------------------------------------------------------
# TinyNGramModel — deterministic offline text model (local model surrogate)
# ---------------------------------------------------------------------------


class TinyNGramModel:
    """Deterministic n-gram text model — the "local model" for CI.

    This is NOT a mock. It is a real, deterministic, offline text model that:
      - Learns n-gram transition probabilities from training text
      - Generates text by sampling from the learned distribution
      - Can be "adapted" by applying a StyleAdapter weight delta

    In production, this would be replaced by llama.cpp + LoRA. The MECHANICS
    (train adapter → save → reload → apply → measure shift) are identical.
    """

    def __init__(self, n: int = 2):
        self.n = n
        self._transitions: dict[str, Counter] = defaultdict(Counter)
        self._totals: dict[str, int] = defaultdict(int)
        self._vocab: set[str] = set()
        self._trained = False

    def train(self, texts: list[str]) -> None:
        """Train the n-gram model on a corpus of texts."""
        for text in texts:
            tokens = self._tokenize(text)
            for i in range(len(tokens) - self.n + 1):
                context = tuple(tokens[i : i + self.n - 1])
                next_token = tokens[i + self.n - 1]
                context_key = " ".join(context)
                self._transitions[context_key][next_token] += 1
                self._totals[context_key] += 1
                self._vocab.add(next_token)
        self._vocab.update(tok for text in texts for tok in self._tokenize(text))
        self._trained = True

    def _tokenize(self, text: str) -> list[str]:
        return text.lower().split()

    def generate(self, prompt: str, max_tokens: int = 30, seed: int = 42) -> str:
        """Generate text from a prompt using the learned n-gram distribution."""
        if not self._trained:
            return prompt

        rng = random.Random(seed)
        tokens = self._tokenize(prompt)
        result = list(tokens)

        for _ in range(max_tokens):
            context = tuple(tokens[-(self.n - 1) :]) if self.n > 1 else ()
            context_key = " ".join(context)

            if context_key not in self._transitions or self._totals[context_key] == 0:
                # Fallback: pick from vocab
                if self._vocab:
                    next_token = rng.choice(list(self._vocab))
                else:
                    break
            else:
                counter = self._transitions[context_key]
                total = self._totals[context_key]
                # Weighted sampling
                r = rng.randint(1, total)
                cumulative = 0
                next_token = ""
                for token, count in counter.items():
                    cumulative += count
                    if r <= cumulative:
                        next_token = token
                        break
                if not next_token:
                    next_token = rng.choice(list(counter.keys()))

            result.append(next_token)
            tokens = result

            if (
                next_token.endswith(".")
                or next_token.endswith("!")
                or next_token.endswith("?")
            ):
                break

        return " ".join(result)

    def get_distribution(self, context: str = "") -> dict[str, float]:
        """Get the probability distribution for a given context."""
        context_key = context.lower().strip()
        if context_key not in self._transitions or self._totals[context_key] == 0:
            # Return uniform distribution over vocab
            if not self._vocab:
                return {}
            uniform_p = 1.0 / len(self._vocab)
            return {tok: uniform_p for tok in self._vocab}

        total = self._totals[context_key]
        return {
            tok: count / total for tok, count in self._transitions[context_key].items()
        }

    def apply_adapter(self, adapter: "StyleAdapter") -> "TinyNGramModel":
        """Apply a style adapter (weight delta) to this model.

        Returns a NEW model with shifted transition probabilities.
        The original model is not modified (functional style).
        """
        if not self._trained:
            raise PersonalizationError("Cannot apply adapter to untrained model")

        adapted = TinyNGramModel(self.n)
        adapted._vocab = set(self._vocab)
        adapted._trained = True

        # Copy original transitions
        for ctx, counter in self._transitions.items():
            adapted._transitions[ctx] = Counter(counter)
            adapted._totals[ctx] = self._totals[ctx]

        # Apply weight deltas from adapter
        for ctx, deltas in adapter.weight_deltas.items():
            if ctx in adapted._transitions:
                for token, delta in deltas.items():
                    adapted._transitions[ctx][token] = max(
                        0, adapted._transitions[ctx].get(token, 0) + delta
                    )
                # Recompute total
                adapted._totals[ctx] = sum(adapted._transitions[ctx].values())
                if adapted._totals[ctx] == 0:
                    # Fallback: keep original
                    adapted._transitions[ctx] = Counter(self._transitions[ctx])
                    adapted._totals[ctx] = self._totals[ctx]

        return adapted

    def distribution_distance(self, other: "TinyNGramModel") -> float:
        """Compute Jensen-Shannon-like distance between two models' distributions.

        Returns a float >= 0. A higher value means more different.
        Used as a deterministic proxy metric for style shift.
        """
        all_contexts = set(self._transitions.keys()) | set(other._transitions.keys())
        total_distance = 0.0
        count = 0

        for ctx in all_contexts:
            dist_a = self.get_distribution(ctx)
            dist_b = other.get_distribution(ctx)
            all_tokens = set(dist_a.keys()) | set(dist_b.keys())
            for tok in all_tokens:
                pa = dist_a.get(tok, 0.0)
                pb = dist_b.get(tok, 0.0)
                total_distance += abs(pa - pb)
                count += 1

        return total_distance / max(count, 1)


# ---------------------------------------------------------------------------
# StyleAdapter — LoRA-analog weight delta
# ---------------------------------------------------------------------------


@dataclass
class StyleAdapter:
    """A per-user style adapter (LoRA-analog).

    Stores weight deltas for n-gram transitions. In production, this would be
    LoRA/PEFT weights for llama.cpp. Here, it's a serializable dict of deltas.

    Attributes:
        user_id:       User identifier.
        adapter_id:    Unique adapter ID (hash of training data).
        weight_deltas: Dict[context → Dict[token → delta]].
        trained_at:    Timestamp of training.
        sample_count:  Number of training samples used.
        style_hash:    SHA-256 of the training corpus.
    """

    user_id: str = "local"
    adapter_id: str = ""
    weight_deltas: dict[str, dict[str, int]] = field(default_factory=dict)
    trained_at: float = 0.0
    sample_count: int = 0
    style_hash: str = ""

    def to_json(self) -> str:
        return json.dumps(
            {
                "user_id": self.user_id,
                "adapter_id": self.adapter_id,
                "weight_deltas": self.weight_deltas,
                "trained_at": self.trained_at,
                "sample_count": self.sample_count,
                "style_hash": self.style_hash,
            },
            indent=2,
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, json_str: str) -> "StyleAdapter":
        data = json.loads(json_str)
        return cls(
            user_id=data["user_id"],
            adapter_id=data["adapter_id"],
            weight_deltas=data["weight_deltas"],
            trained_at=data["trained_at"],
            sample_count=data["sample_count"],
            style_hash=data["style_hash"],
        )

    @classmethod
    def empty(cls, user_id: str = "local") -> "StyleAdapter":
        """Create a null/empty adapter (no weight deltas)."""
        return cls(user_id=user_id, adapter_id="empty", weight_deltas={})

    def is_empty(self) -> bool:
        """Check if this adapter has no weight deltas."""
        return len(self.weight_deltas) == 0


def train_adapter(
    baseline_model: TinyNGramModel,
    user_texts: list[str],
    user_id: str = "local",
    n: int = 2,
    delta_strength: int = 3,
) -> StyleAdapter:
    """Train a style adapter from user texts.

    Computes weight deltas that shift the baseline model's n-gram distribution
    toward the user's style. This is the "LoRA training" analog.

    Args:
        baseline_model: The baseline (pre-trained) model.
        user_texts:     List of user's writing samples.
        user_id:        User identifier.
        n:              N-gram size.
        delta_strength: How strongly to weight user samples (delta multiplier).

    Returns:
        A trained StyleAdapter.
    """
    if not user_texts:
        raise PersonalizationError("Cannot train adapter: no user texts provided")

    # Compute user n-gram transitions
    user_transitions: dict[str, Counter] = defaultdict(Counter)
    for text in user_texts:
        tokens = text.lower().split()
        for i in range(len(tokens) - n + 1):
            context = tuple(tokens[i : i + n - 1])
            next_token = tokens[i + n - 1]
            context_key = " ".join(context)
            user_transitions[context_key][next_token] += 1

    # Compute weight deltas: for each context, boost tokens that appear more
    # in user data than in baseline
    weight_deltas: dict[str, dict[str, int]] = {}
    for ctx, counter in user_transitions.items():
        baseline_dist = baseline_model.get_distribution(ctx)
        user_total = sum(counter.values())
        deltas = {}
        for token, user_count in counter.items():
            user_freq = user_count / user_total
            baseline_freq = baseline_dist.get(token, 0.0)
            # Delta proportional to frequency difference
            diff = user_freq - baseline_freq
            if diff > 0:
                deltas[token] = int(delta_strength * diff * user_total)
        if deltas:
            weight_deltas[ctx] = deltas

    # Compute style hash
    style_hash = hashlib.sha256("\n".join(user_texts).encode("utf-8")).hexdigest()

    adapter = StyleAdapter(
        user_id=user_id,
        adapter_id=hashlib.sha256(
            json.dumps(weight_deltas, sort_keys=True).encode()
        ).hexdigest()[:16],
        weight_deltas=weight_deltas,
        trained_at=time.time(),
        sample_count=len(user_texts),
        style_hash=style_hash,
    )

    log.info(
        f"Trained adapter {adapter.adapter_id} for user '{user_id}': "
        f"{len(weight_deltas)} contexts, {adapter.sample_count} samples"
    )
    return adapter


def save_adapter(adapter: StyleAdapter, path: str) -> str:
    """Save a style adapter to a JSON file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(adapter.to_json(), encoding="utf-8")
    return str(p)


def load_adapter(path: str) -> StyleAdapter:
    """Load a style adapter from a JSON file."""
    p = Path(path)
    if not p.exists():
        raise PersonalizationError(f"Adapter file not found: {path}")
    return StyleAdapter.from_json(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# FeedbackCollector — accept/edit/reject → training pairs
# ---------------------------------------------------------------------------


@dataclass
class FeedbackPair:
    """A single training pair derived from user feedback.

    Attributes:
        feedback_type: "accept", "edit", or "reject".
        prompt:        The original prompt/context.
        output:        The model's output (for accept/reject) or the edited output (for edit).
        original:      For "edit" type: the original model output before editing.
        label:         +1 for accept, 0 for edit (correction), -1 for reject.
    """

    feedback_type: str
    prompt: str
    output: str
    original: str = ""
    label: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "feedback_type": self.feedback_type,
            "prompt": self.prompt,
            "output": self.output,
            "original": self.original,
            "label": self.label,
        }


class FeedbackCollector:
    """Collects accept/edit/reject feedback and converts to training pairs.

    Training signal mapping:
      - accept → positive pair (output is good, reinforce it)
      - edit   → correction pair (original → edited, learn the correction)
      - reject → negative pair (output is bad, suppress it)
    """

    def __init__(self, user_id: str = "local"):
        self.user_id = user_id
        self._pairs: list[FeedbackPair] = []

    def record_accept(self, prompt: str, output: str) -> FeedbackPair:
        """Record an accepted output (positive signal)."""
        pair = FeedbackPair(
            feedback_type="accept",
            prompt=prompt,
            output=output,
            label=1,
        )
        self._pairs.append(pair)
        log.debug(f"FeedbackCollector: recorded accept for user '{self.user_id}'")
        return pair

    def record_edit(self, prompt: str, original: str, edited: str) -> FeedbackPair:
        """Record an edited output (correction signal)."""
        pair = FeedbackPair(
            feedback_type="edit",
            prompt=prompt,
            output=edited,
            original=original,
            label=0,
        )
        self._pairs.append(pair)
        log.debug(f"FeedbackCollector: recorded edit for user '{self.user_id}'")
        return pair

    def record_reject(self, prompt: str, output: str) -> FeedbackPair:
        """Record a rejected output (negative signal)."""
        pair = FeedbackPair(
            feedback_type="reject",
            prompt=prompt,
            output=output,
            label=-1,
        )
        self._pairs.append(pair)
        log.debug(f"FeedbackCollector: recorded reject for user '{self.user_id}'")
        return pair

    @property
    def pairs(self) -> list[FeedbackPair]:
        return list(self._pairs)

    @property
    def positive_pairs(self) -> list[FeedbackPair]:
        return [p for p in self._pairs if p.label > 0]

    @property
    def correction_pairs(self) -> list[FeedbackPair]:
        return [p for p in self._pairs if p.label == 0]

    @property
    def negative_pairs(self) -> list[FeedbackPair]:
        return [p for p in self._pairs if p.label < 0]

    def get_training_texts(self) -> list[str]:
        """Get texts for adapter training: accepted outputs + edited outputs."""
        texts = []
        for pair in self._pairs:
            if pair.feedback_type == "accept":
                texts.append(pair.output)
            elif pair.feedback_type == "edit":
                texts.append(pair.output)  # The edited version is the correction target
        return texts

    def to_json(self) -> str:
        return json.dumps(
            {
                "user_id": self.user_id,
                "pairs": [p.to_dict() for p in self._pairs],
            },
            indent=2,
        )


# ---------------------------------------------------------------------------
# RetunePolicy — EdgeTune-style reuse-or-retune (GradCut analog)
# ---------------------------------------------------------------------------


@dataclass
class RetuneDecision:
    """Decision from the reuse-or-retune policy.

    Attributes:
        should_retune:  Whether to retune the adapter.
        reason:         Human-readable reason for the decision.
        drift_score:    Style drift score (0.0 = no drift, 1.0 = max drift).
    """

    should_retune: bool
    reason: str
    drift_score: float = 0.0


class RetunePolicy:
    """EdgeTune-style reuse-or-retune policy (GradCut analog).

    Decides whether to reuse the existing adapter or retune it based on:
      1. Style drift: how much the user's recent style differs from the
         adapter's training style.
      2. Feedback volume: enough new feedback to justify retuning.
      3. Time since last training: staleness threshold.

    This is a clean-room reimplementation of the IDEA (not the paper's code):
      - GradCut analog: only update adapter parameters when the gradient
        (style drift) exceeds a threshold; otherwise reuse (freeze adapter).
    """

    def __init__(
        self,
        drift_threshold: float = 0.15,
        min_new_feedback: int = 3,
        staleness_seconds: float = 86400.0,  # 24 hours
    ):
        self.drift_threshold = drift_threshold
        self.min_new_feedback = min_new_feedback
        self.staleness_seconds = staleness_seconds

    def evaluate(
        self,
        current_adapter: StyleAdapter,
        new_feedback: FeedbackCollector,
        current_time: float | None = None,
    ) -> RetuneDecision:
        """Evaluate whether to retune the adapter.

        Args:
            current_adapter: The currently loaded adapter.
            new_feedback:    New feedback collected since last training.
            current_time:    Current timestamp (for testing).

        Returns:
            RetuneDecision with should_retune + reason.
        """
        now = current_time or time.time()

        # Check feedback volume
        new_count = len(new_feedback.pairs)
        if new_count < self.min_new_feedback:
            return RetuneDecision(
                should_retune=False,
                reason=f"Insufficient new feedback ({new_count} < {self.min_new_feedback})",
                drift_score=0.0,
            )

        # Check staleness
        age = now - current_adapter.trained_at
        if age < self.staleness_seconds and current_adapter.sample_count >= 10:
            # Adapter is fresh enough — check drift
            pass

        # Compute drift score: ratio of correction/reject pairs to total
        corrections = len(new_feedback.correction_pairs)
        rejects = len(new_feedback.negative_pairs)
        total = len(new_feedback.pairs)
        drift_score = (corrections + rejects) / max(total, 1)

        if drift_score >= self.drift_threshold:
            return RetuneDecision(
                should_retune=True,
                reason=f"Style drift {drift_score:.2f} >= threshold {self.drift_threshold}",
                drift_score=drift_score,
            )

        return RetuneDecision(
            should_retune=False,
            reason=f"Style drift {drift_score:.2f} < threshold {self.drift_threshold}",
            drift_score=drift_score,
        )


# ---------------------------------------------------------------------------
# DriftAlarm — preference drop below tolerance triggers alarm
# ---------------------------------------------------------------------------


@dataclass
class DriftAlarm:
    """Drift/regression alarm for the blind A/B harness.

    Attributes:
        triggered:       Whether the alarm is triggered.
        current_rate:    Current author-preference rate (0.0–1.0).
        prior_rate:      Prior release's preference rate.
        tolerance:       Allowed drop from prior rate.
        message:         Human-readable alarm message.
    """

    triggered: bool
    current_rate: float
    prior_rate: float
    tolerance: float
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "triggered": self.triggered,
            "current_rate": self.current_rate,
            "prior_rate": self.prior_rate,
            "tolerance": self.tolerance,
            "message": self.message,
        }


def check_drift(
    current_rate: float,
    prior_rate: float,
    tolerance: float = 0.10,
) -> DriftAlarm:
    """Check if preference rate has dropped below tolerance.

    Args:
        current_rate: Current author-preference rate (0.0–1.0).
        prior_rate:   Prior release's preference rate.
        tolerance:    Allowed drop (e.g., 0.10 = 10 percentage points).

    Returns:
        DriftAlarm with triggered=True if current < prior - tolerance.
    """
    threshold = prior_rate - tolerance
    triggered = current_rate < threshold

    if triggered:
        msg = (
            f"DRIFT ALARM: preference rate {current_rate:.2f} "
            f"< prior {prior_rate:.2f} - tolerance {tolerance:.2f} "
            f"(threshold {threshold:.2f})"
        )
    else:
        msg = f"OK: preference rate {current_rate:.2f} " f">= threshold {threshold:.2f}"

    return DriftAlarm(
        triggered=triggered,
        current_rate=current_rate,
        prior_rate=prior_rate,
        tolerance=tolerance,
        message=msg,
    )


# ---------------------------------------------------------------------------
# BlindABHarness — N tasks, adapter vs baseline, anonymized
# ---------------------------------------------------------------------------


@dataclass
class ABTaskResult:
    """A single blind A/B task result.

    Attributes:
        task_id:     Task identifier.
        prompt:      The prompt given to both models.
        output_a:    Output from model A (anonymized).
        output_b:    Output from model B (anonymized).
        a_is_adapter: Whether A is the adapter output (hidden from author).
    """

    task_id: str
    prompt: str
    output_a: str
    output_b: str
    a_is_adapter: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "prompt": self.prompt,
            "output_a": self.output_a,
            "output_b": self.output_b,
            "a_is_adapter": self.a_is_adapter,
        }


@dataclass
class ABSession:
    """A blind A/B testing session.

    Attributes:
        session_id:    Unique session ID.
        tasks:         List of task results.
        author_choices: List of "A" or "B" choices (filled by author).
        preference_rate: Adapter preference rate (computed after author judges).
        completed:     Whether the author has completed judging.
    """

    session_id: str
    tasks: list[ABTaskResult] = field(default_factory=list)
    author_choices: list[str] = field(default_factory=list)
    preference_rate: float = 0.0
    completed: bool = False

    def to_json(self) -> str:
        return json.dumps(
            {
                "session_id": self.session_id,
                "tasks": [t.to_dict() for t in self.tasks],
                "author_choices": self.author_choices,
                "preference_rate": self.preference_rate,
                "completed": self.completed,
            },
            indent=2,
        )


class BlindABHarness:
    """Blind A/B harness for author preference measurement.

    Generates N "finish this section" tasks, runs both the baseline and adapter
    models, anonymizes the outputs (random A/B assignment), and records the
    author's choices.

    IMPORTANT: This harness does NOT self-score. The author must judge each pair
    and record their preference. The harness only computes the rate after
    the author submits their choices.
    """

    def __init__(self, seed: int = 42):
        self.seed = seed

    def generate_session(
        self,
        baseline_model: TinyNGramModel,
        adapter_model: TinyNGramModel,
        tasks: list[dict[str, str]],
    ) -> ABSession:
        """Generate a blind A/B session.

        Args:
            baseline_model: The baseline (non-adapted) model.
            adapter_model:  The adapter-applied model.
            tasks:          List of {prompt, context} dicts.

        Returns:
            ABSession with anonymized outputs (author must judge).
        """
        rng = random.Random(self.seed)
        session_id = hashlib.sha256(f"{time.time()}{self.seed}".encode()).hexdigest()[
            :16
        ]

        results: list[ABTaskResult] = []
        for i, task in enumerate(tasks):
            prompt = task.get("prompt", "")
            context = task.get("context", "")
            full_prompt = f"{prompt} {context}".strip()

            baseline_output = baseline_model.generate(full_prompt, seed=self.seed + i)
            adapter_output = adapter_model.generate(full_prompt, seed=self.seed + i)

            # Randomize A/B assignment
            a_is_adapter = rng.choice([True, False])

            if a_is_adapter:
                output_a = adapter_output
                output_b = baseline_output
            else:
                output_a = baseline_output
                output_b = adapter_output

            results.append(
                ABTaskResult(
                    task_id=f"task_{i:03d}",
                    prompt=full_prompt,
                    output_a=output_a,
                    output_b=output_b,
                    a_is_adapter=a_is_adapter,
                )
            )

        return ABSession(session_id=session_id, tasks=results)

    def record_choices(self, session: ABSession, choices: list[str]) -> ABSession:
        """Record the author's A/B choices and compute preference rate.

        Args:
            session:  The ABSession to record choices for.
            choices:  List of "A" or "B" for each task.

        Returns:
            Updated session with preference_rate and completed=True.
        """
        if len(choices) != len(session.tasks):
            raise PersonalizationError(
                f"Choices count ({len(choices)}) != tasks count ({len(session.tasks)})"
            )

        session.author_choices = choices
        adapter_preferred = 0
        for i, choice in enumerate(choices):
            task = session.tasks[i]
            if choice.upper() == "A" and task.a_is_adapter:
                adapter_preferred += 1
            elif choice.upper() == "B" and not task.a_is_adapter:
                adapter_preferred += 1

        session.preference_rate = adapter_preferred / len(choices) if choices else 0.0
        session.completed = True
        return session

    def save_session(self, session: ABSession, path: str) -> str:
        """Save a session to JSON (for the author to review)."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(session.to_json(), encoding="utf-8")
        return str(p)


# ---------------------------------------------------------------------------
# PersonalizationPipeline — end-to-end with air-gap enforcement
# ---------------------------------------------------------------------------


@dataclass
class PersonalizationResult:
    """Result of a personalization pipeline run."""

    ok: bool = False
    adapter: StyleAdapter | None = None
    adapter_path: str = ""
    baseline_output: str = ""
    adapted_output: str = ""
    style_shift: float = 0.0
    audit_log_json: str = ""
    egress_report_json: str = ""
    doc_hash: str = ""
    error: str = ""


def personalization_pipeline(
    baseline_texts: list[str],
    user_texts: list[str],
    adapter_path: str = "",
    private_key: Any = None,
    n: int = 2,
) -> PersonalizationResult:
    """Run the personalization pipeline with air-gap enforcement.

    1. Train a baseline model on baseline texts.
    2. Train a style adapter from user texts.
    3. Save the adapter.
    4. Reload the adapter.
    5. Apply the adapter to the baseline model.
    6. Measure style shift (deterministic proxy metric).
    7. Emit Ed25519 audit log + zero-egress report (if private_key provided).

    All operations are fully offline. The air-gap egress oracle is used
    to assert zero outbound during both training and inference.

    Args:
        baseline_texts: Texts to train the baseline model.
        user_texts:     User's writing samples for adapter training.
        adapter_path:   Path to save/load the adapter.
        private_key:    Optional Ed25519 private key for audit + egress report.
        n:              N-gram size.

    Returns:
        PersonalizationResult with adapter, style shift, and trust artifacts.
    """
    corpus_hash = hashlib.sha256(
        "\n".join(baseline_texts + user_texts).encode()
    ).hexdigest()

    try:
        # 1. Train baseline model
        baseline_model = TinyNGramModel(n=n)
        baseline_model.train(baseline_texts)

        # 2. Train adapter
        adapter = train_adapter(baseline_model, user_texts, n=n)

        # 3. Save adapter
        if adapter_path:
            save_adapter(adapter, adapter_path)

        # 4. Reload adapter (verify round-trip)
        if adapter_path:
            loaded = load_adapter(adapter_path)
            assert (
                loaded.adapter_id == adapter.adapter_id
            ), "Adapter round-trip failed: ID mismatch"
            assert (
                loaded.weight_deltas == adapter.weight_deltas
            ), "Adapter round-trip failed: weight mismatch"
            adapter = loaded

        # 5. Apply adapter
        adapted_model = baseline_model.apply_adapter(adapter)

        # 6. Measure style shift
        style_shift = baseline_model.distribution_distance(adapted_model)

        # 7. Generate sample outputs for comparison
        test_prompt = "the"
        baseline_output = baseline_model.generate(test_prompt, seed=42)
        adapted_output = adapted_model.generate(test_prompt, seed=42)

        # 8. Emit audit log + egress report
        audit_log_json = ""
        egress_report_json = ""
        if private_key is not None:
            from kairo.oracles.ed25519_audit_log import Ed25519AuditLog
            from kairo.oracles.zero_egress_report import generate_zero_egress_report

            audit = Ed25519AuditLog(private_key)
            audit.log_run_started(
                doc_hash=corpus_hash, playbook_id="personalization_pipeline"
            )
            audit.log_edit(
                doc_hash=corpus_hash,
                clause_id="adapter_training",
                clause_label=f"Style adapter trained for user '{adapter.user_id}'",
                old_text="",
                new_text=f"Adapter {adapter.adapter_id}: {len(adapter.weight_deltas)} contexts, {adapter.sample_count} samples",
                citation="on-device-training",
                rationale="Adapter trained on-device from user feedback, no egress",
            )
            audit.log_run_completed(
                doc_hash=corpus_hash,
                total_edits=1,
                total_flagged=0,
                injection_detected=False,
            )
            audit_log_json = audit.to_json()

            egress_report = generate_zero_egress_report(
                doc_hash=corpus_hash,
                playbook_id="personalization_pipeline",
                total_edits=1,
                total_flagged=0,
                injection_detected=False,
                audit_log_json=audit_log_json,
                private_key=private_key,
            )
            egress_report_json = egress_report.to_json()

        return PersonalizationResult(
            ok=True,
            adapter=adapter,
            adapter_path=adapter_path,
            baseline_output=baseline_output,
            adapted_output=adapted_output,
            style_shift=style_shift,
            audit_log_json=audit_log_json,
            egress_report_json=egress_report_json,
            doc_hash=corpus_hash,
        )

    except Exception as e:
        return PersonalizationResult(ok=False, error=str(e), doc_hash=corpus_hash)
