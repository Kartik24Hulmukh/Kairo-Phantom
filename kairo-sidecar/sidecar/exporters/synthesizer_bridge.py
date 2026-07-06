"""
Synthesizer Bridge for Kairo Phantom Domain 7.
Local, offline document-to-audio conversion using open-source dialogue generators (openbooklm/synthesizer + Piper TTS).

HONEST DEGRADATION:
  If the synthesizer module or TTS backend is unavailable, this bridge
  RAISES EngineUnavailableError — it NEVER writes a mock WAV file and
  claims success. The caller must handle the absence explicitly.
"""

import logging
import os
import subprocess
import tempfile

from sidecar.bridge_health import EngineUnavailableError, check_python_module

logger = logging.getLogger("kairo.sidecar.synthesizer_bridge")


class SynthesizerBridge:
    """Local, sovereign document-to-podcast TTS pipeline adapter."""

    def __init__(self, tts_backend: str = "piper") -> None:
        self.tts_backend = tts_backend

    def is_available(self) -> bool:
        """Check if the synthesizer module and TTS backend are available."""
        return check_python_module("synthesizer")

    def generate_audio(
        self,
        document_text: str,
        output_path: str,
        voice: str = "en_US-amy-medium",
    ) -> str:
        """
        Generate two-speaker dialogue-style audio overview 100% offline.

        Raises:
            EngineUnavailableError: If the synthesizer module is not installed.
                NEVER writes a mock WAV file.
        """
        logger.info(f"Synthesizing offline audio dialogue using local backend [{self.tts_backend}]")

        if not self.is_available():
            raise EngineUnavailableError(
                engine_name="synthesizer",
                message="Audio synthesis engine is not installed. Cannot generate audio.",
                install_hint="pip install synthesizer  (or install piper-tts for Piper backend)",
            )

        try:
            with tempfile.NamedTemporaryFile(
                suffix=".txt", mode="w", delete=False, encoding="utf-8"
            ) as f:
                f.write(document_text)
                temp_path = f.name

            cmd = [
                "python",
                "-m",
                "synthesizer",
                "--input",
                temp_path,
                "--output",
                output_path,
                "--tts",
                self.tts_backend,
                "--voice",
                voice,
                "--format",
                "dialogue",
            ]

            subprocess.run(
                cmd, check=True, timeout=180, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            os.unlink(temp_path)
            logger.info(f"Offline audio synthesis successful: {output_path}")
            return output_path
        except subprocess.CalledProcessError as e:
            raise EngineUnavailableError(
                engine_name="synthesizer",
                message=f"Audio synthesis failed: {e}. Engine present but execution error.",
                install_hint="Check synthesizer installation and TTS backend configuration.",
            ) from e
        except Exception as e:
            raise EngineUnavailableError(
                engine_name="synthesizer",
                message=f"Audio synthesis failed: {e}",
                install_hint="Check synthesizer installation and TTS backend configuration.",
            ) from e
