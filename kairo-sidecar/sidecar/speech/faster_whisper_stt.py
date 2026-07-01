"""
Domain 8: faster-whisper STT Wrapper
=====================================
Real wrapper for faster-whisper speech-to-text (CTranslate2 backend).

If faster-whisper is not installed, the class raises RuntimeError on init —
NEVER silently falls back or mocks.

Usage:
    stt = FasterWhisperSTT(model_size='base.en', device='cpu', compute_type='int8')
    result = stt.transcribe('/path/to/audio.wav')
    # → {text, segments, language, duration}
"""

from __future__ import annotations

import logging
import os
import time
from typing import Dict, List, Optional

import numpy as np

log = logging.getLogger("kairo.faster_whisper_stt")

# ── Availability check ──────────────────────────────────────────────────────

HAS_FASTER_WHISPER: bool = False

try:
    from faster_whisper import WhisperModel  # type: ignore

    HAS_FASTER_WHISPER = True
except ImportError:
    log.info(
        "faster-whisper not installed — FasterWhisperSTT will raise on init. "
        "Install: pip install faster-whisper"
    )
    WhisperModel = None  # type: ignore


class FasterWhisperSTT:
    """
    Real faster-whisper STT wrapper.

    Raises RuntimeError if faster-whisper is not installed — never mocks.
    """

    def __init__(
        self,
        model_size: str = "base.en",
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        if not HAS_FASTER_WHISPER:
            raise RuntimeError("faster-whisper not installed. pip install faster-whisper")

        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model: Optional[WhisperModel] = None
        self._load_model()

    def _load_model(self) -> None:
        """Load the faster-whisper model."""
        log.info(
            f"Loading faster-whisper model: size={self.model_size}, "
            f"device={self.device}, compute_type={self.compute_type}"
        )
        self._model = WhisperModel(
            self.model_size,
            device=self.device,
            compute_type=self.compute_type,
        )

    def transcribe(self, audio_path: str) -> Dict:
        """
        Transcribe an audio file on disk.

        Returns dict with keys:
            text: str          — full transcription
            segments: List[Dict] — per-segment {start, end, text}
            language: str      — detected language code
            duration: float    — audio duration in seconds
        """
        if not self._model:
            raise RuntimeError("Model not loaded")
        if not os.path.isfile(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        t0 = time.monotonic()
        segments_iter, info = self._model.transcribe(
            audio_path,
            beam_size=5,
            vad_filter=True,
        )
        segments: List[Dict] = []
        full_text_parts: List[str] = []
        for seg in segments_iter:
            segments.append(
                {
                    "start": round(seg.start, 3),
                    "end": round(seg.end, 3),
                    "text": seg.text.strip(),
                }
            )
            full_text_parts.append(seg.text.strip())

        elapsed = time.monotonic() - t0
        full_text = " ".join(full_text_parts).strip()
        duration = float(info.duration) if hasattr(info, "duration") else 0.0

        log.info(
            f"Transcribed {audio_path}: {len(segments)} segments, "
            f"{duration:.1f}s audio in {elapsed:.2f}s"
        )

        return {
            "text": full_text,
            "segments": segments,
            "language": info.language if hasattr(info, "language") else "unknown",
            "duration": duration,
        }

    def transcribe_audio_array(self, audio: np.ndarray, sample_rate: int) -> Dict:
        """
        Transcribe audio from a numpy array.

        Args:
            audio: 1-D float32 numpy array (mono) or 2-D (channels, samples)
            sample_rate: sample rate in Hz (must be 16000 for faster-whisper)

        Returns same dict shape as transcribe().
        """
        if not self._model:
            raise RuntimeError("Model not loaded")

        # faster-whisper expects float32 mono at 16kHz
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        if audio.ndim > 1:
            # Take first channel
            audio = audio[0] if audio.ndim == 2 else audio.flatten()

        t0 = time.monotonic()
        segments_iter, info = self._model.transcribe(
            audio,
            beam_size=5,
            vad_filter=True,
        )
        segments: List[Dict] = []
        full_text_parts: List[str] = []
        for seg in segments_iter:
            segments.append(
                {
                    "start": round(seg.start, 3),
                    "end": round(seg.end, 3),
                    "text": seg.text.strip(),
                }
            )
            full_text_parts.append(seg.text.strip())

        elapsed = time.monotonic() - t0
        full_text = " ".join(full_text_parts).strip()
        duration = float(len(audio)) / float(sample_rate)

        log.info(
            f"Transcribed array: {len(segments)} segments, "
            f"{duration:.1f}s audio in {elapsed:.2f}s"
        )

        return {
            "text": full_text,
            "segments": segments,
            "language": info.language if hasattr(info, "language") else "unknown",
            "duration": duration,
        }

    def is_loaded(self) -> bool:
        """Return True if the model is loaded and ready."""
        return self._model is not None
