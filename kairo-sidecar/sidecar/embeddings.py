import logging
import os
import threading
from typing import List

log = logging.getLogger("kairo-sidecar.embeddings")

_model = None
_lock = threading.Lock()


class EmbeddingError(RuntimeError):
    """Raised when text embeddings cannot be produced.

    Callers must not treat a broken/missing model as success. Returning zero
    vectors previously allowed semantic paths to fake-green; that path is gone.
    """


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
                    log.error("Failed to load Model2Vec: %s", e)
                    # KAIRO_REQUIRE_SEMANTIC is sticky in CI/e2e; always raise so a
                    # missing model cannot be mistaken for a successful embed.
                    raise EmbeddingError(
                        "Failed to load Model2Vec potion-base-8M offline model: "
                        f"{e}. Vendored assets must be present (see "
                        "kairo-sidecar/assets/models/potion-base-8M). "
                        "KAIRO_REQUIRE_SEMANTIC="
                        f"{os.getenv('KAIRO_REQUIRE_SEMANTIC', '0')}"
                    ) from e
    return _model


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Generate 256-dimensional static embeddings for a list of texts using Model2Vec.

    Raises EmbeddingError on any load/encode failure. Does not return zero vectors.
    """
    if not texts:
        return []
    try:
        model = get_model()
        embeddings = model.encode(texts)
        # Convert numpy array / list output to serializable float list
        return [list(map(float, emb)) for emb in embeddings]
    except EmbeddingError:
        raise
    except Exception as e:
        log.error("Embedding generation failed: %s", e)
        raise EmbeddingError(f"Embedding generation failed: {e}") from e


def embed_text(text: str) -> List[float]:
    """
    Generate 256-dimensional static embedding for a single text.

    Raises EmbeddingError on failure (including empty encode results).
    """
    res = embed_texts([text])
    if not res:
        raise EmbeddingError("embed_text produced no vectors for non-empty input")
    return res[0]
