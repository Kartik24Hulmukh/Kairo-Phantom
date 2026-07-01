"""
Domain 8: openWakeWord Wake Word Detector
==========================================
Real wrapper for openWakeWord wake word detection.

If openwakeword is not installed, the class raises RuntimeError on init —
NEVER silently falls back or mocks.

Usage:
    detector = WakeDetector(model_name='hey_kairo')
    result = detector.detect(audio_chunk_bytes)
    # → {detected: bool, confidence: float}
"""

from __future__ import annotations

import logging
from typing import Dict, List

import numpy as np

log = logging.getLogger("kairo.wake_detector")

# ── Availability check ──────────────────────────────────────────────────────

HAS_OPENWAKEWORD: bool = False

try:
    from openwakeword import Model as OWWModel  # type: ignore

    HAS_OPENWAKEWORD = True
except ImportError:
    log.info(
        "openwakeword not installed — WakeDetector will raise on init. "
        "Install: pip install openwakeword"
    )
    OWWModel = None  # type: ignore


class WakeDetector:
    """
    Real openWakeWord wake word detector.

    Raises RuntimeError if openwakeword is not installed — never mocks.
    """

    def __init__(self, model_name: str = "hey_kairo"):
        if not HAS_OPENWAKEWORD:
            raise RuntimeError("openwakeword not installed. pip install openwakeword")

        self.model_name = model_name
        self._model = None
        self._load_model()

    def _load_model(self) -> None:
        """Load the openWakeWord model."""
        log.info(f"Loading openWakeWord model: {self.model_name}")
        self._model = OWWModel(wakeword_models=[self.model_name])

    def detect(self, audio_chunk: bytes) -> Dict:
        """
        Detect wake word in an audio chunk.

        Args:
            audio_chunk: 16-bit PCM mono bytes at 16kHz
                         (typically 1280 samples = 2560 bytes for 80ms)

        Returns:
            {detected: bool, confidence: float}
            confidence is 0.0–1.0
        """
        if not self._model:
            raise RuntimeError("Model not loaded")

        # Convert 16-bit PCM bytes to int16 numpy array
        samples = np.frombuffer(audio_chunk, dtype=np.int16)

        # openWakeWord expects int16 numpy array
        prediction = self._model.predict(samples)

        # Get the score for our model
        # predict() returns a dict like {model_name: score}
        if isinstance(prediction, dict):
            score = prediction.get(self.model_name, 0.0)
        else:
            score = float(prediction)

        confidence = float(score)
        detected = confidence >= 0.5

        if detected:
            log.info(f"Wake word '{self.model_name}' detected: confidence={confidence:.3f}")

        return {
            "detected": detected,
            "confidence": confidence,
        }

    @staticmethod
    def get_available_models() -> List[str]:
        """
        Return list of available openWakeWord model names.

        This queries the openwakeword package for bundled models.
        """
        if not HAS_OPENWAKEWORD:
            raise RuntimeError("openwakeword not installed. pip install openwakeword")

        try:
            from openwakeword import get_pretrained_model_names  # type: ignore

            return list(get_pretrained_model_names())
        except ImportError:
            # Fallback: return known default models
            return [
                "hey_jarvis",
                "hey_mycroft",
                "hey_firefox",
                "alexa",
                "computer",
                "hey_kairo",
            ]

    def is_loaded(self) -> bool:
        """Return True if the model is loaded and ready."""
        return self._model is not None
