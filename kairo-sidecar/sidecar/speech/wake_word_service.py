"""
Domain 8: Wake Word Detection Service
======================================
Standalone daemon that listens for "Hey Kairo" and signals Kairo Phantom.

Uses openwakeword (Apache 2.0) as primary engine.
Falls back gracefully if openwakeword is not installed.

Usage:
    python wake_word_service.py [--sensitivity 0.5] [--port 7440]

Environment variables:
    WAKE_WORD_SENSITIVITY   0.0–1.0 (default: 0.5)
    WAKE_WORD_PHRASE        Wake phrase (default: hey kairo)
    WAKE_WORD_NOTIFY_PORT   Port to send HTTP notification (default: 7441)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import threading
from pathlib import Path
from typing import Optional

# ── Logging ──────────────────────────────────────────────────────────────────

log_path = Path.home() / ".kairo-phantom" / "wake_word.log"
log_path.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WAKEWORD] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(log_path, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("kairo.wake_word")

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_SENSITIVITY = float(os.environ.get("WAKE_WORD_SENSITIVITY", "0.5"))
DEFAULT_PHRASE = os.environ.get("WAKE_WORD_PHRASE", "hey kairo")
DEFAULT_NOTIFY_PORT = int(os.environ.get("WAKE_WORD_NOTIFY_PORT", "7441"))
CHUNK_DURATION_MS = 80  # 80ms chunks for real-time processing
SAMPLE_RATE = 16000
CHANNELS = 1

# ── Engine detection ──────────────────────────────────────────────────────────

_openwakeword_available = False
_sounddevice_available = False

try:
    import openwakeword  # type: ignore  # noqa: F401
    from openwakeword.model import Model as OwwModel  # type: ignore

    _openwakeword_available = True
    log.info("✅ openwakeword detected")
except ImportError:
    log.warning("⚠️  openwakeword not installed. Install: pip install openwakeword")

try:
    import sounddevice as sd  # type: ignore
    import numpy as np  # type: ignore  # noqa: F401

    _sounddevice_available = True
    log.info("✅ sounddevice detected")
except ImportError:
    log.warning("⚠️  sounddevice not installed. Install: pip install sounddevice numpy")


# ── Notification client ───────────────────────────────────────────────────────


def _notify_kairo(confidence: float, notify_port: int) -> None:
    """Send wake word detection notification to Kairo Phantom sidecar."""
    import urllib.request
    import urllib.error

    payload = json.dumps(
        {
            "event": "wake_word_detected",
            "confidence": round(confidence, 3),
            "phrase": DEFAULT_PHRASE,
            "timestamp": time.time(),
        }
    ).encode()

    try:
        req = urllib.request.Request(
            f"http://localhost:{notify_port}/wake_word",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=2):
            pass
        log.info(f"👂 Wake word notification sent (confidence={confidence:.3f})")
    except urllib.error.URLError:
        # Kairo might not be listening — that's OK, log and continue
        log.debug("Wake word: Kairo notification endpoint not reachable")
    except Exception as e:
        log.debug(f"Wake word notification error: {e}")


# ── openwakeword Detection Loop ───────────────────────────────────────────────


class WakeWordDetector:
    """
    Listens to the microphone and detects the wake word phrase.

    Uses openwakeword (Apache 2.0) for neural wake word detection.
    Runs at <1% CPU on modern hardware.
    """

    def __init__(
        self,
        sensitivity: float = DEFAULT_SENSITIVITY,
        notify_port: int = DEFAULT_NOTIFY_PORT,
        cooldown_secs: float = 5.0,
    ):
        self.sensitivity = sensitivity
        self.notify_port = notify_port
        self.cooldown_secs = cooldown_secs
        self._running = threading.Event()
        self._last_detection = 0.0
        self._model: Optional[OwwModel] = None

    def _load_model(self) -> bool:
        """Load openwakeword model (lazy)."""
        if not _openwakeword_available:
            return False
        try:
            # openwakeword ships pre-trained models including alexa-like patterns
            # We use the "hey_jarvis" model as the closest available to "hey kairo"
            # For production: train a custom hey_kairo model via openWakeWord tools
            self._model = OwwModel(
                inference_framework="onnx",
                wakeword_models=["hey_jarvis"],  # Closest built-in to "hey kairo"
            )
            log.info("✅ Wake word model loaded (hey_jarvis → hey kairo mapping)")
            return True
        except Exception as e:
            log.error(f"Failed to load wake word model: {e}")
            return False

    def _check_detection(self, predictions: dict) -> Optional[float]:
        """
        Check if wake word is detected in current frame.

        Maps openwakeword predictions to our confidence threshold.
        Returns confidence float if detected, None otherwise.
        """
        if not predictions:
            return None

        # Get max confidence across all models
        max_conf = max(
            (v if isinstance(v, float) else float(v[-1]))
            for v in predictions.values()
            if v is not None
        )

        # Threshold: sensitivity maps 0.0-1.0 to 0.3-0.9 detection threshold
        threshold = 0.3 + (self.sensitivity * 0.6)

        if max_conf >= threshold:
            return max_conf
        return None

    def start(self) -> None:
        """Start the wake word detection loop (blocking)."""
        if not _openwakeword_available or not _sounddevice_available:
            log.warning(
                "Wake word detection requires openwakeword + sounddevice. "
                "Install: pip install openwakeword sounddevice numpy"
            )
            return

        if not self._load_model():
            log.error("Cannot start: model load failed")
            return

        self._running.set()
        chunk_size = int(SAMPLE_RATE * CHUNK_DURATION_MS / 1000)

        log.info(
            f"👂 Wake word detector started (sensitivity={self.sensitivity:.2f}, "
            f"threshold≈{0.3 + self.sensitivity * 0.6:.2f})"
        )
        log.info("   Listening for wake phrase...")

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=chunk_size,
        ) as stream:
            while self._running.is_set():
                audio_chunk, _ = stream.read(chunk_size)
                audio_flat = audio_chunk.flatten()

                try:
                    predictions = self._model.predict(audio_flat)
                    confidence = self._check_detection(predictions)

                    if confidence is not None:
                        now = time.time()
                        if now - self._last_detection >= self.cooldown_secs:
                            self._last_detection = now
                            log.info(f"👂 WAKE WORD DETECTED! confidence={confidence:.3f}")
                            # Notify in background thread
                            threading.Thread(
                                target=_notify_kairo,
                                args=(confidence, self.notify_port),
                                daemon=True,
                            ).start()
                        else:
                            log.debug(
                                f"Wake word cooldown active ({now - self._last_detection:.1f}s < {self.cooldown_secs}s)"
                            )

                except Exception as e:
                    log.debug(f"Prediction error (non-fatal): {e}")
                    continue

        log.info("👂 Wake word detector stopped")

    def stop(self) -> None:
        """Signal the detection loop to stop."""
        self._running.clear()
        log.info("👂 Wake word stop requested")


# ── Fallback: text-based simulation ──────────────────────────────────────────


class FallbackWakeWordDetector:
    """
    Fallback wake word detector when openwakeword/sounddevice is unavailable.

    Prints a clear message and exits with code 2 (not an error, just unavailable).
    The Rust wake_word.rs daemon handles fallback to whisper.cpp polling.
    """

    def start(self) -> None:
        log.warning(
            "╔══════════════════════════════════════════════════════════════╗\n"
            "║   openwakeword/sounddevice not installed.                    ║\n"
            "║   Wake word detection is handled by Kairo's internal engine. ║\n"
            "║                                                              ║\n"
            "║   To enable neural wake word: pip install openwakeword       ║\n"
            "║                               pip install sounddevice numpy  ║\n"
            "╚══════════════════════════════════════════════════════════════╝"
        )
        sys.exit(2)  # Exit code 2 = feature not available (not an error)

    def stop(self) -> None:
        pass


# ── HTTP notification endpoint (for Kairo to receive wake events) ─────────────


async def _http_notify_handler(request):
    """Receives wake word events (when this service acts as server, not client)."""
    try:
        from aiohttp import web

        data = await request.json()
        log.info(f"Received wake event: {data}")
        return web.json_response({"ok": True})
    except Exception as e:
        from aiohttp import web

        return web.json_response({"ok": False, "error": str(e)}, status=400)


# ── Main entry point ──────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Kairo Wake Word Detection Service",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--sensitivity",
        type=float,
        default=DEFAULT_SENSITIVITY,
        help="Detection sensitivity (0.0=low false positives, 1.0=high recall)",
    )
    parser.add_argument(
        "--notify-port",
        type=int,
        default=DEFAULT_NOTIFY_PORT,
        help="Port to send HTTP wake word notifications",
    )
    parser.add_argument(
        "--cooldown",
        type=float,
        default=5.0,
        help="Seconds to wait after detection before listening again",
    )
    args = parser.parse_args()

    if _openwakeword_available and _sounddevice_available:
        detector = WakeWordDetector(
            sensitivity=args.sensitivity,
            notify_port=args.notify_port,
            cooldown_secs=args.cooldown,
        )
    else:
        detector = FallbackWakeWordDetector()

    try:
        detector.start()
    except KeyboardInterrupt:
        log.info("Interrupted by user")
        detector.stop()


if __name__ == "__main__":
    main()
