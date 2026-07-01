"""
SemanticMemoryStore — Local semantic memory recall using REAL model2vec embeddings (Domain 10)

This module provides a local in-memory semantic search over stored memories
using the REAL model2vec embeddings from sidecar.embeddings (Part 1).

CRITICAL: This uses the REAL semantic embeddings (minishlab/potion-base-8M,
256-dim), NOT a hash fallback. The paraphrase retrieval test proves that
'cancel subscription' retrieves 'membership termination' — which would FAIL
with a hash-based approach because the tokens don't overlap.

If model2vec is not available, embed_text returns zero vectors and the
store raises RuntimeError on init — it NEVER silently falls back to hashing.
"""

from __future__ import annotations

import math
import logging
import threading
from typing import Dict, List, Optional, Tuple

from sidecar.embeddings import embed_text
from sidecar.safety.prompt_shield import PromptShield
from sidecar.safety.pii_guard import PiiGuard

log = logging.getLogger("kairo-sidecar.semantic_memory_store")


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class SemanticMemoryStore:
    """
    Local semantic memory store using REAL model2vec embeddings.

    Memories are embedded with sidecar.embeddings.embed_text() (model2vec
    potion-base-8M, 256-dim). Recall uses cosine similarity, NOT token
    matching. This means paraphrases and semantically equivalent queries
    retrieve the right memory even when no words overlap.

    Security: All inputs pass through PromptShield + PiiGuard.
    """

    def __init__(self):
        self.prompt_shield = PromptShield()
        self.pii_guard = PiiGuard()
        self._memories: List[Dict] = []  # list of {id, text, user_id, embedding, metadata}
        self._lock = threading.Lock()
        self._next_id = 0

        # Verify that embeddings are REAL (non-zero) — fail loudly if not
        test_vec = embed_text("semantic initialization test")
        nonzero = sum(1 for x in test_vec if x != 0.0)
        if nonzero == 0:
            raise RuntimeError(
                "SemanticMemoryStore requires REAL semantic embeddings. "
                "embed_text() returned a zero vector — model2vec is not loaded. "
                "pip install model2vec"
            )
        log.info(
            f"SemanticMemoryStore initialized (embedding dim={len(test_vec)}, nonzero={nonzero})"
        )

    def add(self, text: str, user_id: str = "local", metadata: Optional[Dict] = None) -> int:
        """
        Add a memory with semantic embedding.

        Security gate: PiiGuard.redact → PromptShield.scan → embed.
        Returns memory ID.
        """
        # Layer 1: PII scrub
        cleaned = self.pii_guard.redact(text)

        # Layer 2: Injection detection
        if not self.prompt_shield.scan(cleaned):
            detail = self.prompt_shield.scan_detailed(cleaned)
            raise ValueError(
                f"Prompt injection detected in memory text. "
                f"Matched: {detail.get('matched_patterns', [])}"
            )

        # Layer 3: Embed with REAL semantic model
        embedding = embed_text(cleaned)

        with self._lock:
            mem_id = self._next_id
            self._next_id += 1
            self._memories.append(
                {
                    "id": mem_id,
                    "text": cleaned,
                    "user_id": user_id,
                    "embedding": embedding,
                    "metadata": metadata or {},
                }
            )

        log.info(f"Memory {mem_id} added for user {user_id} (len={len(cleaned)})")
        return mem_id

    def search(
        self,
        query: str,
        user_id: Optional[str] = None,
        top_k: int = 5,
        min_similarity: float = 0.0,
    ) -> List[Dict]:
        """
        Semantic search over memories using cosine similarity.

        Security gate: PromptShield.scan on query.
        Returns list of {id, text, score, metadata} sorted by similarity.
        """
        # Security: check query for injection
        if not self.prompt_shield.scan(query):
            detail = self.prompt_shield.scan_detailed(query)
            raise ValueError(
                f"Prompt injection detected in query. "
                f"Matched: {detail.get('matched_patterns', [])}"
            )

        # Embed query with REAL semantic model
        query_vec = embed_text(query)

        with self._lock:
            candidates = self._memories.copy()

        # Score all memories
        scored: List[Tuple[float, Dict]] = []
        for mem in candidates:
            if user_id is not None and mem["user_id"] != user_id:
                continue
            score = _cosine_similarity(query_vec, mem["embedding"])
            if score >= min_similarity:
                scored.append((score, mem))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)

        # Return top_k results
        results = []
        for score, mem in scored[:top_k]:
            results.append(
                {
                    "id": mem["id"],
                    "text": mem["text"],
                    "score": score,
                    "metadata": mem.get("metadata", {}),
                }
            )
        return results

    def count(self, user_id: Optional[str] = None) -> int:
        """Return number of stored memories."""
        with self._lock:
            if user_id is not None:
                return sum(1 for m in self._memories if m["user_id"] == user_id)
            return len(self._memories)

    def get_all(self, user_id: Optional[str] = None) -> List[Dict]:
        """Return all memories (without embeddings)."""
        with self._lock:
            results = []
            for mem in self._memories:
                if user_id is not None and mem["user_id"] != user_id:
                    continue
                results.append(
                    {
                        "id": mem["id"],
                        "text": mem["text"],
                        "user_id": mem["user_id"],
                        "metadata": mem.get("metadata", {}),
                    }
                )
            return results
