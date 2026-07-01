"""
Headroom Context Compression Proxy (Phase 0.2)

Wraps LLM calls with Headroom's compression middleware to reduce token usage
by 60-95%. Compresses context before sending to LLM, decompresses response.

Integration point: sits between domain masters and the LLM caller (llm_caller.py).
When enabled, LLM calls go through: domain master → headroom_proxy → llm_caller → LLM

The compression ratio is logged to the Opik trace (from Phase 0.1).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Tuple

log = logging.getLogger("kairo-sidecar.headroom_proxy")

# Lazy import — headroom-ai is a heavy dependency
_headroom_available = False
_headroom_client = None

try:
    import headroom

    _headroom_available = True
    log.debug("headroom-ai is available")
except ImportError:
    log.debug("headroom-ai not installed — compression disabled")


def is_compression_enabled() -> bool:
    """Check if Headroom compression is enabled (env flag + package available)."""
    return _headroom_available and os.environ.get("KAIRO_HEADROOM", "1") == "1"


def get_headroom_client():
    """Get or create the global Headroom client."""
    global _headroom_client
    if _headroom_client is None and _headroom_available:
        try:
            _headroom_client = headroom.HeadroomClient()
            log.info("Headroom client initialized")
        except Exception as e:
            log.warning(f"Failed to initialize Headroom client: {e}")
            _headroom_client = None
    return _headroom_client


def compress_context(text: str) -> Tuple[str, Dict[str, Any]]:
    """
    Compress a text context using Headroom.

    Returns (compressed_text, metrics) where metrics includes:
    - tokens_before: estimated token count before compression
    - tokens_after: estimated token count after compression
    - compression_ratio: float (0.0-1.0, lower = more compression)
    - chars_before, chars_after

    If compression is disabled or fails, returns the original text with
    a metrics dict showing no compression.
    """
    metrics = {
        "tokens_before": 0,
        "tokens_after": 0,
        "compression_ratio": 1.0,
        "chars_before": len(text),
        "chars_after": len(text),
        "compressed": False,
    }

    if not is_compression_enabled() or not text.strip():
        return text, metrics

    client = get_headroom_client()
    if client is None:
        return text, metrics

    try:
        # Use headroom's compress function
        result = headroom.compress(text)
        compressed = result.compressed_text if hasattr(result, "compressed_text") else str(result)

        # Estimate tokens (rough: 1 token ≈ 4 chars)
        tokens_before = len(text) // 4
        tokens_after = len(compressed) // 4

        metrics["tokens_before"] = tokens_before
        metrics["tokens_after"] = tokens_after
        metrics["chars_after"] = len(compressed)
        metrics["compression_ratio"] = tokens_after / max(tokens_before, 1)
        metrics["compressed"] = True

        log.debug(
            f"Headroom compressed: {tokens_before}→{tokens_after} tokens "
            f"({metrics['compression_ratio']:.1%} ratio)"
        )
        return compressed, metrics

    except Exception as e:
        log.warning(f"Headroom compression failed: {e} — using uncompressed text")
        return text, metrics


def compress_spreadsheet_context(text: str) -> Tuple[str, Dict[str, Any]]:
    """
    Compress spreadsheet-specific context (tabular data).

    Uses Headroom's spreadsheet-specific compression if available.
    """
    metrics = {
        "tokens_before": 0,
        "tokens_after": 0,
        "compression_ratio": 1.0,
        "chars_before": len(text),
        "chars_after": len(text),
        "compressed": False,
    }

    if not is_compression_enabled() or not text.strip():
        return text, metrics

    try:
        result = headroom.compress_spreadsheet(text)
        compressed = result.compressed_text if hasattr(result, "compressed_text") else str(result)

        tokens_before = len(text) // 4
        tokens_after = len(compressed) // 4

        metrics["tokens_before"] = tokens_before
        metrics["tokens_after"] = tokens_after
        metrics["chars_after"] = len(compressed)
        metrics["compression_ratio"] = tokens_after / max(tokens_before, 1)
        metrics["compressed"] = True

        return compressed, metrics
    except Exception as e:
        log.warning(f"Headroom spreadsheet compression failed: {e}")
        return text, metrics


def count_tokens(text: str) -> int:
    """Count tokens in text using Headroom's tokenizer if available."""
    if _headroom_available:
        try:
            return headroom.count_tokens_text(text)
        except Exception:
            pass
    # Fallback: rough estimate
    return len(text) // 4
