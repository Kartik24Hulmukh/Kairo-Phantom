"""
Domain 8: Voice Processing Bridge
==================================
Python sidecar module for post-processing whisper.cpp transcriptions.

Handles:
- Punctuation restoration
- Filler word removal ("um", "uh", "like", etc.)
- Command detection ("write me an email" → "// write email")
- Context formatting for the ghost-write pipeline
"""

import re
import json
import os
import subprocess
import urllib.request
import urllib.error
from typing import Dict, Optional


class VoiceBridge:
    """Post-processes voice transcriptions for the Kairo ghost-write pipeline."""

    # Common filler words to remove from transcriptions
    FILLER_WORDS = {
        "um",
        "uh",
        "uhm",
        "hmm",
        "hm",
        "er",
        "ah",
        "like",
        "you know",
        "i mean",
        "basically",
        "literally",
        "actually",
        "so basically",
        "kind of",
        "sort of",
    }

    # Voice command patterns → Kairo command mode mappings
    COMMAND_PATTERNS = [
        (r"^(?:hey kairo|kairo)\s*,?\s*write\s+(?:me\s+)?(?:an?\s+)?(.+)", "// write {0}"),
        (r"^(?:hey kairo|kairo)\s*,?\s*design\s+(.+)", "// design {0}"),
        (r"^(?:hey kairo|kairo)\s*,?\s*check\s+(.+)", "// check {0}"),
        (r"^(?:hey kairo|kairo)\s*,?\s*explain\s+(.+)", "// explain {0}"),
        (r"^(?:hey kairo|kairo)\s*,?\s*read\s+(.+)", "// read {0}"),
        (r"^(?:hey kairo|kairo)\s*,?\s*learn\s+(.+)", "// learn {0}"),
        (r"^(?:hey kairo|kairo)\s*,?\s*think\s+(?:about\s+)?(.+)", "// think {0}"),
        (r"^(?:hey kairo|kairo)\s*,?\s*export\s+(?:as\s+)?(?:to\s+)?(.+)", "// kami {0}"),
        (r"^(?:hey kairo|kairo)\s*,?\s*health\b", "// health"),
        (r"^(?:hey kairo|kairo)\s*,?\s*(.+)", "// {0}"),
    ]

    def __init__(self):
        pass

    async def post_process_transcription(
        self,
        raw_text: str,
        app_context: Optional[Dict] = None,
    ) -> Dict:
        """
        Post-process a raw whisper.cpp transcription.

        Returns a dict with:
        - "processed_text": cleaned transcription
        - "command": detected Kairo command (e.g., "// write email") or None
        - "is_command": whether the transcription is a Kairo command
        - "confidence": transcription confidence estimate
        """
        if not raw_text or not raw_text.strip():
            return {
                "processed_text": "",
                "command": None,
                "is_command": False,
                "confidence": 0.0,
            }

        # Step 1: Clean whitespace and normalize
        text = self._normalize(raw_text)

        # Step 2: Remove filler words
        text = self._remove_fillers(text)

        # Step 3: Restore basic punctuation
        text = self._restore_punctuation(text)

        # Step 4: Detect Kairo commands
        command = self._detect_command(text)

        # Step 5: Estimate confidence from text quality
        confidence = self._estimate_confidence(raw_text, text)

        return {
            "processed_text": text,
            "command": command,
            "is_command": command is not None,
            "confidence": confidence,
        }

    async def format_voice_prompt(
        self,
        transcription: str,
        mode: str = "ghost_write",
    ) -> Dict:
        """
        Format a voice transcription as a Kairo prompt.

        If the transcription contains a natural-language command ("write me an email"),
        converts it to the corresponding // command. Otherwise, wraps as a generic
        // ghost-write prompt.
        """
        result = await self.post_process_transcription(transcription)

        if result["is_command"]:
            prompt = result["command"]
        elif mode == "dictation":
            # Pure dictation mode: output text as-is (no // prefix)
            prompt = result["processed_text"]
        else:
            # Default: treat as ghost-write instruction
            prompt = f"// {result['processed_text']}"

        return {
            "prompt": prompt,
            "original": transcription,
            "processed": result["processed_text"],
            "mode": "command" if result["is_command"] else mode,
        }

    def _normalize(self, text: str) -> str:
        """Normalize whitespace and casing."""
        # Collapse multiple spaces
        text = re.sub(r"\s+", " ", text.strip())
        # Remove leading/trailing whitespace from each line
        text = "\n".join(line.strip() for line in text.split("\n"))
        return text

    def _remove_fillers(self, text: str) -> str:
        """Remove common filler words from transcription."""
        words = text.split()
        result = []
        i = 0

        while i < len(words):
            # Check two-word fillers first
            if i + 1 < len(words):
                two_word = f"{words[i].lower()} {words[i+1].lower()}"
                if two_word in self.FILLER_WORDS:
                    i += 2
                    continue

            # Check single-word fillers
            if words[i].lower().rstrip(",.!?") in self.FILLER_WORDS:
                # Don't remove "like" when used as comparison ("looks like")
                if (
                    words[i].lower().startswith("like")
                    and i > 0
                    and words[i - 1].lower() in ("looks", "feels", "sounds", "seems")
                ):
                    result.append(words[i])
                else:
                    i += 1
                    continue

            result.append(words[i])
            i += 1

        return " ".join(result)

    def _restore_punctuation(self, text: str) -> str:
        """Add basic punctuation to unpunctuated transcription."""
        if not text:
            return text

        # If text already has sentence-ending punctuation, leave it
        if re.search(r"[.!?]$", text.strip()):
            return text

        # Capitalize first letter
        if text and text[0].islower():
            text = text[0].upper() + text[1:]

        # Add period if missing
        if not text.endswith((".", "!", "?", ":", ";")):
            text += "."

        return text

    def _detect_command(self, text: str) -> Optional[str]:
        """Detect Kairo commands from natural language transcription."""
        text_lower = text.lower().strip().rstrip(".")

        for pattern, template in self.COMMAND_PATTERNS:
            match = re.match(pattern, text_lower, re.IGNORECASE)
            if match:
                groups = match.groups()
                if groups:
                    return template.format(*[g.strip() for g in groups])
                return template

        return None

    def _estimate_confidence(self, raw: str, processed: str) -> float:  # type: ignore[return]
        """Estimate transcription quality (0.0 to 1.0)."""
        if not raw.strip():
            return 0.0

        # Heuristics:
        score = 1.0

        # Short text = lower confidence
        if len(processed.split()) < 3:
            score *= 0.7

        # Many repeated words = likely noise
        words = processed.lower().split()
        if words:
            unique_ratio = len(set(words)) / len(words)
            if unique_ratio < 0.5:
                score *= 0.5

        # Presence of "[inaudible]" or similar
        if any(marker in raw.lower() for marker in ["[inaudible]", "[noise]", "[blank_audio]"]):
            score *= 0.3

        return min(max(score, 0.0), 1.0)


# ── MoonshineClient ──────────────────────────────────────────────────────────


class MoonshineClient:
    """
    HTTP client for the Moonshine Voice transcription service (port 7439).

    The service is a standalone Python process (sidecar/speech/moonshine_service.py)
    that must be started separately. This client connects to it via HTTP.

    The user NEVER sees "Moonshine" — this is Kairo Voice Dictation.
    """

    DEFAULT_URL = "http://localhost:7439"

    def __init__(self, service_url: str = DEFAULT_URL):
        self.service_url = service_url.rstrip("/")

    def is_available(self) -> bool:
        """Check if the Moonshine service is reachable (non-blocking, 2s timeout)."""
        try:
            with urllib.request.urlopen(f"{self.service_url}/health", timeout=2) as resp:
                return resp.status == 200
        except Exception:
            return False

    async def transcribe_file(self, wav_path: str) -> Optional[Dict]:
        """
        Transcribe a WAV file via the Moonshine HTTP service.

        Sends the file path to the sidecar (avoids copying audio bytes over HTTP).
        Returns a dict with text, confidence, language, duration_ms.
        Returns None if the service is unavailable or the call fails.
        """
        import json as _json

        if not os.path.exists(wav_path):
            return None

        payload = _json.dumps({"audio_path": wav_path}).encode()
        try:
            request = urllib.request.Request(
                f"{self.service_url}/transcribe",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=60) as resp:
                data = _json.loads(resp.read())
                return data
        except urllib.error.HTTPError:
            return None
        except urllib.error.URLError:
            return None
        except Exception:
            return None

    def get_supported_languages(self) -> list:
        """Get list of languages supported by the loaded Moonshine model."""
        try:
            with urllib.request.urlopen(f"{self.service_url}/languages", timeout=3) as resp:
                data = json.loads(resp.read())
                return data.get("supported", ["en"])
        except Exception:
            return ["en"]


# ── Fallback whisper.cpp transcription ────────────────────────────────────────


def _transcribe_with_whisper_cli(
    wav_path: str,
    language: str = "en",
    model: str = "base.en",
) -> Optional[str]:
    """
    Transcribe a WAV file using whisper.cpp CLI as fallback.

    Tries to find whisper-cli or main binary in ~/.kairo-phantom/bin/ and PATH.
    Returns transcription text, or None if whisper.cpp is not available.
    """
    import shutil
    from pathlib import Path

    kairo_bin = Path.home() / ".kairo-phantom" / "bin"
    model_path = Path.home() / ".kairo-phantom" / "models" / f"ggml-{model}.bin"

    # Find whisper binary
    whisper_bin = None
    candidates = [
        kairo_bin / "whisper-cli.exe",
        kairo_bin / "whisper-cli",
        kairo_bin / "main.exe",
        kairo_bin / "main",
    ]
    for candidate in candidates:
        if candidate.exists():
            whisper_bin = str(candidate)
            break

    if not whisper_bin:
        whisper_bin = shutil.which("whisper-cli") or shutil.which("whisper")

    if not whisper_bin or not model_path.exists():
        return None

    try:
        result = subprocess.run(
            [
                whisper_bin,
                "-m",
                str(model_path),
                "-f",
                wav_path,
                "--no-timestamps",
                "-l",
                language,
                "-np",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except Exception:
        return None


# ── Primary async transcription function ─────────────────────────────────────


async def transcribe_with_moonshine_or_fallback(
    wav_path: str,
    confidence_threshold: float = 0.6,
    moonshine_url: str = MoonshineClient.DEFAULT_URL,
    whisper_model: str = "base.en",
    whisper_language: str = "en",
) -> Dict:
    """
    Transcribe a WAV file using Moonshine as primary ASR.

    Falls back to whisper.cpp if:
    - Moonshine service is unreachable
    - Moonshine confidence is below threshold
    - Moonshine detects a non-English language

    Returns:
        {
            "text": str,
            "engine": "moonshine" | "whisper" | "none",
            "confidence": float,
            "language": str,
        }
    """
    client = MoonshineClient(moonshine_url)
    moonshine_result = await client.transcribe_file(wav_path)

    if moonshine_result is not None and "text" in moonshine_result:
        text = moonshine_result.get("text", "")
        confidence = float(moonshine_result.get("confidence", 0.0))
        language = moonshine_result.get("language", "en")

        # Use Moonshine result if confidence is high enough and language is English
        if confidence >= confidence_threshold and language == "en" and text.strip():
            return {
                "text": text,
                "engine": "moonshine",
                "confidence": confidence,
                "language": language,
            }

        # Low confidence or non-English — try whisper.cpp
        whisper_text = _transcribe_with_whisper_cli(wav_path, language, whisper_model)
        if whisper_text:
            return {
                "text": whisper_text,
                "engine": "whisper",
                "confidence": 0.75,  # whisper.cpp doesn't return confidence
                "language": language,
                "fallback_reason": (
                    f"moonshine_confidence={confidence:.2f}<{confidence_threshold}"
                    if language == "en"
                    else f"non_english_language={language}"
                ),
            }

        # Moonshine result below threshold but whisper also failed
        if text.strip():
            return {
                "text": text,
                "engine": "moonshine",
                "confidence": confidence,
                "language": language,
                "warning": "low_confidence",
            }

    # Moonshine completely unavailable — use whisper.cpp directly
    whisper_text = _transcribe_with_whisper_cli(wav_path, whisper_language, whisper_model)
    if whisper_text:
        return {
            "text": whisper_text,
            "engine": "whisper",
            "confidence": 0.75,
            "language": whisper_language,
            "fallback_reason": "moonshine_unavailable",
        }

    # Both engines failed
    return {
        "text": "",
        "engine": "none",
        "confidence": 0.0,
        "language": "en",
        "error": "Both Moonshine and whisper.cpp unavailable or returned empty result",
    }
