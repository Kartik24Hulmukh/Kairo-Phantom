"""
Domain 8: Moonshine Voice Transcription Service
================================================
Standalone HTTP sidecar (port 7439) for Kairo Phantom.
Provides offline speech-to-text via Moonshine Voice (MIT license).

The user NEVER sees "Moonshine" — this is Kairo Voice Dictation™.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import time
import tempfile
from pathlib import Path
from typing import Optional, Tuple

# ── Logging ──────────────────────────────────────────────────────────────────

log_path = Path.home() / ".kairo-phantom" / "moonshine.log"
log_path.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MOONSHINE] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(log_path, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("kairo.moonshine")

# ── Moonshine model (lazy-loaded) ─────────────────────────────────────────────

_moonshine_model = None
_model_name: str = "moonshine/moonshine-base"
_model_loaded: bool = False
_moonshine_available: bool = False

try:
    from aiohttp import web

    _aiohttp_available = True
except ImportError:
    log.error("aiohttp not installed: pip install aiohttp")
    _aiohttp_available = False


def _try_load_moonshine(model_name: str = "moonshine/moonshine-base") -> bool:
    """Attempt to import and initialise Moonshine model. Returns True on success."""
    global _moonshine_model, _model_loaded, _moonshine_available, _model_name

    if _model_loaded:
        return _moonshine_available

    _model_name = model_name
    log.info(f"Loading Moonshine model: {model_name}")

    try:
        # Try moonshine-voice package first (MIT)
        try:
            from moonshine_onnx import MoonshineOnnxModel  # type: ignore

            _moonshine_model = MoonshineOnnxModel(model=model_name)
            _moonshine_available = True
            log.info(f"✅ Moonshine ONNX model loaded: {model_name}")
        except ImportError:
            # Try the PyPI moonshine package
            import moonshine  # type: ignore

            _moonshine_model = moonshine.load(model_name)
            _moonshine_available = True
            log.info(f"✅ Moonshine model loaded: {model_name}")

    except ImportError as e:
        log.warning(
            f"⚠️  Moonshine not installed ({e}). "
            "Install with: pip install moonshine-onnx  OR  pip install moonshine-voice"
        )
        _moonshine_available = False
    except Exception as e:
        log.error(f"❌ Failed to load Moonshine model: {e}")
        _moonshine_available = False

    _model_loaded = True
    return _moonshine_available


def _estimate_confidence(text: str, duration_secs: float) -> float:
    """
    Heuristic confidence score (0.0–1.0) based on transcription quality.

    Real Moonshine returns confidence via CTC decoder — this is a fallback
    for implementations that don't expose per-token logprobs.
    """
    if not text.strip():
        return 0.0

    score = 1.0
    words = text.split()
    word_count = len(words)

    # Very few words for duration → likely noise
    if duration_secs > 2.0 and word_count < 2:
        score *= 0.4

    # Repetition → likely hallucination
    if word_count > 2:
        unique_ratio = len(set(w.lower() for w in words)) / word_count
        if unique_ratio < 0.4:
            score *= 0.3

    # Whisper artefact markers
    noise_markers = ["[inaudible]", "[noise]", "[blank_audio]", "[music]"]
    if any(m in text.lower() for m in noise_markers):
        score *= 0.2

    # Short text
    if word_count < 3:
        score *= 0.7

    return round(min(max(score, 0.0), 1.0), 3)


def _detect_language(text: str) -> str:
    """
    Lightweight English detection heuristic.
    Returns ISO-639-1 code. Moonshine base only supports 'en'.
    """
    if not text.strip():
        return "en"

    # ASCII ratio: English is almost always >85% ASCII
    ascii_count = sum(1 for c in text if ord(c) < 128)
    if len(text) > 0 and ascii_count / len(text) > 0.85:
        return "en"

    # Check for common non-Latin scripts
    cjk_ranges = [(0x4E00, 0x9FFF), (0x3040, 0x30FF), (0x1100, 0x11FF)]
    arabic_range = (0x0600, 0x06FF)
    cyrillic_range = (0x0400, 0x04FF)

    for char in text:
        cp = ord(char)
        for start, end in cjk_ranges:
            if start <= cp <= end:
                return "zh"
        if arabic_range[0] <= cp <= arabic_range[1]:
            return "ar"
        if cyrillic_range[0] <= cp <= cyrillic_range[1]:
            return "ru"

    return "en"


def _transcribe_with_moonshine(wav_path: str) -> Tuple[str, float, str, float]:
    """
    Transcribe a WAV file using the loaded Moonshine model.

    Returns (text, confidence, language, duration_ms).
    """
    t0 = time.perf_counter()

    if not _moonshine_available or _moonshine_model is None:
        raise RuntimeError("Moonshine model not loaded")

    try:
        # moonshine-onnx API
        if hasattr(_moonshine_model, "transcribe"):
            result = _moonshine_model.transcribe(wav_path)
            if isinstance(result, dict):
                text = result.get("text", "")
                confidence = result.get("confidence", _estimate_confidence(text, 5.0))
            else:
                text = str(result)
                confidence = _estimate_confidence(text, 5.0)
        else:
            # Generic call
            text = str(_moonshine_model(wav_path))
            confidence = _estimate_confidence(text, 5.0)

    except Exception as e:
        log.error(f"Moonshine transcription error: {e}")
        raise

    duration_ms = (time.perf_counter() - t0) * 1000
    language = _detect_language(text)

    return text.strip(), confidence, language, duration_ms


# ── HTTP Handlers ─────────────────────────────────────────────────────────────


async def handle_transcribe(request) -> "web.Response":
    """
    POST /transcribe

    Accepts JSON body:
      {"audio_path": "/path/to/audio.wav"}

    OR multipart form:
      audio=<wav bytes>

    Returns:
      {"text": "...", "confidence": 0.87, "language": "en",
       "speaker_id": null, "duration_ms": 107, "model": "moonshine-base"}
    """
    from aiohttp import web

    # Lazy-load model on first request
    if not _model_loaded:
        _try_load_moonshine(_model_name)

    if not _moonshine_available:
        return web.json_response(
            {
                "error": "Moonshine model not available",
                "install": "pip install moonshine-onnx",
                "text": "",
                "confidence": 0.0,
                "language": "en",
                "speaker_id": None,
                "duration_ms": 0,
                "model": _model_name,
            },
            status=503,
        )

    wav_path: Optional[str] = None
    tmp_path: Optional[str] = None

    try:
        content_type = request.content_type or ""

        if "multipart" in content_type:
            # Handle uploaded audio bytes
            reader = await request.multipart()
            async for part in reader:
                if part.name == "audio":
                    audio_bytes = await part.read()
                    with tempfile.NamedTemporaryFile(
                        suffix=".wav", delete=False, dir=str(log_path.parent / "tmp")
                    ) as tmp:
                        tmp.write(audio_bytes)
                        tmp_path = tmp.name
                    wav_path = tmp_path
                    break
        else:
            # JSON body with audio_path
            try:
                body = await request.json()
                wav_path = body.get("audio_path", "")
            except Exception:
                return web.json_response(
                    {"error": "Invalid request body — expected JSON with audio_path"},
                    status=400,
                )

        if not wav_path or not os.path.exists(wav_path):
            return web.json_response(
                {"error": f"WAV file not found: {wav_path}"},
                status=400,
            )

        # Run transcription in thread pool (CPU-bound)
        loop = asyncio.get_event_loop()
        text, confidence, language, duration_ms = await loop.run_in_executor(
            None, _transcribe_with_moonshine, wav_path
        )

        log.info(
            f"Transcribed in {duration_ms:.0f}ms | "
            f"conf={confidence:.2f} lang={language} | "
            f"'{text[:80]}'"
        )

        return web.json_response(
            {
                "text": text,
                "confidence": confidence,
                "language": language,
                "speaker_id": None,  # Future: speaker diarization
                "duration_ms": round(duration_ms, 1),
                "model": _model_name,
            }
        )

    except Exception as e:
        log.error(f"Transcription error: {e}")
        return web.json_response({"error": str(e)}, status=500)

    finally:
        # Clean up temp file if created
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


async def handle_health(request) -> "web.Response":
    """GET /health — service health check."""
    from aiohttp import web

    if not _model_loaded:
        # Trigger load on first health check
        _try_load_moonshine(_model_name)

    return web.json_response(
        {
            "status": "ok" if _moonshine_available else "degraded",
            "model": _model_name,
            "loaded": _moonshine_available,
            "service": "kairo-voice-transcription",
        }
    )


async def handle_languages(request) -> "web.Response":
    """GET /languages — supported languages."""
    from aiohttp import web

    # Moonshine base: English only. Medium: +partial multilingual.
    supported = ["en"]
    if "medium" in _model_name:
        # Medium model has limited multilingual capability
        supported = ["en", "es", "fr", "de", "it", "pt", "nl", "ru"]

    return web.json_response(
        {
            "supported": supported,
            "primary": "en",
            "note": "Non-English input will be processed but may have lower accuracy. "
            "whisper.cpp fallback is recommended for non-English.",
        }
    )


def create_app():
    """Create and configure the aiohttp application."""
    from aiohttp import web

    app = web.Application()
    app.router.add_post("/transcribe", handle_transcribe)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/languages", handle_languages)
    return app


def main():
    """Entry point for standalone execution."""
    if not _aiohttp_available:
        print("ERROR: aiohttp not installed. Run: pip install aiohttp")
        raise SystemExit(1)

    parser = argparse.ArgumentParser(
        description="Kairo Voice Transcription Service",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--port", type=int, default=7439, help="HTTP port")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    parser.add_argument(
        "--model",
        default="moonshine/moonshine-base",
        help="Moonshine model name (moonshine-base=26MB, moonshine-medium=245MB)",
    )
    parser.add_argument(
        "--preload",
        action="store_true",
        help="Load model at startup (rather than first request)",
    )
    args = parser.parse_args()

    global _model_name
    _model_name = args.model

    # Pre-load model if requested
    if args.preload:
        log.info("Pre-loading model...")
        _try_load_moonshine(args.model)

    from aiohttp import web

    app = create_app()
    log.info(f"Starting Kairo Voice Transcription Service on {args.host}:{args.port}")
    log.info(f"Model: {args.model} | Pre-loaded: {args.preload}")

    web.run_app(app, host=args.host, port=args.port, print=log.info)


if __name__ == "__main__":
    main()
