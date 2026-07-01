"""
Domain 8: Multimodal Input — Python Test Suite
===============================================
Tests for voice_bridge.py and screen_context_bridge.py sidecar modules.
"""

import os
import sys
import json
import tempfile
import pytest

# Add sidecar to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sidecar.voice_bridge import VoiceBridge
from sidecar.screen_context_bridge import ScreenContextBridge


# ── VoiceBridge Tests ────────────────────────────────────────────────────────


class TestVoiceBridge:
    """Tests for voice transcription post-processing."""

    def setup_method(self):
        self.bridge = VoiceBridge()

    @pytest.mark.asyncio
    async def test_empty_input(self):
        """Empty transcription returns empty result."""
        result = await self.bridge.post_process_transcription("")
        assert result["processed_text"] == ""
        assert result["command"] is None
        assert result["is_command"] is False
        assert result["confidence"] == 0.0

    @pytest.mark.asyncio
    async def test_filler_word_removal(self):
        """Filler words (um, uh, like) are removed from transcription."""
        result = await self.bridge.post_process_transcription(
            "um I want to uh write like a paragraph about testing"
        )
        text = result["processed_text"]
        assert "um" not in text.lower().split()
        assert "uh" not in text.lower().split()
        # "like" should be removed when used as filler
        assert "I want to write a paragraph about testing" in text or "want to write" in text

    @pytest.mark.asyncio
    async def test_punctuation_restoration(self):
        """Basic punctuation is added to unpunctuated text."""
        result = await self.bridge.post_process_transcription(
            "write me an email about project updates"
        )
        text = result["processed_text"]
        # Should end with punctuation
        assert text[-1] in ".!?"
        # Should start with capital
        assert text[0].isupper() or text.startswith("//")

    @pytest.mark.asyncio
    async def test_already_punctuated(self):
        """Already punctuated text is left unchanged."""
        result = await self.bridge.post_process_transcription(
            "Please write a summary of the document."
        )
        # Should not double-punctuate
        assert not result["processed_text"].endswith("..")

    @pytest.mark.asyncio
    async def test_command_detection_write(self):
        """'hey kairo write me an email' → '// write email'."""
        result = await self.bridge.post_process_transcription("hey kairo write me an email")
        assert result["is_command"] is True
        assert result["command"] is not None
        assert result["command"].startswith("//")
        assert "write" in result["command"].lower()

    @pytest.mark.asyncio
    async def test_command_detection_design(self):
        """'kairo design a header' → '// design a header'."""
        result = await self.bridge.post_process_transcription("kairo design a header")
        assert result["is_command"] is True
        assert "// design" in result["command"]

    @pytest.mark.asyncio
    async def test_command_detection_health(self):
        """'hey kairo health' → '// health'."""
        result = await self.bridge.post_process_transcription("hey kairo health")
        assert result["is_command"] is True
        assert result["command"] == "// health"

    @pytest.mark.asyncio
    async def test_non_command_text(self):
        """Regular text without 'kairo' prefix is not detected as command."""
        result = await self.bridge.post_process_transcription(
            "the meeting is at three o'clock today"
        )
        assert result["is_command"] is False
        assert result["command"] is None

    @pytest.mark.asyncio
    async def test_confidence_estimation(self):
        """Confidence is between 0 and 1."""
        result = await self.bridge.post_process_transcription(
            "write a paragraph about artificial intelligence and machine learning"
        )
        assert 0.0 <= result["confidence"] <= 1.0

    @pytest.mark.asyncio
    async def test_low_confidence_for_noise(self):
        """[blank_audio] markers lower confidence."""
        result = await self.bridge.post_process_transcription("[blank_audio] some text")
        assert result["confidence"] < 0.5

    @pytest.mark.asyncio
    async def test_format_voice_prompt_command(self):
        """Voice prompt with command is formatted correctly."""
        result = await self.bridge.format_voice_prompt("hey kairo write an email")
        assert "prompt" in result
        assert result["prompt"].startswith("//")
        assert result["mode"] == "command"

    @pytest.mark.asyncio
    async def test_format_voice_prompt_default(self):
        """Non-command voice prompt wrapped as // voice."""
        result = await self.bridge.format_voice_prompt("the weather is nice today")
        assert "prompt" in result
        assert result["prompt"].startswith("//")

    @pytest.mark.asyncio
    async def test_format_voice_prompt_dictation(self):
        """Dictation mode outputs raw text."""
        result = await self.bridge.format_voice_prompt(
            "the weather is nice today", mode="dictation"
        )
        assert not result["prompt"].startswith("//")


# ── ScreenContextBridge Tests ────────────────────────────────────────────────


class TestScreenContextBridge:
    """Tests for screen context extraction."""

    def setup_method(self):
        self.bridge = ScreenContextBridge()

    @pytest.mark.asyncio
    async def test_missing_image(self):
        """Non-existent image returns error."""
        result = await self.bridge.extract_context("/nonexistent/path/to/image.png")
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_empty_path(self):
        """Empty path returns error."""
        result = await self.bridge.extract_context("")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_valid_image_metadata_fallback(self):
        """Real image file returns at least metadata context."""
        # Create a temp BMP file
        with tempfile.NamedTemporaryFile(suffix=".bmp", delete=False) as f:
            # Write minimal BMP header
            f.write(b"BM")
            f.write(b"\x00" * 52)  # Minimal valid-ish BMP
            temp_path = f.name

        try:
            result = await self.bridge.extract_context(temp_path)
            assert result["success"] is True
            assert result["method"] in ("farscry", "tesseract", "metadata")
            assert result["text"]  # Should have some text
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_app_context_passthrough(self):
        """App context is passed through to result."""
        with tempfile.NamedTemporaryFile(suffix=".bmp", delete=False) as f:
            f.write(b"BM" + b"\x00" * 52)
            temp_path = f.name

        try:
            result = await self.bridge.extract_context(temp_path, {"app_name": "Microsoft Word"})
            assert result["app_name"] == "Microsoft Word"
        finally:
            os.unlink(temp_path)


# ── Sidecar Routing Tests ────────────────────────────────────────────────────


class TestSidecarRouting:
    """Tests for action routing in main.py handle_request."""

    @pytest.mark.asyncio
    async def test_voice_process_routing(self):
        """voice_process action routes correctly."""
        # Import handle_request
        from sidecar.main import handle_request

        result = await handle_request(
            {
                "id": "test-voice-1",
                "action": "voice_process",
                "path": "",
                "payload": {
                    "transcription": "hey kairo write an email",
                    "app_context": {"app": "test"},
                },
            }
        )

        assert result["ok"] is True
        assert "data" in result
        assert result["data"]["is_command"] is True

    @pytest.mark.asyncio
    async def test_voice_format_routing(self):
        """voice_format action routes correctly."""
        from sidecar.main import handle_request

        result = await handle_request(
            {
                "id": "test-voice-2",
                "action": "voice_format",
                "path": "",
                "payload": {
                    "transcription": "write a summary",
                    "mode": "ghost_write",
                },
            }
        )

        assert result["ok"] is True
        assert "data" in result
        assert "prompt" in result["data"]

    @pytest.mark.asyncio
    async def test_screen_extract_routing(self):
        """screen_extract action routes correctly (missing file graceful)."""
        from sidecar.main import handle_request

        result = await handle_request(
            {
                "id": "test-screen-1",
                "action": "screen_extract",
                "path": "",
                "payload": {
                    "image_path": "/nonexistent/screenshot.bmp",
                    "app_context": {"app_name": "Test"},
                },
            }
        )

        # Should not crash — returns ok=False for missing file
        assert result["ok"] is False or "error" in result.get("data", {})


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])


# ═══════════════════════════════════════════════════════════════════════════════
# Domain 8 Extended: Moonshine / TTS / Wake Word Tests
# ═══════════════════════════════════════════════════════════════════════════════

import struct
from unittest.mock import AsyncMock, MagicMock, patch


def _make_wav_bytes(duration_secs: float = 0.5, sample_rate: int = 16000) -> bytes:
    """Return bytes of a minimal valid WAV file with silence."""
    num_samples = int(sample_rate * duration_secs)
    data_size = num_samples * 2  # 16-bit PCM
    file_size = 36 + data_size
    buf = (
        b"RIFF"
        + struct.pack("<I", file_size)
        + b"WAVE"
        + b"fmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16)
        + b"data"
        + struct.pack("<I", data_size)
        + b"\x00" * data_size
    )
    return buf


def _write_wav(path: str, duration_secs: float = 0.5) -> None:
    with open(path, "wb") as f:
        f.write(_make_wav_bytes(duration_secs))


class TestMoonshineServiceHelpers:
    """Tests for moonshine_service internal helper functions."""

    def test_confidence_empty(self):
        from sidecar.speech.moonshine_service import _estimate_confidence

        assert _estimate_confidence("", 1.0) == 0.0

    def test_confidence_normal_speech(self):
        from sidecar.speech.moonshine_service import _estimate_confidence

        score = _estimate_confidence(
            "Hello this is a test of the Kairo voice dictation system", 3.0
        )
        assert score > 0.6, f"Expected > 0.6, got {score}"

    def test_confidence_repetitive_text_penalized(self):
        from sidecar.speech.moonshine_service import _estimate_confidence

        score = _estimate_confidence("the the the the the the the the the", 4.0)
        assert score < 0.4, f"Repetitive text should score < 0.4, got {score}"

    def test_confidence_noise_markers(self):
        from sidecar.speech.moonshine_service import _estimate_confidence

        score = _estimate_confidence("[blank_audio]", 3.0)
        assert score < 0.3

    def test_detect_language_english(self):
        from sidecar.speech.moonshine_service import _detect_language

        assert _detect_language("Hello world this is a test") == "en"

    def test_detect_language_empty(self):
        from sidecar.speech.moonshine_service import _detect_language

        assert _detect_language("") == "en"

    def test_detect_language_cjk(self):
        from sidecar.speech.moonshine_service import _detect_language

        assert _detect_language("你好世界") == "zh"

    def test_detect_language_arabic(self):
        from sidecar.speech.moonshine_service import _detect_language

        assert _detect_language("مرحبا بالعالم") == "ar"

    def test_detect_language_cyrillic(self):
        from sidecar.speech.moonshine_service import _detect_language

        assert _detect_language("Привет мир") == "ru"


class TestMoonshineClient:
    """Tests for the MoonshineClient HTTP wrapper."""

    def test_default_url(self):
        from sidecar.voice_bridge import MoonshineClient

        assert MoonshineClient().service_url == "http://localhost:7439"

    def test_custom_url(self):
        from sidecar.voice_bridge import MoonshineClient

        client = MoonshineClient("http://localhost:9999/")
        assert client.service_url == "http://localhost:9999"  # strips trailing slash

    def test_is_available_unreachable(self):
        from sidecar.voice_bridge import MoonshineClient

        client = MoonshineClient("http://localhost:39998")  # unused port
        assert client.is_available() is False

    @pytest.mark.asyncio
    async def test_transcribe_file_missing(self):
        from sidecar.voice_bridge import MoonshineClient

        result = await MoonshineClient().transcribe_file("/tmp/does_not_exist_12345678.wav")
        assert result is None

    @pytest.mark.asyncio
    async def test_transcribe_file_mocked(self):
        from sidecar.voice_bridge import MoonshineClient

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name
        try:
            _write_wav(wav_path)
            mock_resp_data = json.dumps(
                {
                    "text": "mocked transcription",
                    "confidence": 0.88,
                    "language": "en",
                    "duration_ms": 120.0,
                }
            ).encode()
            mock_resp = MagicMock()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.read = MagicMock(return_value=mock_resp_data)

            with patch("urllib.request.urlopen", return_value=mock_resp):
                result = await MoonshineClient().transcribe_file(wav_path)

            assert result is not None
            assert result["text"] == "mocked transcription"
            assert abs(result["confidence"] - 0.88) < 0.001
        finally:
            os.unlink(wav_path)

    def test_get_languages_fallback(self):
        from sidecar.voice_bridge import MoonshineClient

        langs = MoonshineClient("http://localhost:39998").get_supported_languages()
        assert langs == ["en"]


class TestTranscribeFallback:
    """Tests for transcribe_with_moonshine_or_fallback."""

    @pytest.mark.asyncio
    async def test_moonshine_primary_success(self):
        from sidecar.voice_bridge import transcribe_with_moonshine_or_fallback

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name
        try:
            _write_wav(wav_path)
            with patch(
                "sidecar.voice_bridge.MoonshineClient.transcribe_file",
                new_callable=AsyncMock,
                return_value={"text": "hello world", "confidence": 0.92, "language": "en"},
            ):
                result = await transcribe_with_moonshine_or_fallback(
                    wav_path, confidence_threshold=0.6
                )
            assert result["engine"] == "moonshine"
            assert result["text"] == "hello world"
        finally:
            os.unlink(wav_path)

    @pytest.mark.asyncio
    async def test_low_confidence_triggers_whisper(self):
        from sidecar.voice_bridge import transcribe_with_moonshine_or_fallback

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name
        try:
            _write_wav(wav_path)
            with (
                patch(
                    "sidecar.voice_bridge.MoonshineClient.transcribe_file",
                    new_callable=AsyncMock,
                    return_value={"text": "mumble", "confidence": 0.2, "language": "en"},
                ),
                patch(
                    "sidecar.voice_bridge._transcribe_with_whisper_cli",
                    return_value="hello from whisper fallback",
                ),
            ):
                result = await transcribe_with_moonshine_or_fallback(wav_path)
            assert result["engine"] == "whisper"
            assert "fallback_reason" in result
        finally:
            os.unlink(wav_path)

    @pytest.mark.asyncio
    async def test_both_fail_returns_none_engine(self):
        from sidecar.voice_bridge import transcribe_with_moonshine_or_fallback

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name
        try:
            _write_wav(wav_path)
            with (
                patch(
                    "sidecar.voice_bridge.MoonshineClient.transcribe_file",
                    new_callable=AsyncMock,
                    return_value=None,
                ),
                patch(
                    "sidecar.voice_bridge._transcribe_with_whisper_cli",
                    return_value=None,
                ),
            ):
                result = await transcribe_with_moonshine_or_fallback(wav_path)
            assert result["engine"] == "none"
            assert result["text"] == ""
        finally:
            os.unlink(wav_path)

    @pytest.mark.asyncio
    async def test_moonshine_unavailable_whisper_succeeds(self):
        from sidecar.voice_bridge import transcribe_with_moonshine_or_fallback

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name
        try:
            _write_wav(wav_path)
            with (
                patch(
                    "sidecar.voice_bridge.MoonshineClient.transcribe_file",
                    new_callable=AsyncMock,
                    return_value=None,
                ),
                patch(
                    "sidecar.voice_bridge._transcribe_with_whisper_cli",
                    return_value="whisper fallback text",
                ),
            ):
                result = await transcribe_with_moonshine_or_fallback(wav_path)
            assert result["engine"] == "whisper"
            assert result["fallback_reason"] == "moonshine_unavailable"
        finally:
            os.unlink(wav_path)


class TestTtsService:
    """Tests for cross-platform TtsService."""

    def test_import(self):
        from sidecar.speech.tts_service import TtsService

        assert TtsService is not None

    def test_speak_empty_is_noop(self):
        from sidecar.speech.tts_service import TtsService

        svc = TtsService()
        assert svc.speak("") is True

    def test_speak_all_engines_fail(self):
        from sidecar.speech.tts_service import TtsService

        svc = TtsService()
        with (
            patch.object(svc, "_has_sherpa", return_value=False),
            patch.object(svc, "_has_pyttsx3", return_value=False),
            patch.object(svc, "_speak_via_sapi", return_value=False),
            patch.object(svc, "_speak_via_say", return_value=False),
            patch.object(svc, "_speak_via_espeak", return_value=False),
        ):
            result = svc.speak("test speech")
        assert result is False
        assert svc.active_engine == "none"

    def test_speak_sherpa_primary(self):
        from sidecar.speech.tts_service import TtsService

        svc = TtsService()
        with (
            patch.object(svc, "_has_sherpa", return_value=True),
            patch.object(svc, "_speak_via_sherpa", return_value=True),
        ):
            result = svc.speak("hello world")
        assert result is True
        assert svc.active_engine == "sherpa-onnx"


class TestWakeWordService:
    """Tests for wake_word_service.py."""

    def test_import(self):
        from sidecar.speech.wake_word_service import WakeWordDetector, FallbackWakeWordDetector

        assert WakeWordDetector is not None
        assert FallbackWakeWordDetector is not None

    def test_init_defaults(self):
        from sidecar.speech.wake_word_service import WakeWordDetector

        d = WakeWordDetector()
        assert 0.0 <= d.sensitivity <= 1.0
        assert d.cooldown_secs > 0

    def test_check_detection_below_threshold(self):
        from sidecar.speech.wake_word_service import WakeWordDetector

        d = WakeWordDetector(sensitivity=0.5)  # threshold ≈ 0.6
        assert d._check_detection({"hey_jarvis": 0.1}) is None

    def test_check_detection_above_threshold(self):
        from sidecar.speech.wake_word_service import WakeWordDetector

        d = WakeWordDetector(sensitivity=0.5)
        result = d._check_detection({"hey_jarvis": 0.95})
        assert result is not None
        assert abs(result - 0.95) < 0.01

    def test_check_detection_empty(self):
        from sidecar.speech.wake_word_service import WakeWordDetector

        d = WakeWordDetector()
        assert d._check_detection({}) is None


class TestDomain8SidecarActions:
    """Tests for new sidecar action handlers added in Domain 8."""

    @pytest.mark.asyncio
    async def test_moonshine_health_action(self):
        from sidecar.main import handle_request

        with patch("sidecar.voice_bridge.MoonshineClient.is_available", return_value=False):
            result = await handle_request(
                {
                    "id": "d8-001",
                    "action": "moonshine_health",
                    "payload": {"moonshine_url": "http://localhost:39999"},
                }
            )
        assert result["ok"] is True
        assert result["data"]["available"] is False
        assert isinstance(result["data"]["supported_languages"], list)

    @pytest.mark.asyncio
    async def test_moonshine_transcribe_action(self):
        from sidecar.main import handle_request

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name
        try:
            _write_wav(wav_path)
            mock_result = {
                "text": "hello from the sidecar test",
                "engine": "moonshine",
                "confidence": 0.91,
                "language": "en",
            }
            with patch(
                "sidecar.voice_bridge.transcribe_with_moonshine_or_fallback",
                new_callable=AsyncMock,
                return_value=mock_result,
            ):
                result = await handle_request(
                    {
                        "id": "d8-002",
                        "action": "moonshine_transcribe",
                        "payload": {"wav_path": wav_path},
                    }
                )
            assert result["ok"] is True
            assert result["data"]["engine"] == "moonshine"
        finally:
            os.unlink(wav_path)

    @pytest.mark.asyncio
    async def test_tts_speak_empty_skipped(self):
        from sidecar.main import handle_request

        result = await handle_request(
            {
                "id": "d8-003",
                "action": "tts_speak",
                "payload": {"text": ""},
            }
        )
        assert result["ok"] is True
        assert result["data"]["skipped"] is True

    @pytest.mark.asyncio
    async def test_unknown_action_returns_error(self):
        from sidecar.main import handle_request

        result = await handle_request(
            {
                "id": "d8-999",
                "action": "nonexistent_domain8_xyz",
                "payload": {},
            }
        )
        assert result["ok"] is False
        assert "Unknown action" in result["error"]
