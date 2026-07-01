import logging
import threading
from typing import List

log = logging.getLogger("kairo-sidecar.embeddings")

_model = None
_lock = threading.Lock()


def get_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                log.info("Loading Model2Vec 'minishlab/potion-base-8M'...")
                try:
                    from model2vec import StaticModel

                    # Note: First load will download and cache the model from HuggingFace
                    _model = StaticModel.from_pretrained("minishlab/potion-base-8M")
                    log.info(
                        "Model2Vec model 'minishlab/potion-base-8M' loaded successfully (256 dimensions)"
                    )
                except Exception as e:
                    log.error(f"Failed to load Model2Vec: {e}")
                    raise
    return _model


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Generate 256-dimensional static embeddings for a list of texts using Model2Vec.
    """
    if not texts:
        return []
    try:
        model = get_model()
        embeddings = model.encode(texts)
        # Convert numpy array / list output to serializable float list
        return [list(map(float, emb)) for emb in embeddings]
    except Exception as e:
        log.error(f"Embedding generation failed: {e}")
        # Return fallback zero vectors (256-dim) so the system degrades gracefully
        return [[0.0] * 256 for _ in texts]


def embed_text(text: str) -> List[float]:
    """
    Generate 256-dimensional static embedding for a single text.
    """
    res = embed_texts([text])
    return res[0] if res else [0.0] * 256
