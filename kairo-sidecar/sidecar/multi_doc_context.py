# Multi-document context retrieval for MemMachine
# Assembles context from multiple previously-indexed documents
# Uses the existing embeddings.py Model2Vec for semantic similarity

import os
import logging
from pathlib import Path
from typing import List

log = logging.getLogger("kairo-sidecar.multi_doc_context")

# ---------------------------------------------------------------------------
# Token-budget constants
# ---------------------------------------------------------------------------
_CHUNK_TOKEN_BUDGET = 512  # approximate tokens per chunk (words * 1.3 ≈ tokens)
_WORDS_PER_CHUNK = int(_CHUNK_TOKEN_BUDGET / 1.3)  # ~393 words


def _read_document_text(file_path: str) -> str:
    """Read plain text from a document.

    Supports: .txt, .md, .py, .docx (via python-docx if installed),
    .pdf (via PyMuPDF if installed).  Falls back to raw UTF-8 for anything else.
    """
    p = Path(file_path)
    ext = p.suffix.lower()

    if ext == ".docx":
        try:
            from docx import Document

            doc = Document(str(p))
            return "\n".join(para.text for para in doc.paragraphs if para.text.strip())
        except ImportError:
            log.warning(
                "python-docx not installed; reading .docx as raw bytes (text quality may be poor)"
            )
        except Exception as e:
            log.warning(f"Failed to read .docx {p}: {e}")

    if ext == ".pdf":
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(str(p))
            pages = [page.get_text() for page in doc]
            doc.close()
            return "\n".join(pages)
        except ImportError:
            log.warning("PyMuPDF not installed; cannot read .pdf; returning empty string")
            return ""
        except Exception as e:
            log.warning(f"Failed to read .pdf {p}: {e}")
            return ""

    # Fallback: plain text / markdown / source code
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        log.warning(f"Failed to read {p}: {e}")
        return ""


def _chunk_text(text: str, max_words: int = _WORDS_PER_CHUNK) -> List[str]:
    """Split text into chunks of at most *max_words* words, preserving paragraph breaks."""
    words = text.split()
    if not words:
        return []

    chunks: List[str] = []
    start = 0
    while start < len(words):
        end = min(start + max_words, len(words))
        chunks.append(" ".join(words[start:end]))
        start = end
    return chunks


def _cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Cosine similarity between two equal-length vectors using numpy."""
    try:
        import numpy as np  # noqa: F401 – lazy import so we gracefully degrade

        a = np.array(v1, dtype=float)
        b = np.array(v2, dtype=float)
        denom = np.linalg.norm(a) * np.linalg.norm(b)
        if denom == 0.0:
            return 0.0
        return float(np.dot(a, b) / denom)
    except ImportError:
        log.warning("numpy not available; falling back to pure-Python cosine similarity")
        dot = sum(x * y for x, y in zip(v1, v2))
        norm_a = sum(x * x for x in v1) ** 0.5
        norm_b = sum(x * x for x in v2) ** 0.5
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)


class MultiDocContextAssembler:
    """Assembles semantically relevant context from multiple documents for a given query.

    Typical usage::

        assembler = MultiDocContextAssembler()
        context_str = assembler.assemble(
            query="What is the refund policy?",
            doc_paths=["/path/to/policy.pdf", "/path/to/terms.docx"],
            max_chunks=5,
        )
        # context_str is a concatenated string of the top-k most relevant excerpts
    """

    def assemble(
        self,
        query: str,
        doc_paths: List[str],
        max_chunks: int = 5,
        chunk_word_size: int = _WORDS_PER_CHUNK,
    ) -> str:
        """Return the top-k most semantically similar text chunks across *doc_paths*.

        Args:
            query: The user query or instruction to match against.
            doc_paths: List of absolute paths to documents to search.
            max_chunks: Maximum number of top-ranked chunks to include.
            chunk_word_size: Override the default chunk word budget.

        Returns:
            A single string joining the most relevant chunks separated by
            ``--- [<source_file>] ---`` section headers.  Returns an empty
            string when no text could be extracted from any document.
        """
        if not query or not doc_paths:
            return ""

        from sidecar.embeddings import embed_texts  # imported here to avoid circular imports

        # ── Step 1: Collect all chunks across all documents ──────────────────
        all_chunks: List[dict] = []  # {"source": str, "text": str}
        for raw_path in doc_paths:
            path = str(Path(raw_path).resolve())
            if not os.path.exists(path):
                log.warning(f"MultiDocContextAssembler: skipping missing path {path}")
                continue
            text = _read_document_text(path)
            if not text.strip():
                log.warning(f"MultiDocContextAssembler: no text extracted from {path}")
                continue
            chunks = _chunk_text(text, max_words=chunk_word_size)
            source_label = Path(path).name
            for chunk in chunks:
                all_chunks.append({"source": source_label, "text": chunk})

        if not all_chunks:
            log.warning("MultiDocContextAssembler: no chunks produced from any document")
            return ""

        # ── Step 2: Embed query + all chunks in one batched call ─────────────
        texts_to_embed = [query] + [c["text"] for c in all_chunks]
        try:
            all_vectors = embed_texts(texts_to_embed)
        except Exception as e:
            log.error(f"MultiDocContextAssembler: embedding failed: {e}")
            return ""

        if len(all_vectors) != len(texts_to_embed):
            log.error("MultiDocContextAssembler: vector count mismatch; aborting")
            return ""

        query_vec = all_vectors[0]
        chunk_vecs = all_vectors[1:]

        # ── Step 3: Rank chunks by cosine similarity to query ─────────────────
        scored: List[tuple] = []  # (score, chunk_dict)
        for chunk_dict, vec in zip(all_chunks, chunk_vecs):
            score = _cosine_similarity(query_vec, vec)
            scored.append((score, chunk_dict))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_chunks = scored[:max_chunks]

        # ── Step 4: Assemble the context string ───────────────────────────────
        if not top_chunks:
            return ""

        parts: List[str] = []
        for score, chunk_dict in top_chunks:
            header = f"--- [{chunk_dict['source']}] (similarity: {score:.3f}) ---"
            parts.append(f"{header}\n{chunk_dict['text']}")

        assembled = "\n\n".join(parts)
        log.info(
            f"MultiDocContextAssembler: assembled {len(top_chunks)} chunks "
            f"from {len(doc_paths)} doc(s) for query '{query[:60]}...'"
        )
        return assembled
