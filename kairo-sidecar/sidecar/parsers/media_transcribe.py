"""
Domain 9: Media Transcription
==============================

Media transcription using faster-whisper (from Domain 8).
Uses ffmpeg to extract audio from video files.

If ffmpeg is unavailable: raises RuntimeError with install instructions.
If faster-whisper is unavailable: raises RuntimeError.

NEVER mocks. All operations are real.

Usage:
    transcriber = MediaTranscriber(model_size='base.en')
    result = transcriber.transcribe_video('/path/to/video.mp4')
    # → {text, segments, duration, language}
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from typing import Dict, List, Optional

log = logging.getLogger("kairo.media_transcribe")

# ── Availability checks ─────────────────────────────────────────────

HAS_FASTER_WHISPER: bool = False

try:
    from faster_whisper import WhisperModel  # type: ignore

    HAS_FASTER_WHISPER = True
except ImportError:
    log.info(
        "faster-whisper not installed — MediaTranscriber will raise on init. "
        "Install: pip install faster-whisper"
    )
    WhisperModel = None  # type: ignore


def _check_ffmpeg() -> str:
    """Return path to ffmpeg binary, or raise RuntimeError."""
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise RuntimeError(
            "ffmpeg not found on PATH. Install: "
            "apt-get install ffmpeg  (Debian/Ubuntu)  |  "
            "brew install ffmpeg  (macOS)  |  "
            "conda install ffmpeg -c conda-forge"
        )
    return ffmpeg_path


class MediaTranscriber:
    """
    Real media transcription wrapper.

    Uses ffmpeg for audio extraction and faster-whisper for STT.
    Raises RuntimeError if either dependency is missing — never mocks.
    """

    def __init__(
        self,
        model_size: str = "base.en",
        device: str = "cpu",
        compute_type: str = "int8",
    ) -> None:
        if not HAS_FASTER_WHISPER:
            raise RuntimeError("faster-whisper not installed. pip install faster-whisper")
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model: Optional[WhisperModel] = None

    def _get_model(self) -> "WhisperModel":
        """Lazily load the faster-whisper model."""
        if self._model is None:
            log.info("Loading faster-whisper model '%s'...", self.model_size)
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
        return self._model

    def extract_audio(self, video_path: str, output_path: str) -> str:
        """
        Extract audio from a video file using ffmpeg.

        Returns the path to the extracted audio file.
        Raises RuntimeError if ffmpeg is unavailable or extraction fails.
        """
        ffmpeg_path = _check_ffmpeg()

        if not os.path.exists(video_path):
            raise RuntimeError(f"Video file not found: {video_path}")

        cmd = [
            ffmpeg_path,
            "-i",
            video_path,
            "-vn",  # no video
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",  # 16kHz for whisper
            "-ac",
            "1",  # mono
            "-y",  # overwrite
            output_path,
        ]
        log.info("Extracting audio: %s → %s", video_path, output_path)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=300,
            )
            if result.returncode != 0:
                stderr = result.stderr.decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"ffmpeg audio extraction failed (exit {result.returncode}): {stderr}"
                )
        except subprocess.TimeoutExpired:
            raise RuntimeError("ffmpeg timed out after 300s")
        except FileNotFoundError as exc:
            raise RuntimeError(f"ffmpeg not found: {exc}") from exc

        if not os.path.exists(output_path):
            raise RuntimeError(f"ffmpeg did not produce output file: {output_path}")
        return output_path

    def transcribe_audio(self, audio_path: str) -> Dict:
        """
        Transcribe an audio file directly via faster-whisper.

        Returns: {text, segments, duration, language}
        """
        if not HAS_FASTER_WHISPER:
            raise RuntimeError("faster-whisper not installed. pip install faster-whisper")
        if not os.path.exists(audio_path):
            raise RuntimeError(f"Audio file not found: {audio_path}")

        model = self._get_model()
        log.info("Transcribing audio: %s", audio_path)

        segments_iter, info = model.transcribe(audio_path, beam_size=5)

        segments: List[Dict] = []
        full_text_parts: List[str] = []
        total_duration = 0.0

        for seg in segments_iter:
            seg_dict = {
                "start": float(seg.start),
                "end": float(seg.end),
                "text": seg.text.strip(),
            }
            segments.append(seg_dict)
            full_text_parts.append(seg.text.strip())
            total_duration = max(total_duration, float(seg.end))

        return {
            "text": " ".join(full_text_parts),
            "segments": segments,
            "duration": total_duration,
            "language": getattr(info, "language", "unknown"),
        }

    def transcribe_video(self, video_path: str) -> Dict:
        """
        Extract audio from a video file and transcribe it.

        Returns: {text, segments, duration, language}
        """
        if not os.path.exists(video_path):
            raise RuntimeError(f"Video file not found: {video_path}")

        # Extract audio to a temp file
        tmp_dir = tempfile.mkdtemp(prefix="kairo_media_")
        audio_path = os.path.join(tmp_dir, "extracted_audio.wav")

        try:
            self.extract_audio(video_path, audio_path)
            return self.transcribe_audio(audio_path)
        finally:
            # Cleanup temp audio
            if os.path.exists(audio_path):
                os.remove(audio_path)
            if os.path.exists(tmp_dir):
                os.rmdir(tmp_dir)
