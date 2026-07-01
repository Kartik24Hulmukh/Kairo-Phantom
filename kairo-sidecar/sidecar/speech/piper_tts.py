"""
Domain 8: Piper TTS Wrapper
============================
Real wrapper for Piper neural TTS (offline, GPL-compatible via separate process).

If piper-tts is not installed, the class raises RuntimeError on init —
NEVER silently falls back or mocks.

Usage:
    tts = PiperTTS(voice_model_path='/path/to/en_US-lessac-medium.onnx')
    result = tts.synthesize('Hello world')
    # → {audio_path, duration, sample_rate}
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
import wave
from pathlib import Path
from typing import Dict, Optional

import numpy as np

log = logging.getLogger("kairo.piper_tts")

# ── Availability check ──────────────────────────────────────────────────────

HAS_PIPER: bool = False

try:
    import piper  # type: ignore

    HAS_PIPER = True
except ImportError:
    log.info("piper not installed — PiperTTS will raise on init. " "Install: pip install piper-tts")
    piper = None  # type: ignore


class PiperTTS:
    """
    Real Piper TTS wrapper.

    Raises RuntimeError if piper-tts is not installed — never mocks.
    """

    def __init__(self, voice_model_path: Optional[str] = None):
        if not HAS_PIPER:
            raise RuntimeError("Piper not installed. pip install piper-tts")

        self.voice_model_path = voice_model_path
        self._voice = None
        self._sample_rate: int = 22050

        if voice_model_path:
            if not os.path.isfile(voice_model_path):
                raise FileNotFoundError(f"Piper voice model not found: {voice_model_path}")
            self._load_voice(voice_model_path)

    def _load_voice(self, voice_model_path: str) -> None:
        """Load the Piper voice model from an .onnx file."""
        log.info(f"Loading Piper voice model: {voice_model_path}")
        try:
            # piper.Voice is the main interface
            self._voice = piper.PiperVoice.load(voice_model_path)  # type: ignore
            # Get sample rate from the voice config
            if hasattr(self._voice, "config") and hasattr(self._voice.config, "sample_rate"):
                self._sample_rate = int(self._voice.config.sample_rate)
        except Exception as e:
            raise RuntimeError(f"Failed to load Piper voice model: {e}") from e

    def synthesize(self, text: str) -> Dict:
        """
        Synthesize speech from text.

        Args:
            text: Input text to synthesize.

        Returns:
            {audio_path: str, duration: float, sample_rate: int}
        """
        if not self._voice:
            raise RuntimeError("No voice model loaded. Provide voice_model_path to __init__.")
        if not text or not text.strip():
            raise ValueError("Text must not be empty")

        # Create temp WAV file
        tmp_dir = Path(tempfile.gettempdir()) / "kairo_piper"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(tmp_dir / f"tts_{int(time.time() * 1000)}.wav")

        self._synthesize_to_file_internal(text, output_path)

        # Read back duration
        duration = self._get_wav_duration(output_path)

        log.info(f"Synthesized {len(text)} chars → {output_path} ({duration:.2f}s)")

        return {
            "audio_path": output_path,
            "duration": duration,
            "sample_rate": self._sample_rate,
        }

    def synthesize_to_file(self, text: str, output_path: str) -> str:
        """
        Synthesize speech and write to a specific file path.

        Args:
            text: Input text to synthesize.
            output_path: Path to write WAV file.

        Returns:
            The output_path (same as input).
        """
        if not self._voice:
            raise RuntimeError("No voice model loaded. Provide voice_model_path to __init__.")
        if not text or not text.strip():
            raise ValueError("Text must not be empty")

        self._synthesize_to_file_internal(text, output_path)

        log.info(f"Synthesized {len(text)} chars → {output_path}")

        return output_path

    def _synthesize_to_file_internal(self, text: str, output_path: str) -> None:
        """Internal: synthesize text to a WAV file."""
        with wave.open(output_path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(self._sample_rate)

            # Piper synthesize returns audio chunks
            for chunk in self._voice.synthesize(text):
                audio_bytes = chunk.audio_bytes
                if isinstance(audio_bytes, np.ndarray):
                    audio_bytes = audio_bytes.tobytes()
                wav_file.writeframes(audio_bytes)

    @staticmethod
    def _get_wav_duration(wav_path: str) -> float:
        """Read duration from a WAV file."""
        try:
            with wave.open(wav_path, "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                return float(frames) / float(rate) if rate > 0 else 0.0
        except Exception:
            return 0.0

    def is_loaded(self) -> bool:
        """Return True if a voice model is loaded."""
        return self._voice is not None
