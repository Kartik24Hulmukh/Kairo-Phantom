from __future__ import annotations
import logging, math

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
DEFAULT_CLIP_MODEL = "openai/clip-vit-base-patch32"


class MediaEmbeddings:
    def __init__(self, model=DEFAULT_CLIP_MODEL, device="cpu"):
        if not HAS_EMBED_ANYTHING:
            raise RuntimeError("embed-anything not installed. pip install embed-anything")
        self.model_name = model
        self.device = device
        self._config = None
        self._init_model()

    def _init_model(self):
        try:
            self._config = EmbeddingModel.from_pretrained_hf(self.model_name)
        except Exception as exc:
            raise RuntimeError("Failed to initialise embed-anything model: " + str(exc)) from exc

    def embed_image(self, image_path):
        if not HAS_EMBED_ANYTHING:
            raise RuntimeError("embed-anything not installed. pip install embed-anything")
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
