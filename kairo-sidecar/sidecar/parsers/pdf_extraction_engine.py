"""
Multi-Tier PDF Extraction Engine for Kairo Phantom Domain 4.

Tier 1 (PyMuPDF/fitz): Fast born-digital PDFs, ~10ms, column-aware blocks
Tier 2 (OpenDataLoader): Complex layouts, tables, charts, headings, hybrid AI
Tier 3 (olmOCR VLM): Scanned/image-only PDFs, Qwen2.5-VL-7B-Instruct
Tier 4 (Surya): Non-Latin scripts (90+ languages), LaTeX OCR, layout analysis

Fallback chain: tries tiers in order, falls back if text yield is insufficient.
All engines are optional — graceful degradation if not installed.
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("kairo-sidecar.pdf_extraction_engine")


# ---------------------------------------------------------------------------
# Enumerations & Data Structures
# ---------------------------------------------------------------------------


class ExtractionTier(Enum):
    """Identifies which extraction engine produced the result."""

    PYMUPDF = 1
    OPENDATALOADER = 2
    OLMOCR = 3
    SURYA = 4


@dataclass
class PdfExtractionResult:
    """
    Structured result from the PDF extraction engine.

    Attributes:
        text:             Full plain-text content of the document.
        markdown:         Markdown-formatted representation (headings, bullets, tables).
        tables:           List of extracted tables.  Each entry:
                          {'headers': List[str], 'rows': List[List[str]],
                           'page': int, 'caption': str}
        images:           List of image metadata entries.  Each entry:
                          {'page': int, 'bbox': [x0, y0, x1, y1], 'caption': str}
        headings:         Detected section headings.  Each entry:
                          {'text': str, 'level': int, 'page': int}
        metadata:         Raw PDF metadata plus engine diagnostics.
        tier_used:        Which ExtractionTier produced this result (None = fallback).
        extraction_time_ms: Wall-clock extraction time in milliseconds.
        confidence:       Estimated extraction quality, 0.0–1.0.
        language:         Dominant language code ('en', 'zh', 'ja', 'ko', 'ar').
    """

    text: str = ""
    markdown: str = ""
    tables: List[Dict[str, Any]] = field(default_factory=list)
    images: List[Dict[str, Any]] = field(default_factory=list)
    headings: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    tier_used: Optional[ExtractionTier] = None
    extraction_time_ms: float = 0.0
    confidence: float = 0.0
    language: str = "en"


# ---------------------------------------------------------------------------
# Main Engine
# ---------------------------------------------------------------------------


class PdfExtractionEngine:
    """
    Orchestrates multi-tier PDF extraction with automatic fallback.

    Usage::

        engine = PdfExtractionEngine()
        result = engine.extract("/path/to/document.pdf")
        print(result.text)
    """

    # Minimum word-count ratios required to accept a tier's output
    TIER1_THRESHOLD: float = 0.80  # 80 % of estimated word count
    TIER2_THRESHOLD: float = 0.60  # 60 %
    TIER3_THRESHOLD: float = 0.40  # 40 %

    def __init__(self, offline_mode: bool = True) -> None:
        self.offline_mode: bool = offline_mode
        self._has_pymupdf: bool = self._check_pymupdf()
        self._has_opendataloader: bool = self._check_opendataloader()
        self._has_olmocr: bool = self._check_olmocr()
        self._has_surya: bool = self._check_surya()

        log.info(
            "PdfExtractionEngine initialised | "
            f"PyMuPDF={self._has_pymupdf} | "
            f"OpenDataLoader={self._has_opendataloader} | "
            f"olmOCR={self._has_olmocr} | "
            f"Surya={self._has_surya}"
        )

    # ------------------------------------------------------------------
    # Availability Checks
    # ------------------------------------------------------------------

    def _check_pymupdf(self) -> bool:
        try:
            import fitz  # noqa: F401

            return True
        except ImportError:
            return False

    def _check_opendataloader(self) -> bool:
        try:
            import opendataloader  # noqa: F401

            return True
        except ImportError:
            return False

    def _check_olmocr(self) -> bool:
        try:
            import olmocr  # noqa: F401

            return True
        except ImportError:
            return False

    def _check_surya(self) -> bool:
        try:
            from surya.ocr import run_ocr  # noqa: F401

            return True
        except ImportError:
            return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, file_path: str) -> PdfExtractionResult:
        """
        Main entry point.  Attempts tiers 1–4 in order, accepting the first
        result whose text yield meets the threshold for that tier.  If language
        is non-English, Tier 4 (Surya) is always attempted.

        Args:
            file_path: Absolute or relative path to the PDF file.

        Returns:
            A :class:`PdfExtractionResult` populated by the best available tier.
        """
        file_path = str(Path(file_path).resolve())
        if not os.path.isfile(file_path):
            log.error(f"PDF file not found: {file_path}")
            result = PdfExtractionResult()
            result.metadata["error"] = f"File not found: {file_path}"
            return result

        t_start = time.perf_counter()

        language: str = self._detect_language(file_path)
        estimated_words: int = self._estimate_word_count(file_path)
        log.info(
            f"Extracting '{file_path}' | lang={language} | " f"estimated_words≈{estimated_words}"
        )

        result: Optional[PdfExtractionResult] = None

        # --- Tier 1: PyMuPDF ---
        if self._has_pymupdf:
            try:
                raw = self._tier1_pymupdf(file_path)
                word_count = len(raw.get("text", "").split())
                ratio = word_count / max(estimated_words, 1)
                log.debug(f"Tier 1 word ratio: {ratio:.2f}")
                if ratio >= self.TIER1_THRESHOLD:
                    result = self._build_result(
                        raw, ExtractionTier.PYMUPDF, language, confidence=0.95
                    )
            except Exception as exc:
                log.warning(f"Tier 1 (PyMuPDF) failed: {exc}")

        # --- Tier 2: OpenDataLoader (or enhanced-fitz fallback) ---
        if result is None:
            try:
                raw = self._tier2_opendataloader(file_path)
                word_count = len(raw.get("text", "").split())
                ratio = word_count / max(estimated_words, 1)
                log.debug(f"Tier 2 word ratio: {ratio:.2f}")
                if ratio >= self.TIER2_THRESHOLD:
                    result = self._build_result(
                        raw, ExtractionTier.OPENDATALOADER, language, confidence=0.85
                    )
            except Exception as exc:
                log.warning(f"Tier 2 (OpenDataLoader) failed: {exc}")

        # --- Tier 3: olmOCR ---
        if result is None:
            try:
                raw = self._tier3_olmocr(file_path)
                word_count = len(raw.get("text", "").split())
                ratio = word_count / max(estimated_words, 1)
                log.debug(f"Tier 3 word ratio: {ratio:.2f}")
                if ratio >= self.TIER3_THRESHOLD:
                    result = self._build_result(
                        raw, ExtractionTier.OLMOCR, language, confidence=0.75
                    )
            except Exception as exc:
                log.warning(f"Tier 3 (olmOCR) failed: {exc}")

        # --- Tier 4: Surya (always if non-English OR all prior tiers failed) ---
        if result is None or language != "en":
            try:
                raw = self._tier4_surya(file_path)
                if raw.get("text", "").strip():
                    surya_result = self._build_result(
                        raw, ExtractionTier.SURYA, language, confidence=0.80
                    )
                    # Prefer Surya over partial results for non-English
                    if result is None or (
                        language != "en" and len(surya_result.text) > len(result.text)
                    ):
                        result = surya_result
            except Exception as exc:
                log.warning(f"Tier 4 (Surya) failed: {exc}")

        # --- Final fallback: whatever fitz can provide ---
        if result is None:
            fallback_text = self._fallback_extract(file_path)
            result = PdfExtractionResult(
                text=fallback_text,
                markdown=fallback_text,
                tier_used=None,
                confidence=0.1,
                language=language,
            )
            result.metadata["warning"] = "All extraction tiers failed; raw fallback used."
            log.warning("All tiers failed — using raw fallback text.")

        elapsed_ms = (time.perf_counter() - t_start) * 1000.0
        result.extraction_time_ms = elapsed_ms
        result.language = language
        result.metadata.setdefault("file_path", file_path)
        result.metadata.setdefault("estimated_words", estimated_words)

        log.info(
            f"Extraction complete | tier={result.tier_used} | "
            f"words={len(result.text.split())} | "
            f"confidence={result.confidence:.2f} | "
            f"time={elapsed_ms:.1f}ms"
        )
        return result

    # ------------------------------------------------------------------
    # Language Detection
    # ------------------------------------------------------------------

    def _detect_language(self, file_path: str) -> str:
        """
        Detect dominant script by sampling the first 1 000 characters of
        extracted text.  Returns one of: 'zh', 'ja', 'ko', 'ar', 'en'.
        """
        sample = ""
        try:
            import fitz

            with fitz.open(file_path) as doc:
                for page in doc:
                    sample += page.get_text()
                    if len(sample) >= 1000:
                        break
        except ImportError:
            return "en"
        except Exception as exc:
            log.debug(f"Language detection error: {exc}")
            return "en"

        sample = sample[:1000]
        if not sample.strip():
            return "en"

        cjk_count = 0
        arabic_count = 0
        hangul_count = 0
        total = 0

        for ch in sample:
            if ch.isspace():
                continue
            total += 1
            unicodedata.name(ch, "")
            unicodedata.category(ch)
            cp = ord(ch)

            # CJK Unified Ideographs (covers Chinese and Japanese Kanji)
            if 0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or 0x20000 <= cp <= 0x2A6DF:
                cjk_count += 1
            # Hiragana / Katakana (Japanese-specific)
            elif 0x3040 <= cp <= 0x30FF:
                cjk_count += 1
            # Hangul (Korean)
            elif 0xAC00 <= cp <= 0xD7AF or 0x1100 <= cp <= 0x11FF:
                hangul_count += 1
            # Arabic block
            elif 0x0600 <= cp <= 0x06FF or 0x0750 <= cp <= 0x077F:
                arabic_count += 1

        if total == 0:
            return "en"

        cjk_ratio = cjk_count / total
        hangul_ratio = hangul_count / total
        arabic_ratio = arabic_count / total

        if hangul_ratio > 0.15:
            return "ko"
        if arabic_ratio > 0.15:
            return "ar"
        if cjk_ratio > 0.15:
            # Distinguish Japanese vs Chinese by Hiragana/Katakana presence
            hira_kata = sum(1 for ch in sample if 0x3040 <= ord(ch) <= 0x30FF)
            return "ja" if hira_kata > 5 else "zh"
        return "en"

    # ------------------------------------------------------------------
    # Word Count Estimation
    # ------------------------------------------------------------------

    def _estimate_word_count(self, file_path: str) -> int:
        """
        Estimate word count using actual fitz text count when available,
        falling back to a page-based heuristic for scanned PDFs.
        """
        try:
            import fitz

            word_count = 0
            page_count = 0
            with fitz.open(file_path) as doc:
                page_count = len(doc)
                for page in doc:
                    word_count += len(page.get_text().split())
            if word_count > 5:
                # Born-digital PDF with actual text
                return max(word_count, 1)
            else:
                # Scanned/image-only PDF: estimate 300 words per page
                return max(page_count * 300, 1)
        except Exception:
            # Final fallback: file size heuristic (rough)
            try:
                size = os.path.getsize(file_path)
                return max(size // 100, 1)
            except OSError:
                return 1

    # ------------------------------------------------------------------
    # Tier 1: PyMuPDF
    # ------------------------------------------------------------------

    def _tier1_pymupdf(self, file_path: str) -> Dict[str, Any]:
        """
        Extract using PyMuPDF (fitz).

        - Text blocks are retrieved with coordinate metadata.
        - Headings are detected by font-size heuristic (fontsize > 14).
        - Tables extracted via page.find_tables() when available.
        - Column-aware ordering preserved by sort on (y, x) block coordinates.

        Returns a raw dict consumed by :meth:`_build_result`.
        """
        try:
            import fitz  # PyMuPDF — AGPL, lazy import inside try/except
        except ImportError:
            raise ImportError("PyMuPDF (fitz) is required for PDF extraction")

        text_parts: List[str] = []
        markdown_parts: List[str] = []
        tables: List[Dict[str, Any]] = []
        headings: List[Dict[str, Any]] = []
        images: List[Dict[str, Any]] = []
        metadata: Dict[str, Any] = {}

        with fitz.open(file_path) as doc:
            metadata = dict(doc.metadata)
            metadata["pages"] = len(doc)
            for page_num, page in enumerate(doc, start=1):
                page_text_parts: List[Tuple[float, float, str]] = []

                # Retrieve rich text blocks with font information
                raw_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
                for block in raw_dict.get("blocks", []):
                    if block.get("type") != 0:  # type 0 = text
                        # Image block
                        bbox = block.get("bbox", [0, 0, 0, 0])
                        images.append(
                            {
                                "page": page_num,
                                "bbox": list(bbox),
                                "caption": "",
                            }
                        )
                        continue

                    block_text_lines: List[str] = []
                    max_font_size: float = 0.0

                    for line in block.get("lines", []):
                        line_spans: List[str] = []
                        for span in line.get("spans", []):
                            span_text = span.get("text", "").strip()
                            if span_text:
                                line_spans.append(span_text)
                                fs = span.get("size", 0.0)
                                if fs > max_font_size:
                                    max_font_size = fs
                        if line_spans:
                            block_text_lines.append(" ".join(line_spans))

                    block_text = "\n".join(block_text_lines).strip()
                    if not block_text:
                        continue

                    bbox = block.get("bbox", (0, 0, 0, 0))
                    # Sort key preserves reading order (top-to-bottom, left-to-right)
                    sort_y = bbox[1]
                    sort_x = bbox[0]
                    page_text_parts.append((sort_y, sort_x, block_text, max_font_size))

                # Sort blocks in natural reading order
                page_text_parts.sort(key=lambda t: (t[0], t[1]))

                for _, _, block_text, font_size in page_text_parts:
                    text_parts.append(block_text)

                    # Heading detection: font size > 14 → heading
                    if font_size > 14.0:
                        level = 1 if font_size > 20.0 else 2
                        headings.append(
                            {
                                "text": block_text.replace("\n", " "),
                                "level": level,
                                "page": page_num,
                            }
                        )
                        md_prefix = "#" * level
                        markdown_parts.append(f"{md_prefix} {block_text.replace(chr(10), ' ')}")
                    else:
                        markdown_parts.append(block_text)

                # Table extraction
                try:
                    tab_finder = page.find_tables()
                    for tab in tab_finder:
                        extracted = tab.extract()
                        if not extracted:
                            continue
                        headers: List[str] = []
                        rows: List[List[str]] = []
                        if extracted:
                            headers = [str(c) if c is not None else "" for c in extracted[0]]
                            rows = [
                                [str(c) if c is not None else "" for c in row]
                                for row in extracted[1:]
                            ]
                        tables.append(
                            {
                                "headers": headers,
                                "rows": rows,
                                "page": page_num,
                                "caption": "",
                            }
                        )
                except Exception as exc:
                    log.debug(f"Table extraction skipped on page {page_num}: {exc}")

        full_text = "\n\n".join(text_parts)
        full_markdown = "\n\n".join(markdown_parts)

        return {
            "text": full_text,
            "markdown": full_markdown,
            "tables": tables,
            "images": images,
            "headings": headings,
            "metadata": metadata,
        }

    # ------------------------------------------------------------------
    # Tier 2: OpenDataLoader (with enhanced-fitz simulation fallback)
    # ------------------------------------------------------------------

    def _tier2_opendataloader(self, file_path: str) -> Dict[str, Any]:
        """
        Attempt extraction with the OpenDataLoader library.  If not installed,
        falls back to an enhanced fitz extraction that applies richer table
        detection and heading heuristics — functionally equivalent for most
        born-digital PDFs.

        Returns a raw dict consumed by :meth:`_build_result`.
        """
        if self._has_opendataloader:
            return self._tier2_via_opendataloader(file_path)
        # Simulated OpenDataLoader using enhanced fitz
        return self._tier2_enhanced_fitz(file_path)

    def _tier2_via_opendataloader(self, file_path: str) -> Dict[str, Any]:
        """Real OpenDataLoader extraction path."""
        try:
            from opendataloader import PDFExtractor  # type: ignore

            extractor = PDFExtractor(
                table_extraction=True,
                formula_extraction=True,
            )
            doc_result = extractor.extract(file_path)

            text = getattr(doc_result, "text", "") or ""
            markdown = getattr(doc_result, "markdown", "") or text
            raw_tables = getattr(doc_result, "tables", []) or []
            raw_headings = getattr(doc_result, "headings", []) or []
            raw_images = getattr(doc_result, "images", []) or []
            meta = getattr(doc_result, "metadata", {}) or {}

            tables: List[Dict[str, Any]] = []
            for t in raw_tables:
                if isinstance(t, dict):
                    tables.append(
                        {
                            "headers": t.get("headers", []),
                            "rows": t.get("rows", []),
                            "page": t.get("page", 0),
                            "caption": t.get("caption", ""),
                        }
                    )

            headings: List[Dict[str, Any]] = []
            for h in raw_headings:
                if isinstance(h, dict):
                    headings.append(
                        {
                            "text": h.get("text", ""),
                            "level": int(h.get("level", 1)),
                            "page": int(h.get("page", 0)),
                        }
                    )

            images: List[Dict[str, Any]] = []
            for img in raw_images:
                if isinstance(img, dict):
                    images.append(
                        {
                            "page": img.get("page", 0),
                            "bbox": img.get("bbox", [0, 0, 0, 0]),
                            "caption": img.get("caption", ""),
                        }
                    )

            return {
                "text": text,
                "markdown": markdown,
                "tables": tables,
                "images": images,
                "headings": headings,
                "metadata": dict(meta),
            }

        except Exception as exc:
            log.warning(
                f"OpenDataLoader library raised an error: {exc}; falling back to enhanced fitz"
            )
            return self._tier2_enhanced_fitz(file_path)

    def _tier2_enhanced_fitz(self, file_path: str) -> Dict[str, Any]:
        """
        Enhanced fitz extraction that simulates OpenDataLoader's richer output.

        Improvements over Tier 1:
        - Deeper heading detection using font flags (bold) in addition to size.
        - Multi-column detection via X-coordinate clustering.
        - Aggressive table extraction with header-row identification.
        - Caption extraction for tables and images.
        """
        try:
            import fitz
        except ImportError:
            return {
                "text": "",
                "markdown": "",
                "tables": [],
                "images": [],
                "headings": [],
                "metadata": {},
            }

        text_parts: List[str] = []
        markdown_parts: List[str] = []
        tables: List[Dict[str, Any]] = []
        headings: List[Dict[str, Any]] = []
        images: List[Dict[str, Any]] = []
        metadata: Dict[str, Any] = {}

        # Font size statistics for adaptive heading thresholds
        all_font_sizes: List[float] = []

        with fitz.open(file_path) as doc:
            metadata = dict(doc.metadata)

            # First pass: gather font size distribution
            for page in doc:
                raw_dict = page.get_text("dict")
                for block in raw_dict.get("blocks", []):
                    if block.get("type") != 0:
                        continue
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            fs = span.get("size", 0.0)
                            if fs > 0:
                                all_font_sizes.append(fs)

            body_size: float = 10.0
            if all_font_sizes:
                sorted_sizes = sorted(all_font_sizes)
                # Body size ≈ median font size
                body_size = sorted_sizes[len(sorted_sizes) // 2]
            heading_threshold = body_size * 1.25  # 25% larger than body

            # Second pass: extract with adaptive heuristics
            for page_num, page in enumerate(doc, start=1):
                raw_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
                page_blocks: List[Tuple[float, float, str, float, int]] = []

                for block in raw_dict.get("blocks", []):
                    if block.get("type") != 0:
                        bbox = block.get("bbox", [0, 0, 0, 0])
                        images.append(
                            {
                                "page": page_num,
                                "bbox": list(bbox),
                                "caption": "",
                            }
                        )
                        continue

                    block_lines: List[str] = []
                    max_font_size: float = 0.0
                    bold_flag: int = 0

                    for line in block.get("lines", []):
                        line_spans: List[str] = []
                        for span in line.get("spans", []):
                            span_text = span.get("text", "").strip()
                            if span_text:
                                line_spans.append(span_text)
                                fs = span.get("size", 0.0)
                                if fs > max_font_size:
                                    max_font_size = fs
                                # flags bit 4 = bold
                                flags = span.get("flags", 0)
                                if flags & 2**4:  # bold bit
                                    bold_flag = 1
                        if line_spans:
                            block_lines.append(" ".join(line_spans))

                    block_text = "\n".join(block_lines).strip()
                    if not block_text:
                        continue

                    bbox = block.get("bbox", (0, 0, 0, 0))
                    page_blocks.append((bbox[1], bbox[0], block_text, max_font_size, bold_flag))

                page_blocks.sort(key=lambda t: (t[0], t[1]))

                for _, _, block_text, font_size, is_bold in page_blocks:
                    text_parts.append(block_text)
                    is_heading = (font_size > heading_threshold) or (
                        is_bold
                        and font_size >= body_size
                        and len(block_text.split("\n")) == 1
                        and len(block_text) < 120
                    )

                    if is_heading:
                        if font_size > heading_threshold * 1.4:
                            level = 1
                        elif font_size > heading_threshold * 1.15:
                            level = 2
                        else:
                            level = 3
                        headings.append(
                            {
                                "text": block_text.replace("\n", " "),
                                "level": level,
                                "page": page_num,
                            }
                        )
                        md_prefix = "#" * level
                        markdown_parts.append(f"{md_prefix} {block_text.replace(chr(10), ' ')}")
                    else:
                        markdown_parts.append(block_text)

                # Enhanced table extraction
                try:
                    tab_finder = page.find_tables()
                    for tab in tab_finder:
                        extracted = tab.extract()
                        if not extracted:
                            continue
                        headers = [str(c) if c is not None else "" for c in extracted[0]]
                        rows = [
                            [str(c) if c is not None else "" for c in row] for row in extracted[1:]
                        ]
                        # Attempt to find a caption line above/below the table bbox
                        caption = ""
                        try:
                            tab_bbox = tab.bbox  # (x0, y0, x1, y1)
                            nearby_text = page.get_text(
                                "text",
                                clip=fitz.Rect(
                                    tab_bbox[0], max(0, tab_bbox[1] - 20), tab_bbox[2], tab_bbox[1]
                                ),
                            ).strip()
                            if nearby_text and len(nearby_text) < 200:
                                caption = nearby_text
                        except Exception:
                            pass
                        tables.append(
                            {
                                "headers": headers,
                                "rows": rows,
                                "page": page_num,
                                "caption": caption,
                            }
                        )
                except Exception as exc:
                    log.debug(f"Enhanced table extraction skipped on page {page_num}: {exc}")

        return {
            "text": "\n\n".join(text_parts),
            "markdown": "\n\n".join(markdown_parts),
            "tables": tables,
            "images": images,
            "headings": headings,
            "metadata": metadata,
        }

    # ------------------------------------------------------------------
    # Tier 3: olmOCR (with image-based fallback)
    # ------------------------------------------------------------------

    def _tier3_olmocr(self, file_path: str) -> Dict[str, Any]:
        """
        Attempt OCR via olmOCR (Qwen2.5-VL-7B-Instruct based).
        Falls back to a PDF-page-to-image pipeline using fitz when olmOCR
        is not installed or the model is not available.

        Returns a raw dict consumed by :meth:`_build_result`.
        """
        if self._has_olmocr:
            return self._tier3_via_olmocr(file_path)
        return self._tier3_fitz_image_fallback(file_path)

    def _tier3_via_olmocr(self, file_path: str) -> Dict[str, Any]:
        """Real olmOCR extraction path."""
        try:
            from olmocr import OCR  # type: ignore

            ocr = OCR()
            raw_result = ocr.process_pdf(file_path)

            pages_text: List[str] = []
            if hasattr(raw_result, "pages"):
                for page in raw_result.pages:
                    pages_text.append(getattr(page, "text", "") or "")
            elif isinstance(raw_result, str):
                pages_text = [raw_result]
            elif isinstance(raw_result, dict):
                pages_text = [raw_result.get("text", "")]

            full_text = "\n\n".join(p for p in pages_text if p.strip())

            return {
                "text": full_text,
                "markdown": full_text,
                "tables": [],
                "images": [],
                "headings": [],
                "metadata": {"ocr_engine": "olmOCR"},
            }
        except Exception as exc:
            log.warning(f"olmOCR failed: {exc}; trying image fallback")
            return self._tier3_fitz_image_fallback(file_path)

    def _tier3_fitz_image_fallback(self, file_path: str) -> Dict[str, Any]:
        """
        Convert PDF pages to PNG images using fitz, then attempt OCR with
        pytesseract if available.  This is a best-effort path for scanned PDFs
        when no VLM is installed.
        """
        try:
            import fitz
        except ImportError:
            return {
                "text": "",
                "markdown": "",
                "tables": [],
                "images": [],
                "headings": [],
                "metadata": {},
            }

        pages_text: List[str] = []
        tmp_dir = tempfile.mkdtemp(prefix="kairo_ocr_")

        try:
            with fitz.open(file_path) as doc:
                for page_num, page in enumerate(doc, start=1):
                    # Render at 150 DPI
                    mat = fitz.Matrix(150 / 72, 150 / 72)
                    pix = page.get_pixmap(matrix=mat, alpha=False)
                    img_path = os.path.join(tmp_dir, f"page_{page_num:04d}.png")
                    pix.save(img_path)
                    pix = None  # free memory

                    # Attempt tesseract OCR
                    page_text = ""
                    try:
                        import pytesseract  # type: ignore
                        from PIL import Image  # type: ignore

                        with Image.open(img_path) as img:
                            page_text = pytesseract.image_to_string(img)
                    except ImportError:
                        # No OCR engine available — record placeholder
                        page_text = f"[Page {page_num} — image-only, no OCR engine available]"
                    except Exception as ocr_exc:
                        log.debug(f"Tesseract failed on page {page_num}: {ocr_exc}")
                        page_text = f"[Page {page_num} — OCR failed]"

                    if page_text.strip():
                        pages_text.append(page_text.strip())

                    # Clean up temp image
                    try:
                        os.remove(img_path)
                    except OSError:
                        pass

        finally:
            try:
                os.rmdir(tmp_dir)
            except OSError:
                pass

        full_text = "\n\n".join(pages_text)
        return {
            "text": full_text,
            "markdown": full_text,
            "tables": [],
            "images": [],
            "headings": [],
            "metadata": {"ocr_engine": "tesseract_fallback"},
        }

    # ------------------------------------------------------------------
    # Tier 4: Surya
    # ------------------------------------------------------------------

    def _tier4_surya(self, file_path: str) -> Dict[str, Any]:
        """
        Extract using the Surya OCR library (supports 90+ languages, LaTeX,
        and complex layouts).

        Surya API::

            from surya.ocr import run_ocr
            from surya.model.detection.model import load_model, load_processor
            from surya.model.recognition.model import load_model as load_rec_model
            from surya.model.recognition.processor import load_processor as load_rec_processor

        Returns a raw dict consumed by :meth:`_build_result`.
        """
        if not self._has_surya:
            log.debug("Surya not installed; Tier 4 unavailable.")
            return {
                "text": "",
                "markdown": "",
                "tables": [],
                "images": [],
                "headings": [],
                "metadata": {},
            }

        try:
            import fitz
            from surya.ocr import run_ocr  # type: ignore
        except ImportError as exc:
            log.warning(f"Surya/fitz import failed: {exc}")
            return {
                "text": "",
                "markdown": "",
                "tables": [],
                "images": [],
                "headings": [],
                "metadata": {},
            }

        # Load Surya models (cached by the library after first load)
        det_processor = None
        det_model = None
        rec_model = None
        rec_processor = None

        try:
            from surya.model.detection.model import load_model as load_det_model  # type: ignore
            from surya.model.detection.model import load_processor as load_det_processor  # type: ignore

            det_processor = load_det_processor()
            det_model = load_det_model()
        except Exception as exc:
            log.warning(f"Surya detection model load failed: {exc}")

        try:
            from surya.model.recognition.model import load_model as load_rec_model  # type: ignore
            from surya.model.recognition.processor import load_processor as load_rec_processor  # type: ignore

            rec_model = load_rec_model()
            rec_processor = load_rec_processor()
        except Exception as exc:
            log.warning(f"Surya recognition model load failed: {exc}")

        pages_text: List[str] = []
        headings: List[Dict[str, Any]] = []
        tmp_dir = tempfile.mkdtemp(prefix="kairo_surya_")

        try:
            with fitz.open(file_path) as doc:
                for page_num, page in enumerate(doc, start=1):
                    mat = fitz.Matrix(150 / 72, 150 / 72)
                    pix = page.get_pixmap(matrix=mat, alpha=False)
                    img_path = os.path.join(tmp_dir, f"page_{page_num:04d}.png")
                    pix.save(img_path)
                    pix = None

                    page_text = ""
                    try:
                        from PIL import Image  # type: ignore

                        with Image.open(img_path) as pil_img:
                            # Determine languages to pass to surya
                            surya_langs = self._surya_lang_codes(self._detect_language(file_path))
                            if det_model is not None and rec_model is not None:
                                predictions = run_ocr(
                                    [pil_img],
                                    [surya_langs],
                                    det_model,
                                    det_processor,
                                    rec_model,
                                    rec_processor,
                                )
                            else:
                                # Try simplified run_ocr call without explicit models
                                predictions = run_ocr(
                                    [pil_img],
                                    [surya_langs],
                                )
                            if predictions:
                                page_pred = predictions[0]
                                line_texts = []
                                for text_line in getattr(page_pred, "text_lines", []):
                                    txt = getattr(text_line, "text", "").strip()
                                    if txt:
                                        line_texts.append(txt)
                                page_text = " ".join(line_texts)
                    except Exception as ocr_exc:
                        log.debug(f"Surya OCR failed on page {page_num}: {ocr_exc}")
                        page_text = ""
                    finally:
                        try:
                            os.remove(img_path)
                        except OSError:
                            pass

                    if page_text.strip():
                        pages_text.append(page_text.strip())

        finally:
            try:
                os.rmdir(tmp_dir)
            except OSError:
                pass

        full_text = "\n\n".join(pages_text)
        return {
            "text": full_text,
            "markdown": full_text,
            "tables": [],
            "images": [],
            "headings": headings,
            "metadata": {"ocr_engine": "surya"},
        }

    @staticmethod
    def _surya_lang_codes(lang: str) -> List[str]:
        """
        Map internal language codes to Surya's BCP 47 language tag list.
        Surya accepts ISO 639-1 codes.
        """
        mapping: Dict[str, List[str]] = {
            "zh": ["zh"],
            "ja": ["ja"],
            "ko": ["ko"],
            "ar": ["ar"],
            "en": ["en"],
        }
        return mapping.get(lang, ["en"])

    # ------------------------------------------------------------------
    # Fallback Extractor
    # ------------------------------------------------------------------

    def _fallback_extract(self, file_path: str) -> str:
        """
        Absolute last-resort extractor.  Uses fitz if available, otherwise
        returns an empty string.  Never raises.
        """
        try:
            import fitz

            text_parts: List[str] = []
            with fitz.open(file_path) as doc:
                for page in doc:
                    t = page.get_text().strip()
                    if t:
                        text_parts.append(t)
            return "\n\n".join(text_parts)
        except ImportError:
            return ""
        except Exception as exc:
            log.error(f"Fallback extraction failed: {exc}")
            return ""

    # ------------------------------------------------------------------
    # Result Construction
    # ------------------------------------------------------------------

    def _build_result(
        self,
        raw: Dict[str, Any],
        tier: ExtractionTier,
        language: str,
        confidence: float,
    ) -> PdfExtractionResult:
        """
        Convert a raw extraction dict into a :class:`PdfExtractionResult`.

        Args:
            raw:        Raw extraction dict with keys: text, markdown, tables,
                        images, headings, metadata.
            tier:       The tier that produced this raw dict.
            language:   Detected document language.
            confidence: Confidence score 0.0–1.0 assigned to this tier.

        Returns:
            A fully populated :class:`PdfExtractionResult`.
        """
        result = PdfExtractionResult(
            text=raw.get("text", ""),
            markdown=raw.get("markdown", "") or raw.get("text", ""),
            tables=raw.get("tables", []),
            images=raw.get("images", []),
            headings=raw.get("headings", []),
            metadata=raw.get("metadata", {}),
            tier_used=tier,
            confidence=confidence,
            language=language,
        )
        return result
