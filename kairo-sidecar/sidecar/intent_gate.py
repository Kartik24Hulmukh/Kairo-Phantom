"""
sidecar/intent_gate.py — Kairo Phantom Intent Classification Gate
=================================================================
Classifies user prompts into structured intent before any LLM call.
Targets sub-50ms completion using a lightweight qwen2.5:3b model.
"""

from dataclasses import dataclass
import time
import json
import logging

log = logging.getLogger("kairo-sidecar.intent_gate")


@dataclass
class IntentClassification:
    intent: str
    domain: str
    target_element: str
    confidence: float


class IntentGate:
    """
    Lightweight intent classifier that gates every request before the heavy LLM call.
    Uses qwen2.5:3b via Ollama for sub-50ms classifications.
    Lazy-singleton pattern: instantiate once, reuse forever.
    """

    MODEL = "qwen2.5:3b"
    SYSTEM_PROMPT = (
        "You are an intent classifier. "
        "REMINDER: First character must be {. "
        'Respond ONLY with JSON: {"intent": str, "domain": str, "target_element": str, "confidence": float}'
    )

    _FALLBACK = IntentClassification(
        intent="unknown",
        domain="general",
        target_element="document",
        confidence=0.5,
    )

    def classify(self, user_prompt: str, app_name: str = "") -> IntentClassification:
        """
        Classify the user prompt into a structured IntentClassification.

        Must complete under 50ms for cached / warm models.
        Uses ollama.chat() with qwen2.5:3b.
        Falls back gracefully if the model is unavailable or returns malformed JSON.

        Parameters
        ----------
        user_prompt : str
            The raw user instruction.
        app_name : str
            Optional active application name for domain disambiguation.

        Returns
        -------
        IntentClassification
            Populated dataclass; never raises.
        """
        t_start = time.perf_counter()

        try:
            import ollama  # local import so the module loads even without ollama installed

            context_hint = f" Active app: {app_name}." if app_name else ""
            messages = [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (f"Classify this user prompt:{context_hint}\n\n{user_prompt}"),
                },
            ]

            response = ollama.chat(
                model=self.MODEL,
                messages=messages,
                options={"temperature": 0.0, "num_predict": 128},
            )

            raw = response["message"]["content"].strip()

            # Ensure we start at the first `{`
            brace_idx = raw.find("{")
            if brace_idx != -1:
                raw = raw[brace_idx:]

            data = json.loads(raw)

            result = IntentClassification(
                intent=str(data.get("intent", "unknown")),
                domain=str(data.get("domain", "general")),
                target_element=str(data.get("target_element", "document")),
                confidence=float(data.get("confidence", 0.5)),
            )

        except json.JSONDecodeError as e:
            log.warning(f"IntentGate: JSON parse error — {e}. Using fallback.")
            result = IntentClassification(
                intent="unknown",
                domain="general",
                target_element="document",
                confidence=0.5,
            )
        except Exception as e:
            log.warning(f"IntentGate: classify failed — {e}. Using fallback.")
            result = IntentClassification(
                intent="unknown",
                domain="general",
                target_element="document",
                confidence=0.5,
            )

        elapsed_ms = (time.perf_counter() - t_start) * 1000
        log.debug(
            f"IntentGate.classify: intent={result.intent} domain={result.domain} "
            f"confidence={result.confidence:.2f} elapsed={elapsed_ms:.1f}ms"
        )
        if elapsed_ms > 50:
            log.info(
                f"IntentGate: classify exceeded 50ms target (took {elapsed_ms:.1f}ms). "
                "Ensure qwen2.5:3b is warm and GPU-accelerated."
            )

        return result


# ---------------------------------------------------------------------------
# Module-level lazy singleton — import and reuse across the sidecar process
# ---------------------------------------------------------------------------
_gate_singleton: IntentGate | None = None


def get_intent_gate() -> IntentGate:
    """Return the module-level singleton IntentGate (created on first call)."""
    global _gate_singleton
    if _gate_singleton is None:
        _gate_singleton = IntentGate()
    return _gate_singleton
