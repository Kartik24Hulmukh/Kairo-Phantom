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
#
# HONESTY / SEALED MODE:
# - Text embeddings (model2vec potion-base-8M) are vendored and load offline.
# - CLIP media embeddings are OPTIONAL and may require a one-time network
#   download of openai/clip-vit-base-patch32 unless KAIRO_CLIP_MODEL_PATH
#   points at a local HF-format snapshot.
# - Under sealed / air-gap env (KAIRO_SEALED=1, KAIRO_NO_NET=1, KAIRO_OFFLINE=1,
#   HF_HUB_OFFLINE=1) remote download is refused; operators must stage weights
#   locally. Sealed runtime claims do NOT cover an unstaged CLIP download.
DEFAULT_CLIP_MODEL = "openai/clip-vit-base-patch32"


def _sealed_or_offline() -> bool:
    """True when product policy forbids outbound model downloads."""
    flags = (
        os.environ.get("KAIRO_SEALED", ""),
        os.environ.get("KAIRO_NO_NET", ""),
        os.environ.get("KAIRO_OFFLINE", ""),
        os.environ.get("HF_HUB_OFFLINE", ""),
        os.environ.get("TRANSFORMERS_OFFLINE", ""),
    )
    return any(str(v).strip() in ("1", "true", "TRUE", "yes", "YES") for v in flags)


class MediaEmbeddings:
    def __init__(self, model=DEFAULT_CLIP_MODEL, device="cpu"):
        if not HAS_EMBED_ANYTHING:
            raise RuntimeError("embed-anything not installed. pip install embed-anything")
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
            raise RuntimeError("embed-anything not installed. pip install embed-anything")
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
                if _sealed_or_offline():
                    raise RuntimeError(
                        "CLIP media embeddings require a local model snapshot under "
                        "sealed/offline mode. Set KAIRO_CLIP_MODEL_PATH to a directory "
                        f"containing HF-format weights for {self.model_name} "
                        "(~605MB; not vendored). Remote HuggingFace download is blocked "
                        "while KAIRO_SEALED/KAIRO_NO_NET/KAIRO_OFFLINE/HF_HUB_OFFLINE is set. "
                        "CLIP is an optional online-or-pre-staged capability; sealed "
                        "runtime claims do not cover an unstaged CLIP download."
                    )
                # May download on first use when network is available and sealed
                # flags are unset. This is intentionally NOT part of the sealed
                # zero-egress product claim.
                self._config = EmbeddingModel.from_pretrained_hf(self.model_name)
                log.info(
                    "CLIP model %s initialised via embed-anything "
                    "(may have used network if weights were not cached)",
                    self.model_name,
                )
        except Exception as exc:
            raise RuntimeError("Failed to initialise embed-anything model: " + str(exc)) from exc

    def embed_image(self, image_path):
        if not HAS_EMBED_ANYTHING:
            raise RuntimeError("embed-anything not installed. pip install embed-anything")
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
            raise RuntimeError("embed-anything not installed. pip install embed-anything")
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
