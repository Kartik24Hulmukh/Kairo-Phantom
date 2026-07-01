"""
PDF Ingestion Module — real PDF parsing with pdfplumber (MIT-licensed).

pdfplumber is built on pdfminer.six (MIT), NOT PyMuPDF (AGPL).
This keeps the shipped path clean of AGPL dependencies.

Produces page-level chunks with bounding boxes for citation.
One bad file returns a typed IngestError — doesn't crash the caller.
"""

from __future__ import annotations

import hashlib
import logging
import pathlib
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger("kairo.docintel.ingest")


class IngestError(Exception):
    """Typed error for PDF ingestion failures."""

    def __init__(self, path: str, reason: str, recoverable: bool = True):
        self.path = path
        self.reason = reason
        self.recoverable = recoverable
        super().__init__(f"IngestError: {path}: {reason}")


@dataclass
class ChunkMeta:
    """Metadata for a single text chunk extracted from a PDF."""
    chunk_id: str
    page: int          # 1-indexed page number
    text: str
    bbox: tuple[float, float, float, float]  # (x0, y0, x1, y1) normalized [0,1]
    char_start: int = 0  # character offset within the page text
    char_end: int = 0


@dataclass
class IngestResult:
    """Result of ingesting a PDF file."""
    doc_id: str
    source_path: str
    sha256: str
    page_count: int
    chunks: List[ChunkMeta] = field(default_factory=list)
    page_texts: dict[int, str] = field(default_factory=dict)  # page -> full text


class PdfIngestor:
    """
    Real PDF ingestor using pdfplumber (MIT-licensed).

    Parses each page, extracts text blocks with bounding boxes,
    and produces chunks suitable for embedding and retrieval.

    Chunking strategy: split page text into ~500-char chunks at word
    boundaries, each tagged with its page number and approximate bbox.
    """

    CHUNK_SIZE = 500  # characters per chunk
    CHUNK_OVERLAP = 50  # overlap between consecutive chunks

    def ingest(self, path: str) -> IngestResult:
        """
        Ingest a PDF file and return chunks with page metadata.

        Raises IngestError on any failure (missing file, corrupt PDF, etc.).
        """
        filepath = pathlib.Path(path)

        # --- Validate file exists ---
        if not filepath.exists():
            raise IngestError(path, f"File not found: {path}", recoverable=False)

        if filepath.suffix.lower() != ".pdf":
            raise IngestError(
                path,
                f"Expected .pdf file, got: {filepath.suffix}",
                recoverable=False,
            )

        # --- Compute SHA-256 for document identity ---
        try:
            content_bytes = filepath.read_bytes()
        except OSError as e:
            raise IngestError(path, f"Cannot read file: {e}", recoverable=False) from e

        sha256 = hashlib.sha256(content_bytes).hexdigest()
        doc_id = hashlib.sha256(f"{filepath.name}:{sha256}".encode()).hexdigest()[:16]

        # --- Parse PDF with pdfplumber ---
        try:
            import pdfplumber
        except ImportError as e:
            raise IngestError(
                path,
                "pdfplumber is not installed. Install with: pip install pdfplumber",
                recoverable=False,
            ) from e

        chunks: List[ChunkMeta] = []
        page_texts: dict[int, str] = {}

        try:
            with pdfplumber.open(str(filepath)) as pdf:
                page_count = len(pdf.pages)

                if page_count == 0:
                    raise IngestError(
                        path,
                        "PDF has zero pages — possibly corrupt",
                        recoverable=False,
                    )

                for page_idx, page in enumerate(pdf.pages):
                    page_num = page_idx + 1  # 1-indexed

                    # Extract full page text
                    page_text = page.extract_text() or ""
                    page_texts[page_num] = page_text

                    if not page_text.strip():
                        logger.debug("Page %d has no extractable text", page_num)
                        continue

                    # Extract words with positions for bbox-aware chunking
                    try:
                        words = page.extract_words(
                            keep_blank_chars=False,
                            use_text_flow=True,
                        )
                    except Exception:
                        words = []

                    # Get page dimensions
                    pw = float(page.width) if page.width else 612.0
                    ph = float(page.height) if page.height else 792.0

                    # Chunk the page text
                    page_chunks = self._chunk_text(page_text, page_num, words, pw, ph)
                    chunks.extend(page_chunks)

        except IngestError:
            raise
        except Exception as e:
            raise IngestError(
                path,
                f"PDF parsing failed: {type(e).__name__}: {e}",
                recoverable=True,
            ) from e

        if not chunks:
            raise IngestError(
                path,
                "No text could be extracted from the PDF — it may be a scanned image",
                recoverable=True,
            )

        logger.info(
            "Ingested %s: %d pages, %d chunks, sha256=%s",
            filepath.name,
            page_count,
            len(chunks),
            sha256[:12],
        )

        return IngestResult(
            doc_id=doc_id,
            source_path=str(filepath),
            sha256=sha256,
            page_count=page_count,
            chunks=chunks,
            page_texts=page_texts,
        )

    def _chunk_text(
        self,
        text: str,
        page: int,
        words: list,
        page_width: float,
        page_height: float,
    ) -> List[ChunkMeta]:
        """
        Split text into overlapping chunks of ~CHUNK_SIZE characters.

        When word-level positions are available, compute the bbox of
        each chunk from the words it spans. Otherwise, use the full
        page bbox as a fallback.
        """
        chunks: List[ChunkMeta] = []
        chunk_idx = 0

        if not text.strip():
            return chunks

        start = 0
        text_len = len(text)

        while start < text_len:
            end = min(start + self.CHUNK_SIZE, text_len)

            # Extend to word boundary
            if end < text_len:
                while end < text_len and text[end] not in " \n\t":
                    end += 1

            chunk_text = text[start:end].strip()
            if chunk_text:
                bbox = self._compute_bbox(
                    start, end, text, words, page_width, page_height
                )

                chunk_id = f"{page}_{chunk_idx}"
                chunks.append(
                    ChunkMeta(
                        chunk_id=chunk_id,
                        page=page,
                        text=chunk_text,
                        bbox=bbox,
                        char_start=start,
                        char_end=end,
                    )
                )
                chunk_idx += 1

            # Advance start, ensuring forward progress
            next_start = end - self.CHUNK_OVERLAP
            if next_start <= start:
                next_start = end  # No overlap if chunk is too small
            start = next_start

        return chunks

    def _compute_bbox(
        self,
        char_start: int,
        char_end: int,
        text: str,
        words: list,
        page_width: float,
        page_height: float,
    ) -> tuple[float, float, float, float]:
        """
        Compute the bounding box for a text span.

        If word-level positions are available, find the min/max coordinates
        of words within the character span. Otherwise, return the full page
        bbox normalized to [0, 1].
        """
        if not words:
            return (0.0, 0.0, 1.0, 1.0)

        min_x0 = float("inf")
        min_y0 = float("inf")
        max_x1 = float("-inf")
        max_y1 = float("-inf")
        found = False

        char_pos = 0
        for word in words:
            word_text = word.get("text", "")
            word_len = len(word_text)
            word_start = char_pos
            word_end = char_pos + word_len

            if word_start < char_end and word_end > char_start:
                x0 = float(word.get("x0", 0))
                y0 = float(word.get("top", 0))
                x1 = float(word.get("x1", 0))
                y1 = float(word.get("bottom", 0))

                min_x0 = min(min_x0, x0)
                min_y0 = min(min_y0, y0)
                max_x1 = max(max_x1, x1)
                max_y1 = max(max_y1, y1)
                found = True

            char_pos = word_end
            if char_pos < len(text) and text[char_pos] == " ":
                char_pos += 1

        if not found or min_x0 == float("inf"):
            return (0.0, 0.0, 1.0, 1.0)

        return (
            max(0.0, min(min_x0 / page_width, 1.0)),
            max(0.0, min(min_y0 / page_height, 1.0)),
            max(0.0, min(max_x1 / page_width, 1.0)),
            max(0.0, min(max_y1 / page_height, 1.0)),
        )