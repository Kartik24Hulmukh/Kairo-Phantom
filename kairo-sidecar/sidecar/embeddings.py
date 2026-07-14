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
                log.info("Loading Model2Vec 'minishlab/potion-base-8M' from vendored assets...")
                try:
                    from sidecar.model_paths import (
                        POTION_BASE_8M_HF_ID,
                        load_potion_base_8m_static_model,
                        resolve_potion_base_8m_path,
                    )

                    model_dir = resolve_potion_base_8m_path()
                    _model = load_potion_base_8m_static_model()
                    log.info(
                        "Model2Vec model '%s' loaded from local path %s "
                        "(256 dimensions, offline)",
                        POTION_BASE_8M_HF_ID,
                        model_dir,
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
