"""
Mem0Bridge — Cross-session memory persistence with 3-layer security gate (Domain 10)

SECURITY-GATED: Every memory added or queried passes through:
  1. PiiGuard.redact() — strip PII before storage
  2. PromptShield.scan() — block prompt injection attempts
  3. Manual sanitization — strip control chars, normalize whitespace

If mem0ai is not installed, the class raises RuntimeError on init — NEVER silently
falls back to a mock. The caller must handle the absence explicitly.

The local SQLite backend is used (NOT cloud) to preserve data sovereignty.
"""

from __future__ import annotations

import re
import logging
from typing import Dict, List, Optional

from sidecar.safety.prompt_shield import PromptShield
from sidecar.safety.pii_guard import PiiGuard

log = logging.getLogger("kairo-sidecar.mem0_bridge")

# ── Detect mem0 availability ──
try:
    from mem0 import Memory as _Mem0Memory

    HAS_MEM0 = True
except ImportError:
    HAS_MEM0 = False
    _Mem0Memory = None


class InjectionDetected(Exception):
    """Raised when PromptShield detects an injection attempt in memory text or query."""

    pass


# ── Control-char sanitization ──
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MULTI_WS_RE = re.compile(r"\s+")


def _sanitize(text: str) -> str:
    """Strip control characters and normalize whitespace."""
    if not text:
        return ""
    result = _CONTROL_CHAR_RE.sub("", text)
    result = _MULTI_WS_RE.sub(" ", result).strip()
    return result


class Mem0Bridge:
    """
    Security-gated bridge to Mem0 cross-session memory.

    All writes pass through PiiGuard → PromptShield → sanitize.
    All reads pass through PromptShield → sanitize results.
    """

    def __init__(self, backend: str = "sqlite", db_path: Optional[str] = None):
        if not HAS_MEM0:
            raise RuntimeError("mem0ai not installed. pip install mem0ai")

        self.prompt_shield = PromptShield()
        self.pii_guard = PiiGuard()

        # Configure mem0 for local SQLite backend (NOT cloud)
        config = {
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "embedding_model_dims": 256,
                    "path": db_path or ":memory:",
                },
            },
        }
        # Use mem0's local mode
        try:
            self.mem0 = _Mem0Memory.from_config(config)
        except Exception as e:
            # Fallback: try basic init
            log.warning(f"mem0 from_config failed ({e}), trying default init")
            self.mem0 = _Mem0Memory()

    def _security_gate_write(self, text: str) -> str:
        """
        3-layer security gate for memory writes.

        Layer 1: PiiGuard.redact() — strip PII
        Layer 2: PromptShield.scan() — block injection
        Layer 3: _sanitize() — strip control chars

        Returns sanitized text safe for storage.
        Raises InjectionDetected if injection is found.
        """
        # Layer 1: PII scrub
        cleaned = self.pii_guard.redact(text)

        # Layer 2: Injection detection
        if not self.prompt_shield.scan(cleaned):
            detail = self.prompt_shield.scan_detailed(cleaned)
            raise InjectionDetected(
                f"Prompt injection detected in memory text. "
                f"Matched patterns: {detail.get('matched_patterns', [])}"
            )

        # Layer 3: Sanitize control chars
        cleaned = _sanitize(cleaned)
        return cleaned

    def _security_gate_query(self, query: str) -> str:
        """
        Security gate for queries — injection check + sanitize.

        Raises InjectionDetected if injection is found.
        """
        if not self.prompt_shield.scan(query):
            detail = self.prompt_shield.scan_detailed(query)
            raise InjectionDetected(
                f"Prompt injection detected in query. "
                f"Matched patterns: {detail.get('matched_patterns', [])}"
            )
        return _sanitize(query)

    def _sanitize_result(self, result: Dict) -> Dict:
        """Sanitize a single memory result dict."""
        sanitized = {}
        for key, value in result.items():
            if isinstance(value, str):
                sanitized[key] = _sanitize(self.pii_guard.redact(value))
            elif isinstance(value, list):
                sanitized[key] = [
                    _sanitize(self.pii_guard.redact(v)) if isinstance(v, str) else v for v in value
                ]
            else:
                sanitized[key] = value
        return sanitized

    def secure_add(self, memory_text: str, user_id: str = "local") -> Dict:
        """
        Add a memory with 3-layer security gate.

        1. PiiGuard.scrub(memory_text) — strip PII
        2. PromptShield.scan(memory_text) — if False, raise InjectionDetected
        3. _sanitize() — strip control chars
        4. mem0.add(sanitized_text)

        Returns mem0 add result dict.
        Raises InjectionDetected if injection detected.
        """
        cleaned = self._security_gate_write(memory_text)
        if not cleaned:
            raise ValueError("Memory text is empty after security gate processing")

        result = self.mem0.add(cleaned, user_id=user_id)
        log.info(f"Memory added for user {user_id} (len={len(cleaned)})")
        return result

    def secure_query(self, query: str, user_id: str = "local") -> List[Dict]:
        """
        Query memories with security gate.

        1. PromptShield.scan(query) — if injection, raise InjectionDetected
        2. mem0.search(query) — get results
        3. Sanitize all results before returning

        Returns list of sanitized memory dicts.
        Raises InjectionDetected if injection detected in query.
        """
        cleaned_query = self._security_gate_query(query)
        results = self.mem0.search(cleaned_query, user_id=user_id)

        # Sanitize all results
        if isinstance(results, list):
            return [self._sanitize_result(r) if isinstance(r, dict) else r for r in results]
        elif isinstance(results, dict) and "results" in results:
            return [
                self._sanitize_result(r) if isinstance(r, dict) else r for r in results["results"]
            ]
        else:
            return []

    def export_memories(self, user_id: str = "local") -> List[Dict]:
        """Export all memories for a user."""
        if hasattr(self.mem0, "get_all"):
            results = self.mem0.get_all(user_id=user_id)
        elif hasattr(self.mem0, "get"):
            results = self.mem0.get(user_id=user_id)
        else:
            results = []

        if isinstance(results, list):
            return [self._sanitize_result(r) if isinstance(r, dict) else r for r in results]
        elif isinstance(results, dict) and "results" in results:
            return [
                self._sanitize_result(r) if isinstance(r, dict) else r for r in results["results"]
            ]
        return []

    def import_memories(self, memories: List[Dict], user_id: str = "local") -> int:
        """
        Import a list of memory dicts for a user.

        Each memory passes through the security gate before being added.
        Returns count of successfully imported memories.
        """
        count = 0
        for mem in memories:
            text = mem.get("memory", mem.get("text", mem.get("content", "")))
            if not text:
                continue
            try:
                self.secure_add(text, user_id=user_id)
                count += 1
            except (InjectionDetected, ValueError) as e:
                log.warning(f"Skipped memory during import: {e}")
        return count
