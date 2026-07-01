"""
Local Retrieval Index — offline semantic search over ingested PDF chunks.

Uses the SAME local embedding MemMachine v2 uses: model2vec potion-base-8M
(256-dim, offline, bundled/cached). This enables real semantic retrieval —
paraphrased questions retrieve the correct chunks even when no words overlap.

If model2vec is not available (model file absent), falls back to the kernel's
deterministic hash-based embedding (384-dim). The fallback is clearly logged.

No network calls. No runtime downloads. Fully offline.
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass, field
from typing import List, Optional

from kairo.docintel.ingest import ChunkMeta, IngestResult

logger = logging.getLogger("kairo.docintel.retrieval")


@dataclass
class RetrievalResult:
    """A single retrieval hit."""
    chunk: ChunkMeta
    score: float  # cosine similarity, higher is better
    rank: int     # 1-indexed rank


class RetrievalIndex:
    """
    Local in-memory retrieval index over PDF chunks.

    Embeds chunks using model2vec potion-base-8M (the same model used by
    MemMachine v2 / sidecar.embeddings) for real semantic retrieval.
    Falls back to kernel hash embeddings if the model is unavailable.

    Fully offline — no network calls, no runtime downloads.
    """

    def __init__(self) -> None:
        self._chunks: List[ChunkMeta] = []
        self._embeddings: List[List[float]] = []
        self._doc_ids: List[str] = []
        self._embed_dim: int = 256  # model2vec default
        self._embed_backend: str = ""  # "model2vec" or "hash"
        self._embed_fn = None

    def _init_embedding(self) -> None:
        """Initialize the embedding backend. Tries model2vec first, hash fallback."""
        if self._embed_fn is not None:
            return

        # Try model2vec (same as sidecar.embeddings / MemMachine v2)
        try:
            # Set offline mode to prevent any network calls
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

            from model2vec import StaticModel
            model = StaticModel.from_pretrained("minishlab/potion-base-8M")

            def model2vec_embed(text: str) -> List[float]:
                emb = model.encode([text])
                return list(map(float, emb[0]))

            self._embed_fn = model2vec_embed
            self._embed_dim = 256
            self._embed_backend = "model2vec"
            logger.info("Using model2vec potion-base-8M (256-dim) for semantic retrieval")
            return

        except Exception as e:
            logger.warning(
                "model2vec unavailable (%s) — falling back to hash embedding. "
                "Paraphrase retrieval quality will be reduced.",
                type(e).__name__,
            )

        # Fallback: kernel hash embedding
        from kernel.core.embeddings import get_embedding

        self._embed_dim = 384
        self._embed_backend = "hash"

        def hash_embed(text: str) -> List[float]:
            return get_embedding(text, dim=384)

        self._embed_fn = hash_embed
        logger.info("Using hash embedding (384-dim) — fallback mode")

    def add_document(self, result: IngestResult) -> None:
        """Add all chunks from an ingested document to the index."""
        self._init_embedding()

        for chunk in result.chunks:
            emb = self._embed_fn(chunk.text)
            self._chunks.append(chunk)
            self._embeddings.append(emb)
            self._doc_ids.append(result.doc_id)

        logger.info(
            "Added %d chunks from doc %s to retrieval index (total: %d, backend: %s)",
            len(result.chunks),
            result.doc_id,
            len(self._chunks),
            self._embed_backend,
        )

    def retrieve(
        self,
        question: str,
        top_k: int = 5,
    ) -> List[RetrievalResult]:
        """
        Retrieve the top-k most relevant chunks for a question.

        Uses cosine similarity over local embeddings. Fully offline.
        """
        if not self._chunks:
            return []

        self._init_embedding()
        query_emb = self._embed_fn(question)

        scores: List[tuple[float, int]] = []
        for i, chunk_emb in enumerate(self._embeddings):
            score = self._cosine_similarity(query_emb, chunk_emb)
            scores.append((score, i))

        scores.sort(key=lambda x: x[0], reverse=True)

        results: List[RetrievalResult] = []
        for rank, (score, idx) in enumerate(scores[:top_k], 1):
            results.append(
                RetrievalResult(
                    chunk=self._chunks[idx],
                    score=score,
                    rank=rank,
                )
            )

        return results

    def _cosine_similarity(
        self, v1: List[float], v2: List[float]
    ) -> float:
        """Compute cosine similarity between two vectors."""
        dot = sum(a * b for a, b in zip(v1, v2))
        n1 = math.sqrt(sum(a * a for a in v1))
        n2 = math.sqrt(sum(b * b for b in v2))
        if n1 == 0.0 or n2 == 0.0:
            return 0.0
        return dot / (n1 * n2)

    @property
    def size(self) -> int:
        """Number of chunks in the index."""
        return len(self._chunks)

    @property
    def embed_backend(self) -> str:
        """Which embedding backend is in use ('model2vec' or 'hash')."""
        return self._embed_backend