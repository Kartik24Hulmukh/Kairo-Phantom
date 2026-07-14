from __future__ import annotations

import logging
import math
import os

log = logging.getLogger("kairo.media_embeddings")
HAS_EMBED_ANYTHING = False
try:
    import embed_anything as _ea
    from embed_anything import EmbeddingModel, WhichModel

    HAS_EMBED_ANYTHING = True
except ImportError:
    _ea = None
    EmbeddingModel = None
    WhichModel = None

# Default HF id for CLIP. Weights are large (~605MB) and are NOT vendored
# (GitHub 50MB limit / no LFS). Construction is offline-safe: model download
# is deferred until the first embed_* call so Tier-1 wiring tests can assert
# the import guard without phoning home to HuggingFace / Xet CAS.
DEFAULT_CLIP_MODEL = "openai/clip-vit-base-patch32"


class MediaEmbeddings:
    def __init__(self, model=DEFAULT_CLIP_MODEL, device="cpu"):
        if not HAS_EMBED_ANYTHING:
            raise RuntimeError(
                "embed-anything not installed. pip install embed-anything"
            )
        self.model_name = model
        self.device = device
        # Lazy: do NOT call from_pretrained_hf here. CI/offline Tier-1 only
        # needs the constructor to prove the dep is wired; actual weights are
        # loaded on first embed. Override with KAIRO_CLIP_MODEL_PATH to a local
        # directory of HF-format weights if available offline.
        self._config = None

    def _init_model(self):
        if self._config is not None:
            return
        if not HAS_EMBED_ANYTHING:
            raise RuntimeError(
                "embed-anything not installed. pip install embed-anything"
            )
        try:
            local = os.environ.get("KAIRO_CLIP_MODEL_PATH")
            if local and os.path.isdir(local):
                # Prefer a local HF snapshot when the operator has staged one.
                # embed-anything's from_pretrained_hf accepts a local path as
                # model_id when the directory contains model weights.
                os.environ.setdefault("HF_HUB_OFFLINE", "1")
                os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
                self._config = EmbeddingModel.from_pretrained_hf(local)
                log.info("CLIP loaded from local path %s (offline)", local)
            else:
                # May download on first use when network is available.
                # Under HF_HUB_OFFLINE=1 / air-gap this raises — callers that
                # need offline CLIP must set KAIRO_CLIP_MODEL_PATH.
                self._config = EmbeddingModel.from_pretrained_hf(self.model_name)
                log.info("CLIP model %s initialised via embed-anything", self.model_name)
        except Exception as exc:
            raise RuntimeError(
                "Failed to initialise embed-anything model: " + str(exc)
            ) from exc

    def embed_image(self, image_path):
        if not HAS_EMBED_ANYTHING:
            raise RuntimeError(
                "embed-anything not installed. pip install embed-anything"
            )
        self._init_model()
        data = _ea.embed_file(image_path, embedder=self._config)
        if isinstance(data, list) and len(data) > 0:
            emb = data[0]
            if hasattr(emb, "embedding"):
                return list(map(float, emb.embedding))
            return list(map(float, emb))
        raise RuntimeError("No embedding returned for " + str(image_path))

    def embed_images(self, image_paths):
        if not HAS_EMBED_ANYTHING:
            raise RuntimeError(
                "embed-anything not installed. pip install embed-anything"
            )
        return [self.embed_image(p) for p in image_paths]

    @staticmethod
    def cosine_similarity(vec1, vec2):
        if not vec1 or not vec2:
            return 0.0
        dot = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))
        if norm1 == 0.0 or norm2 == 0.0:
            return 0.0
        return dot / (norm1 * norm2)

    @staticmethod
    def find_similar(query_vec, vectors, top_k=5):
        if not vectors:
            return []
        scored = []
        for idx, vec in enumerate(vectors):
            scored.append((MediaEmbeddings.cosine_similarity(query_vec, vec), idx))
        scored.sort(key=lambda x: x[0], reverse=True)
        k = min(top_k, len(scored))
        return [idx for _, idx in scored[:k]]
