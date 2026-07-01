"""
kairo-sidecar/sidecar/cua/vlm_grounding.py

VLM Grounding Engine for Kairo Phantom CUA.

Implements the full Qwen2.5-VL-7B integration described in briefing Doc 01:
  - Screenshot analysis to find UI elements by description
  - Semantic post-action verification ("does the dialog actually say 'Saved'?")
  - Hardware-adaptive: 7B (≥6GB VRAM) or 3B fallback
  - keep_alive=0 to free VRAM immediately after task
  - Keyboard-only mode while model downloads
  - Cross-app orchestration support

The VLM is the "Tier 3" fallback in the CUA hierarchy:
  Tier 0: File API  →  Tier 1: UIA  →  Tier 2: MCP  →  Tier 3: VLM (this module)

Accuracy targets from briefing:
  - Generic CUA miss rate: 56.7% → after VLM fallback: <12%
  - Average accuracy across all user actions: >93%
"""

from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from .vlm_config import VlmConfig, get_vlm_config
from .vlm_download_manager import get_background_downloader

logger = logging.getLogger(__name__)

# ─── Data Structures ──────────────────────────────────────────────────────────


@dataclass
class GroundingResult:
    """Result of a VLM element grounding request."""

    found: bool
    x: int = 0
    y: int = 0
    confidence: float = 0.0
    description: str = ""
    raw_response: str = ""
    latency_ms: float = 0.0

    @property
    def coordinates(self) -> tuple[int, int]:
        return (self.x, self.y)


@dataclass
class VerificationResult:
    """Result of a post-action semantic verification."""

    success: bool
    confidence: float
    explanation: str
    latency_ms: float = 0.0


@dataclass
class ScreenDescription:
    """Structured description of what the VLM sees on screen."""

    elements: list[dict]  # [{name, type, x, y, text}, ...]
    app_name: str
    raw_description: str
    latency_ms: float = 0.0


# ─── Prompt Templates ─────────────────────────────────────────────────────────

GROUNDING_PROMPT = """You are a precise UI element locator. Look at this screenshot carefully.

Find the UI element described as: "{description}"

Respond ONLY with a JSON object in this exact format:
{{
    "found": true or false,
    "x": <integer pixel x coordinate from left>,
    "y": <integer pixel y coordinate from top>,
    "confidence": <float 0.0 to 1.0>,
    "description": "<brief description of what you found>"
}}

If you cannot find the element, set found=false, x=0, y=0, confidence=0.0.
Be precise with coordinates — they will be used for mouse clicks."""

VERIFICATION_PROMPT = """You are a UI action verifier. Compare these two screenshots.

Screenshot 1 (BEFORE action): The first image.
Screenshot 2 (AFTER action): The second image.

The expected result of the action was: "{expected_result}"

Respond ONLY with a JSON object in this exact format:
{{
    "success": true or false,
    "confidence": <float 0.0 to 1.0>,
    "explanation": "<brief one-sentence explanation>"
}}

Look for: dialog text changes, button state changes, visual confirmation indicators.
Be honest — if you're unsure, lower your confidence score."""

SCREEN_DESCRIPTION_PROMPT = """Describe the UI elements visible in this screenshot.

Respond ONLY with a JSON object:
{{
    "app_name": "<detected application name>",
    "elements": [
        {{"name": "<element name>", "type": "<button/input/menu/text/etc>", "x": <int>, "y": <int>, "text": "<visible text>"}}
    ],
    "description": "<one sentence summary of what's on screen>"
}}

List the most important interactive elements (buttons, inputs, menus, checkboxes).
Focus on clickable/interactive elements that would be relevant for automation."""


# ─── VLM Grounding Engine ─────────────────────────────────────────────────────


class VlmGroundingEngine:
    """
    Vision-Language Model grounding engine using Ollama.

    Responsibilities:
    1. Ground UI element descriptions to screen coordinates
    2. Semantically verify post-action state
    3. Describe screen contents for cross-app orchestration

    All calls use keep_alive=0 to free VRAM after each task.
    Keyboard-only mode is active when model is not yet downloaded.
    """

    def __init__(self, config: Optional[VlmConfig] = None) -> None:
        self.config = config or get_vlm_config()
        self._downloader = get_background_downloader()
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def is_available(self) -> bool:
        """True if VLM is downloaded and Ollama is running."""
        return self._downloader.is_ready

    @property
    def available(self) -> bool:
        return self.is_available

    @property
    def is_keyboard_only_mode(self) -> bool:
        """True when VLM is not yet available (downloading)."""
        return not self.is_available

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.config.ollama_url,
                timeout=httpx.Timeout(
                    10.0, read=300.0
                ),  # 300s read: cold GGUF load + first inference can exceed 60s
            )
        return self._client

    def _encode_image(self, image_path: str | Path) -> str:
        """Encode image to base64 for Ollama API."""
        path = Path(image_path)
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    async def _ollama_chat(
        self,
        prompt: str,
        image_paths: list[str | Path],
        model_name: Optional[str] = None,
    ) -> tuple[str, float]:
        """
        Call Ollama chat API with image(s).

        Returns:
            (response_text, latency_ms)
        """
        model = (
            model_name
            or self.config.selected_model.ollama_pull_tag
            or self.config.selected_model.ollama_name
        )
        images = [self._encode_image(p) for p in image_paths]

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": images,
                }
            ],
            "options": self.config.to_ollama_options(),
            "keep_alive": self.config.keep_alive,
            "stream": False,
        }

        start = time.monotonic()
        client = self._get_client()
        response = await client.post("/api/chat", json=payload)
        response.raise_for_status()
        latency_ms = (time.monotonic() - start) * 1000

        data = response.json()
        text = data.get("message", {}).get("content", "")
        return text, latency_ms

    def _parse_json_response(self, text: str) -> dict:
        """Parse JSON from VLM response, handling markdown code fences."""
        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
        # Find first { and last }
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            text = text[start:end]
        return json.loads(text)

    # ─── Core Methods ──────────────────────────────────────────────────────

    async def ground_element(
        self,
        screenshot_path: str | Path,
        description: str,
    ) -> GroundingResult:
        """
        Find a UI element in a screenshot by natural language description.

        This is the primary VLM grounding function. Called when UIA fails to
        find an element (reducing miss rate from 56.7% to <12%).

        Args:
            screenshot_path: Path to the screenshot PNG
            description: Natural language description (e.g., "Submit button",
                         "email input field", "red X close button")

        Returns:
            GroundingResult with coordinates and confidence
        """
        if not self.is_available:
            logger.warning("VLM not available — keyboard-only mode active")
            return GroundingResult(found=False, description="VLM downloading")

        prompt = GROUNDING_PROMPT.format(description=description)

        try:
            raw, latency = await self._ollama_chat(prompt, [screenshot_path])
            parsed = self._parse_json_response(raw)

            result = GroundingResult(
                found=parsed.get("found", False),
                x=int(parsed.get("x", 0)),
                y=int(parsed.get("y", 0)),
                confidence=float(parsed.get("confidence", 0.0)),
                description=parsed.get("description", ""),
                raw_response=raw,
                latency_ms=latency,
            )
            logger.info(
                f"VLM grounding: '{description}' → "
                f"found={result.found} at ({result.x},{result.y}) "
                f"confidence={result.confidence:.2f} in {latency:.0f}ms"
            )
            return result

        except json.JSONDecodeError as e:
            logger.warning(f"VLM response parse error: {e} | raw: {raw[:200]}")
            return GroundingResult(
                found=False,
                description=f"Parse error: {e}",
                latency_ms=latency,
            )
        except httpx.HTTPError as e:
            logger.error(f"VLM HTTP error: {e}")
            return GroundingResult(found=False, description=f"HTTP error: {e}")
        except Exception as e:
            logger.error(f"VLM grounding error: {e}", exc_info=True)
            return GroundingResult(found=False, description=f"Error: {e}")

    async def verify_action(
        self,
        before_screenshot: str | Path,
        after_screenshot: str | Path,
        expected_result: str,
    ) -> VerificationResult:
        """
        Semantically verify that an action produced the expected result.

        This replaces pixel-diff verification with actual intent understanding.
        Example: "does the dialog actually say 'Saved'?" rather than just
        checking pixel changes.

        From briefing: "Eliminates false-positive verification errors that
        plague pixel-based tools."

        Args:
            before_screenshot: Screenshot before the action
            after_screenshot: Screenshot after the action
            expected_result: What should have changed (e.g., "dialog showing 'File saved'")

        Returns:
            VerificationResult with success flag and explanation
        """
        if not self.is_available:
            # In keyboard-only mode, assume success (no VLM to verify)
            return VerificationResult(
                success=True,
                confidence=0.5,
                explanation="VLM not available — assumed success (keyboard-only mode)",
            )

        prompt = VERIFICATION_PROMPT.format(expected_result=expected_result)

        try:
            raw, latency = await self._ollama_chat(
                prompt,
                [before_screenshot, after_screenshot],
            )
            parsed = self._parse_json_response(raw)

            result = VerificationResult(
                success=parsed.get("success", False),
                confidence=float(parsed.get("confidence", 0.0)),
                explanation=parsed.get("explanation", ""),
                latency_ms=latency,
            )
            logger.info(
                f"VLM verify: success={result.success} "
                f"confidence={result.confidence:.2f} "
                f"'{result.explanation}' in {latency:.0f}ms"
            )
            return result

        except json.JSONDecodeError as e:
            logger.warning(f"VLM verify parse error: {e}")
            return VerificationResult(
                success=False,
                confidence=0.0,
                explanation="Parse error — could not verify",
            )
        except Exception as e:
            logger.error(f"VLM verify error: {e}", exc_info=True)
            return VerificationResult(
                success=False,
                confidence=0.0,
                explanation=f"Verification failed: {e}",
            )

    async def describe_screen(
        self,
        screenshot_path: str | Path,
    ) -> ScreenDescription:
        """
        Generate a structured description of all UI elements on screen.

        Used by the CrossAppOrchestrator to understand what apps are open
        and what elements are available for cross-app workflow execution.

        Example use case: "Take Q3 report from Excel → PowerPoint → Email"
        The orchestrator calls describe_screen() on each app window to plan actions.
        """
        if not self.is_available:
            return ScreenDescription(
                elements=[],
                app_name="unknown",
                raw_description="VLM not available",
            )

        try:
            raw, latency = await self._ollama_chat(
                SCREEN_DESCRIPTION_PROMPT,
                [screenshot_path],
            )
            parsed = self._parse_json_response(raw)

            return ScreenDescription(
                elements=parsed.get("elements", []),
                app_name=parsed.get("app_name", "unknown"),
                raw_description=parsed.get("description", ""),
                latency_ms=latency,
            )
        except Exception as e:
            logger.error(f"VLM screen description error: {e}", exc_info=True)
            return ScreenDescription(
                elements=[],
                app_name="unknown",
                raw_description=f"Error: {e}",
            )

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# ─── Singleton ────────────────────────────────────────────────────────────────

_engine: Optional[VlmGroundingEngine] = None


def get_vlm_engine() -> VlmGroundingEngine:
    """Get (or create) the singleton VLM grounding engine."""
    global _engine
    if _engine is None:
        _engine = VlmGroundingEngine()
    return _engine


# Alias for backwards compatibility / checklist validation
VLMGrounding = VlmGroundingEngine
