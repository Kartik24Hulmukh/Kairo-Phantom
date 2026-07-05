# PROVENANCE: original | clean-room Anchor perception layer per specs/ANCHOR_ARCHITECTURE.md + specs/R5_LEGACY_GROUNDING.md
"""Anchor perception layer — local screen-to-element-map fusion engine.

Replaces the vlm_bridge / mocked context-capture path with a local,
multi-modal perception pipeline:

  1. AX-tree leg   — parse accessibility tree dumps (Win UIA / macOS AX / Linux AT-SPI)
  2. OCR leg       — text extraction from canvas regions (Experimental: olmocr/Tesseract)
  3. Vision leg    — icon/shape detection from fixture-provided detections (Experimental: live inference)
  4. Fusion        — merge legs into unified element graph with bbox-overlap dedup (UFO² pattern)
  5. Compaction    — token-efficient element map (>=70% reduction vs raw screenshot)

All perceived text is TAINTED (untrusted) — it can inform content but never
authorize a capability (per prompts/05 out-of-band reference monitor).

HONEST SCOPING:
  - AX-parse + fusion + compaction + resolve() on the static corpus = Real
  - Live screen capture, live vision-detector inference, olmocr OCR = Experimental
  - Experimental paths FAIL LOUD when unavailable — never fake results

All operations are fully offline. No network calls. No LLM. No cloud.
No AGPL/GPL. Clean-room per prompts/15.
"""

from __future__ import annotations

from .engine import (
    AnchorElement,
    ElementMap,
    ScreenMap,
    fuse_elements,
    get_screen_map,
    resolve,
    compact_map,
    AnchorExperimentalError,
    AnchorUnavailableError,
)

__all__ = [
    "AnchorElement",
    "ElementMap",
    "ScreenMap",
    "fuse_elements",
    "get_screen_map",
    "resolve",
    "compact_map",
    "AnchorExperimentalError",
    "AnchorUnavailableError",
]
