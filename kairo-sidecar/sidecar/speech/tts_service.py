"""
Domain 8: TTS Service for Kairo Phantom
========================================
Text-to-speech fallback chain:
  1. sherpa-onnx-offline-tts subprocess (Apache 2.0, 63MB model)
  2. pyttsx3 cross-platform TTS (MPL-2.0 compatible)
  3. Windows SAPI via PowerShell
  4. macOS say command
  5. Linux espeak-ng

The user NEVER sees engine names — this is Kairo's voice feedback.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

log = logging.getLogger("kairo.tts")


class TtsService:
    """
    Cross-platform TTS with sherpa-onnx as primary engine.

    Provides synchronous speak() method with automatic engine detection.
    """

    def __init__(self):
        self.active_engine: str = "none"
        self._sherpa_bin: Optional[Path] = self._find_sherpa_binary()
        self._pyttsx3_engine = None

    # ── Engine detection ──────────────────────────────────────────────────────

    def _find_sherpa_binary(self) -> Optional[Path]:
        """Find sherpa-onnx-offline-tts binary."""
        import shutil

        kairo_bin = Path.home() / ".kairo-phantom" / "bin"
        exe_name = (
            "sherpa-onnx-offline-tts.exe" if sys.platform == "win32" else "sherpa-onnx-offline-tts"
        )

        # Check Kairo-managed bin first
        kairo_candidate = kairo_bin / exe_name
        if kairo_candidate.exists():
            return kairo_candidate

        # Check system PATH
        found = shutil.which("sherpa-onnx-offline-tts")
        if found:
            return Path(found)

        return None

    def _sherpa_model_dir(self, voice: str) -> Optional[Path]:
        """Find sherpa-onnx model directory for given voice."""
        models_dir = Path.home() / ".kairo-phantom" / "models" / voice
        if models_dir.exists() and (models_dir / "model.onnx").exists():
            return models_dir
        return None

    def _has_sherpa(self, voice: str = "en_US-amy-medium") -> bool:
        return self._sherpa_bin is not None and self._sherpa_model_dir(voice) is not None

    def _has_pyttsx3(self) -> bool:
        try:
            import pyttsx3  # type: ignore  # noqa: F401

            return True
        except ImportError:
            return False

    # ── Speak implementations ─────────────────────────────────────────────────

    def _speak_via_sherpa(self, text: str, voice: str = "en_US-amy-medium") -> bool:
        """Speak using sherpa-onnx-offline-tts subprocess."""
        model_dir = self._sherpa_model_dir(voice)
        if not model_dir or not self._sherpa_bin:
            return False

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_wav = tmp.name

        try:
            result = subprocess.run(
                [
                    str(self._sherpa_bin),
                    f"--vits-model={model_dir / 'model.onnx'}",
                    f"--vits-lexicon={model_dir / 'lexicon.txt'}",
                    f"--vits-tokens={model_dir / 'tokens.txt'}",
                    f"--output-filename={tmp_wav}",
                    f"--text={text}",
                ],
                capture_output=True,
                timeout=30,
            )

            if result.returncode != 0:
                log.debug(f"sherpa-onnx failed: {result.stderr.decode()[:200]}")
                return False

            # Play the WAV
            return self._play_wav(tmp_wav)
        except Exception as e:
            log.debug(f"sherpa-onnx exception: {e}")
            return False
        finally:
            try:
                os.unlink(tmp_wav)
            except Exception:
                pass

    def _play_wav(self, wav_path: str) -> bool:
        """Play a WAV file using the platform's audio system."""
        try:
            if sys.platform == "win32":
                import winsound

                winsound.PlaySound(wav_path, winsound.SND_FILENAME)
                return True
            elif sys.platform == "darwin":
                subprocess.run(["afplay", wav_path], capture_output=True, timeout=30)
                return True
            else:
                # Linux: try aplay, then paplay, then sox
                for player in ["aplay", "paplay", "play"]:
                    if subprocess.run(["which", player], capture_output=True).returncode == 0:
                        subprocess.run([player, wav_path], capture_output=True, timeout=30)
                        return True
            return False
        except Exception:
            return False

    def _speak_via_pyttsx3(self, text: str) -> bool:
        """Speak using pyttsx3 (cross-platform, works offline)."""
        try:
            import pyttsx3  # type: ignore

            if self._pyttsx3_engine is None:
                self._pyttsx3_engine = pyttsx3.init()
                self._pyttsx3_engine.setProperty("rate", 175)
                self._pyttsx3_engine.setProperty("volume", 0.85)
            self._pyttsx3_engine.say(text)
            self._pyttsx3_engine.runAndWait()
            return True
        except Exception as e:
            log.debug(f"pyttsx3 failed: {e}")
            return False

    def _speak_via_sapi(self, text: str) -> bool:
        """Speak using Windows SAPI via PowerShell (fallback)."""
        if sys.platform != "win32":
            return False
        try:
            escaped = text.replace("'", "''")
            ps_cmd = (
                "Add-Type -AssemblyName System.Speech; "
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$s.Speak('{escaped}')"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                timeout=30,
            )
            return True
        except Exception as e:
            log.debug(f"SAPI failed: {e}")
            return False

    def _speak_via_say(self, text: str) -> bool:
        """Speak using macOS say command (fallback)."""
        if sys.platform != "darwin":
            return False
        try:
            subprocess.run(["say", text], capture_output=True, timeout=30)
            return True
        except Exception:
            return False

    def _speak_via_espeak(self, text: str) -> bool:
        """Speak using espeak-ng (Linux fallback)."""
        import shutil

        for bin_name in ["espeak-ng", "espeak"]:
            if shutil.which(bin_name):
                try:
                    subprocess.run([bin_name, text], capture_output=True, timeout=30)
                    return True
                except Exception:
                    pass
        return False

    # ── Public interface ──────────────────────────────────────────────────────

    def speak(self, text: str, voice: str = "en_US-amy-medium") -> bool:
        """
        Speak text using the best available TTS engine.

        Engine priority:
          1. sherpa-onnx-offline-tts (best quality, offline)
          2. pyttsx3 (cross-platform, offline)
          3. Windows SAPI
          4. macOS say
          5. Linux espeak-ng
        """
        if not text.strip():
            return True

        # 1. sherpa-onnx
        if self._has_sherpa(voice):
            if self._speak_via_sherpa(text, voice):
                self.active_engine = "sherpa-onnx"
                return True
            log.debug("sherpa-onnx failed, trying next engine")

        # 2. pyttsx3
        if self._has_pyttsx3():
            if self._speak_via_pyttsx3(text):
                self.active_engine = "pyttsx3"
                return True

        # 3. Platform-specific
        if sys.platform == "win32":
            if self._speak_via_sapi(text):
                self.active_engine = "sapi"
                return True
        elif sys.platform == "darwin":
            if self._speak_via_say(text):
                self.active_engine = "say"
                return True
        else:
            if self._speak_via_espeak(text):
                self.active_engine = "espeak"
                return True

        log.warning("TTS: No engine available. Text not spoken.")
        self.active_engine = "none"
        return False
