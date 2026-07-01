"""
sidecar/masters/word/context_extractor.py
==========================================
Rich context extractor for .docx documents.
Targets <200ms for 50-page documents.

Key outputs
-----------
ParagraphInfo   — per-paragraph metadata including run-level formatting
WordDocumentContext — full document state snapshot
"""

from __future__ import annotations

import re
import time
import logging
from dataclasses import dataclass
from typing import List

log = logging.getLogger("kairo-sidecar.word.context_extractor")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ParagraphInfo:
    """Rich per-paragraph metadata extracted from a .docx paragraph."""

    index: int
    text: str
    style_name: str
    level: int  # heading level (0 = body text)
    is_list: bool
    runs: List[dict]  # [{"text": str, "bold": bool, "italic": bool, "font_size": float}]
    word_count: int


@dataclass
class WordDocumentContext:
    """Full document snapshot for prompt assembly."""

    paragraphs: List[ParagraphInfo]
    purpose: str  # legal / academic / business_memo / technical / report / creative
    styles_used: List[str]
    section_count: int
    total_words: int
    extraction_ms: float


# ---------------------------------------------------------------------------
# Extractor implementation
# ---------------------------------------------------------------------------


class WordContextExtractor:
    """
    Extracts rich context from a python-docx Document object.

    Performance target
    ------------------
    Must complete under 200ms for 50-page (~5 000-paragraph) documents.
    We use a single pass over doc.paragraphs with no re-open of the file.
    """

    # ── Purpose-detection keyword sets ────────────────────────────────────────
    _LEGAL_KEYWORDS = {
        "whereas",
        "herein",
        "hereinafter",
        "party",
        "parties",
        "agreement",
        "non-disclosure",
        "nda",
        "indemnify",
        "covenant",
        "governing law",
    }
    _ACADEMIC_KEYWORDS = {
        "abstract",
        "references",
        "bibliography",
        "hypothesis",
        "methodology",
        "literature review",
        "conclusion",
        "appendix",
    }
    _MEMO_KEYWORDS = {"to:", "from:", "re:", "date:", "subject:", "cc:"}
    _TECHNICAL_KEYWORDS = {
        "installation",
        "configuration",
        "api",
        "endpoint",
        "deployment",
        "docker",
        "bash",
        "shell",
        "repository",
    }
    _REPORT_KEYWORDS = {
        "executive summary",
        "findings",
        "recommendations",
        "key performance",
        "kpi",
        "dashboard",
    }
    _CREATIVE_KEYWORDS = {"she said", "he said", '"', "\u201c", "\u201d"}  # dialogue indicators

    def extract(self, doc) -> WordDocumentContext:
        """
        Extract a WordDocumentContext from an open python-docx Document.

        Parameters
        ----------
        doc : docx.Document
            An already-opened python-docx Document instance.

        Returns
        -------
        WordDocumentContext
        """
        t0 = time.perf_counter()

        paragraphs: List[ParagraphInfo] = []
        total_words = 0
        seen_styles = set()
        styles_used = []

        for i, para in enumerate(doc.paragraphs):
            text = para.text or ""
            word_count = len(text.split())
            total_words += word_count

            # Heading level
            level = 0
            style_name = para.style.name if para.style else "Normal"
            if style_name not in seen_styles:
                seen_styles.add(style_name)
                styles_used.append(style_name)

            heading_match = re.match(r"Heading (\d+)", style_name)
            if heading_match:
                level = int(heading_match.group(1))

            # List detection
            is_list = False
            try:
                pPr = para._p.pPr
                if pPr is not None and pPr.numPr is not None:
                    is_list = True
            except Exception:
                pass
            if not is_list and ("List" in style_name or "bullet" in style_name.lower()):
                is_list = True

            # Run-level formatting
            runs = []
            for run in para.runs:
                font_size = 0.0
                bold = False
                italic = False
                try:
                    rPr = run._r.rPr
                    if rPr is not None:
                        bold = bool(rPr.bold)
                        italic = bool(rPr.italic)
                        sz = rPr.sz
                        if sz is not None and sz.val is not None:
                            font_size = sz.val / 2.0
                    else:
                        bold = bool(run.bold)
                        italic = bool(run.italic)
                except Exception:
                    try:
                        bold = bool(run.bold)
                        italic = bool(run.italic)
                    except Exception:
                        pass

                runs.append(
                    {
                        "text": run.text,
                        "bold": bold,
                        "italic": italic,
                        "font_size": font_size,
                    }
                )

            paragraphs.append(
                ParagraphInfo(
                    index=i,
                    text=text[:500],  # cap per-paragraph for memory safety
                    style_name=style_name,
                    level=level,
                    is_list=is_list,
                    runs=runs,
                    word_count=word_count,
                )
            )

        section_count = max(1, len(list(doc.sections)))
        purpose = self._detect_purpose(paragraphs)

        elapsed_ms = (time.perf_counter() - t0) * 1000
        if elapsed_ms > 200:
            log.warning(
                f"WordContextExtractor.extract: took {elapsed_ms:.1f}ms "
                "(target: <200ms). Document may be very large."
            )

        return WordDocumentContext(
            paragraphs=paragraphs,
            purpose=purpose,
            styles_used=styles_used,
            section_count=section_count,
            total_words=total_words,
            extraction_ms=elapsed_ms,
        )

    # ── Purpose detection ─────────────────────────────────────────────────────

    def _detect_purpose(self, paragraphs: List[ParagraphInfo]) -> str:
        """
        Classify the document purpose from the first 50 paragraphs.

        Rules (evaluated in priority order)
        ------------------------------------
        legal        : contains "WHEREAS", "HEREIN", "PARTY" or related legal terms
        academic     : contains "Abstract", "References", citation markers
        business_memo: contains "To:", "From:", "Re:" header block
        technical    : contains code blocks, numbered sections like 1.1.1, API keywords
        report       : contains "Executive Summary", "Findings", KPI language
        creative     : narrative prose with dialogue indicators
        """
        # Analyse first 50 paragraphs for efficiency
        sample = paragraphs[:50]
        sample_text = " ".join(p.text.lower() for p in sample)

        # Legal
        if any(kw in sample_text for kw in self._LEGAL_KEYWORDS):
            return "legal"

        # Academic
        if any(kw in sample_text for kw in self._ACADEMIC_KEYWORDS):
            return "academic"

        # Business memo (check first 15 paragraphs for header block)
        memo_sample = " ".join(p.text.lower() for p in sample[:15])
        if any(kw in memo_sample for kw in self._MEMO_KEYWORDS):
            return "business_memo"

        # Technical
        if any(kw in sample_text for kw in self._TECHNICAL_KEYWORDS):
            return "technical"

        # Report
        if any(kw in sample_text for kw in self._REPORT_KEYWORDS):
            return "report"

        # Creative (dialogue heuristic)
        if any(kw in sample_text for kw in self._CREATIVE_KEYWORDS):
            return "creative"

        return "business_memo"  # safe default

    # ── Style extraction ──────────────────────────────────────────────────────

    def _extract_styles(self, doc) -> List[str]:
        """
        Return a deduplicated list of paragraph style names used in the document.
        Iterates doc.paragraphs once — no extra file I/O.
        """
        seen: set = set()
        styles: List[str] = []
        for para in doc.paragraphs:
            name = para.style.name if para.style else "Normal"
            if name not in seen:
                seen.add(name)
                styles.append(name)
        return styles
