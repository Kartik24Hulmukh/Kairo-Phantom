"""
mineru_parser.py
================
MinerU 3.1 subprocess-based fallback parser for scanned/complex PDFs.
Used when Docling fails or for OCR-heavy documents.

Falls back gracefully to PyMuPDF if MinerU is not installed.

Public API
----------
MineruParser              – class with .parse(file_path, format) method
parse_pdf_structured      – convenience function, same output schema as parse_docx_structured

Cache Strategy
--------------
An in-process LRU cache keyed on (absolute_path, mtime) avoids re-parsing
unchanged files between calls within the same process lifetime.
"""

import os
import json
import shutil
import logging
import subprocess
import tempfile
import threading
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("kairo-sidecar.mineru_parser")

# ---------------------------------------------------------------------------
# Optional dependency probes
# ---------------------------------------------------------------------------

# Prefer 'mineru' CLI; older installations expose 'magic-pdf'
_MINERU_CMD = shutil.which("mineru") or shutil.which("magic-pdf")
_MINERU_AVAILABLE = _MINERU_CMD is not None

if _MINERU_AVAILABLE:
    log.debug("MinerU CLI found at: %s", _MINERU_CMD)
else:
    log.debug("MinerU CLI not found – PyMuPDF fallback will be used.")

try:
    import fitz  # PyMuPDF  # type: ignore

    _PYMUPDF_AVAILABLE = True
    log.debug("PyMuPDF (fitz) is available.")
except ImportError:
    fitz = None  # type: ignore
    _PYMUPDF_AVAILABLE = False
    log.debug("PyMuPDF not installed – raw-text fallback disabled.")


# ---------------------------------------------------------------------------
# LRU-style in-process cache (keyed by (abs_path, mtime))
# Same pattern as docling_parser.
# ---------------------------------------------------------------------------

_CACHE_MAX_SIZE = 16
_cache: Dict[Tuple[str, float], Dict[str, Any]] = {}
_cache_order: List[Tuple[str, float]] = []
_cache_lock = threading.Lock()

_MINERU_TIMEOUT_SECONDS = 60


def _cache_get(abs_path: str) -> Optional[Dict[str, Any]]:
    """Return cached parse result if the file hasn't changed since last parse."""
    try:
        mtime = os.path.getmtime(abs_path)
        key = (abs_path, mtime)
        with _cache_lock:
            return _cache.get(key)
    except OSError:
        return None


def _cache_set(abs_path: str, result: Dict[str, Any]) -> None:
    """Store parse result keyed by (abs_path, current mtime)."""
    try:
        mtime = os.path.getmtime(abs_path)
        key = (abs_path, mtime)
        with _cache_lock:
            if key not in _cache:
                # Evict oldest entry if at capacity
                while len(_cache_order) >= _CACHE_MAX_SIZE:
                    oldest = _cache_order.pop(0)
                    _cache.pop(oldest, None)
                _cache_order.append(key)
            _cache[key] = result
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Heading style helpers (mirror of docling_parser helpers)
# ---------------------------------------------------------------------------

_MINERU_LEVEL_TO_WORD_STYLE: Dict[int, str] = {
    1: "Heading 1",
    2: "Heading 2",
    3: "Heading 3",
    4: "Heading 4",
    5: "Heading 5",
    6: "Heading 6",
}


def _heading_style_from_level(level: int) -> str:
    """Return Word-compatible style string for a given heading level (1-6)."""
    return _MINERU_LEVEL_TO_WORD_STYLE.get(max(1, min(level, 6)), "Heading 1")


def _is_likely_heading_block(block: dict, font_size: float, is_bold: bool) -> Tuple[bool, int]:
    """
    Heuristic for PyMuPDF blocks: bold text at > 14pt is treated as a heading.
    Returns (is_heading, level) where level is 1–3 based on font size buckets.
    """
    if is_bold and font_size > 20:
        return True, 1
    if is_bold and font_size > 16:
        return True, 2
    if is_bold and font_size > 14:
        return True, 3
    return False, 0


# ---------------------------------------------------------------------------
# MinerU output JSON → Kairo schema mapper
# ---------------------------------------------------------------------------


def _map_mineru_content_list(
    content_list: List[Dict[str, Any]],
    source_path: str,
) -> Dict[str, Any]:
    """
    Convert a MinerU 3.1 *_content_list.json items array to the Kairo schema::

        {
            "paragraphs": [...],
            "tables": [...],
            "metadata": {...}
        }

    MinerU content_list item shapes (v3.1):
    - type='text'      → body paragraph
    - type='title'     → heading (level field present, defaults to 1)
    - type='table'     → table (table_body contains HTML or markdown; table_caption optional)
    - type='equation'  → inline/display math, preserved as LaTeX text
    - type='figure'    → image caption, mapped as Normal paragraph
    """
    paragraphs: List[Dict[str, Any]] = []
    tables: List[Dict[str, Any]] = []
    p_idx = 0

    for item in content_list:
        item_type = item.get("type", "").lower()
        text = (item.get("text") or item.get("content") or "").strip()
        page = item.get("page_idx", item.get("page", None))
        if page is not None:
            page = int(page) + 1  # MinerU uses 0-based page index

        if item_type == "title":
            level = int(item.get("level", 1))
            style = _heading_style_from_level(level)
            paragraphs.append(
                {
                    "index": p_idx,
                    "text": text,
                    "style": style,
                    "level": level,
                    "page": page,
                    "runs": [{"text": text, "bold": True, "italic": False}],
                }
            )
            p_idx += 1

        elif item_type in ("text", "equation", "figure"):
            # Equations are kept as raw LaTeX / MathML string in the text field
            style = "Normal"
            paragraphs.append(
                {
                    "index": p_idx,
                    "text": text,
                    "style": style,
                    "level": 0,
                    "page": page,
                    "runs": [{"text": text, "bold": False, "italic": False}],
                }
            )
            p_idx += 1

        elif item_type == "table":
            # MinerU stores tables as HTML inside 'table_body'
            rows = _parse_mineru_table(item)
            caption = (item.get("table_caption") or "").strip()
            if caption:
                # Prepend table caption as a Normal paragraph
                paragraphs.append(
                    {
                        "index": p_idx,
                        "text": caption,
                        "style": "Normal",
                        "level": 0,
                        "page": page,
                        "runs": [{"text": caption, "bold": False, "italic": True}],
                    }
                )
                p_idx += 1
            tables.append(
                {
                    "after_paragraph_index": max(p_idx - 1, 0),
                    "rows": rows,
                    "page": page,
                }
            )

        else:
            # Unrecognised item type – treat as plain text if non-empty
            if text:
                paragraphs.append(
                    {
                        "index": p_idx,
                        "text": text,
                        "style": "Normal",
                        "level": 0,
                        "page": page,
                        "runs": [{"text": text, "bold": False, "italic": False}],
                    }
                )
                p_idx += 1

    return {
        "paragraphs": paragraphs,
        "tables": tables,
        "metadata": {
            "total_paragraphs": len(paragraphs),
            "table_count": len(tables),
        },
    }


def _parse_mineru_table(item: Dict[str, Any]) -> List[List[str]]:
    """
    Extract rows from a MinerU table item.

    MinerU v3.1 stores the table content in 'table_body' as an HTML string.
    We try a simple HTML row/cell parse; fall back to splitting on whitespace.
    """
    table_body = item.get("table_body", "") or ""
    rows: List[List[str]] = []

    # --- Attempt lightweight HTML parse ---
    if "<tr" in table_body.lower():
        try:
            import re

            tr_pattern = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
            td_pattern = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)
            tag_strip = re.compile(r"<[^>]+>")
            for tr_match in tr_pattern.finditer(table_body):
                row_html = tr_match.group(1)
                cells = [
                    tag_strip.sub("", td.group(1)).strip() for td in td_pattern.finditer(row_html)
                ]
                if cells:
                    rows.append(cells)
            return rows
        except Exception:
            pass  # fall through to raw text

    # --- Fall back: each non-empty line is a row; cells split by '|' or '\t' ---
    for line in table_body.splitlines():
        line = line.strip().strip("|")
        if not line:
            continue
        if "|" in line:
            rows.append([c.strip() for c in line.split("|") if c.strip()])
        elif "\t" in line:
            rows.append([c.strip() for c in line.split("\t") if c.strip()])
        else:
            rows.append([line])

    return rows


# ---------------------------------------------------------------------------
# PyMuPDF fallback parser
# ---------------------------------------------------------------------------


def _parse_with_pymupdf(abs_path: str) -> Dict[str, Any]:
    """
    Fallback parser using PyMuPDF (fitz).

    Extracts text blocks page-by-page and applies a heuristic to detect
    headings from font size and bold flags.
    """
    if not _PYMUPDF_AVAILABLE or fitz is None:
        raise RuntimeError("PyMuPDF (fitz) is not installed.")

    doc = fitz.open(abs_path)
    paragraphs: List[Dict[str, Any]] = []
    tables: List[Dict[str, Any]] = []
    p_idx = 0

    for page_num, page in enumerate(doc):
        page_no = page_num + 1

        # Use 'rawdict' for per-span font info (size, flags)
        try:
            raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
            blocks_data = raw.get("blocks", [])
        except Exception:
            blocks_data = []

        # Plain text blocks fallback
        if not blocks_data:
            for block in page.get_text("blocks"):
                block_text = block[4].strip() if len(block) > 4 else ""
                if block_text:
                    paragraphs.append(
                        {
                            "index": p_idx,
                            "text": block_text,
                            "style": "Normal",
                            "level": 0,
                            "page": page_no,
                            "runs": [{"text": block_text, "bold": False, "italic": False}],
                        }
                    )
                    p_idx += 1
            continue

        for block in blocks_data:
            if block.get("type") != 0:  # 0 = text block
                continue
            lines_text: List[str] = []
            max_font_size = 0.0
            is_bold_block = False
            runs: List[Dict[str, Any]] = []

            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    span_text = span.get("text", "").strip()
                    if not span_text:
                        continue
                    size = float(span.get("size", 11.0))
                    flags = int(span.get("flags", 0))
                    bold = bool(flags & 2**4)  # bit 4 = bold in PyMuPDF
                    italic = bool(flags & 2**1)  # bit 1 = italic
                    max_font_size = max(max_font_size, size)
                    if bold:
                        is_bold_block = True
                    runs.append({"text": span_text, "bold": bold, "italic": italic})
                    lines_text.append(span_text)

            full_text = " ".join(lines_text).strip()
            if not full_text:
                continue

            is_heading, h_level = _is_likely_heading_block(block, max_font_size, is_bold_block)

            if is_heading:
                style = _heading_style_from_level(h_level)
            else:
                style = "Normal"
                h_level = 0

            paragraphs.append(
                {
                    "index": p_idx,
                    "text": full_text,
                    "style": style,
                    "level": h_level,
                    "page": page_no,
                    "runs": runs if runs else [{"text": full_text, "bold": False, "italic": False}],
                }
            )
            p_idx += 1

        # Simple table extraction (PyMuPDF ≥ 1.23 find_tables API)
        try:
            tabs = page.find_tables()
            for tab in tabs:
                tab_rows = tab.extract()
                if tab_rows:
                    tables.append(
                        {
                            "after_paragraph_index": max(p_idx - 1, 0),
                            "rows": [
                                [str(c) if c is not None else "" for c in row] for row in tab_rows
                            ],
                            "page": page_no,
                        }
                    )
        except Exception:
            pass

    doc.close()
    return {
        "paragraphs": paragraphs,
        "tables": tables,
        "metadata": {
            "total_paragraphs": len(paragraphs),
            "table_count": len(tables),
        },
    }


# ---------------------------------------------------------------------------
# MineruParser class
# ---------------------------------------------------------------------------


class MineruParser:
    """
    Structured PDF parser backed by MinerU 3.1 subprocess with PyMuPDF fallback.

    parse(file_path, format) → {
        "paragraphs": [
            {
                "index": int,
                "text": str,
                "style": str,        # "Heading 1"-"Heading 6" | "Normal"
                "level": int,        # heading level (0 = body text)
                "page": int | None,  # 1-based page number
                "runs": [
                    {"text": str, "bold": bool, "italic": bool}
                ]
            },
            ...
        ],
        "tables": [
            {
                "after_paragraph_index": int,
                "rows": [[str, ...], ...],
                "page": int | None
            },
            ...
        ],
        "metadata": {
            "tier": str,                # "mineru" | "pymupdf"
            "total_paragraphs": int,
            "table_count": int,
            "file_path": str,
            "parse_timestamp": str
        }
    }
    """

    def parse(self, file_path: str, format: str = "pdf") -> Dict[str, Any]:  # noqa: A002
        """
        Parse *file_path* and return the structured document dict.

        Parameters
        ----------
        file_path : str
            Absolute or relative path to the PDF document.
        format : str
            Hint for the document format (only 'pdf' is fully supported).
        """
        abs_path = str(Path(file_path).resolve())

        # 1. Check LRU cache first
        cached = _cache_get(abs_path)
        if cached is not None:
            log.debug("MineruParser: cache hit for %s", abs_path)
            return cached

        result = None
        tier = "unknown"

        # 2. Tier A: MinerU subprocess
        if _MINERU_AVAILABLE:
            try:
                result = self._parse_with_mineru(abs_path)
                tier = "mineru"
                log.info("MineruParser: MinerU succeeded for %s", abs_path)
            except Exception as exc:
                log.warning(
                    "MineruParser: MinerU subprocess failed (%s) – falling back to PyMuPDF.",
                    exc,
                )

        # 3. Tier B: PyMuPDF fallback
        if result is None and _PYMUPDF_AVAILABLE:
            try:
                result = _parse_with_pymupdf(abs_path)
                tier = "pymupdf"
                log.info("MineruParser: PyMuPDF fallback succeeded for %s", abs_path)
            except Exception as exc:
                log.warning("MineruParser: PyMuPDF fallback failed (%s).", exc)

        if result is None:
            raise RuntimeError(
                f"MineruParser: all parsing tiers failed for {abs_path!r}. "
                "Ensure either MinerU CLI or PyMuPDF (fitz) is installed."
            )

        # Stamp metadata
        result.setdefault("metadata", {})["tier"] = tier
        result["metadata"]["file_path"] = abs_path
        result["metadata"]["parse_timestamp"] = datetime.datetime.now().isoformat()

        # Store in cache
        _cache_set(abs_path, result)
        return result

    # ------------------------------------------------------------------
    # Tier A: MinerU 3.1 subprocess
    # ------------------------------------------------------------------

    def _parse_with_mineru(self, abs_path: str) -> Dict[str, Any]:
        """
        Invoke the MinerU CLI as a subprocess and parse its JSON output.

        MinerU 3.1 command::

            magic-pdf -p <file> -o <outdir> -m auto

        Output layout::

            <outdir>/<stem>/auto/<stem>_content_list.json
        """
        stem = Path(abs_path).stem
        tmpdir = tempfile.mkdtemp(prefix="kairo_mineru_")

        try:
            cmd = [
                _MINERU_CMD,
                "-p",
                abs_path,
                "-o",
                tmpdir,
                "-m",
                "auto",
            ]
            log.debug("MineruParser: running %s", " ".join(cmd))

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=_MINERU_TIMEOUT_SECONDS,
            )

            if proc.returncode != 0:
                stderr_snippet = (proc.stderr or "")[:500]
                raise RuntimeError(f"MinerU exited with code {proc.returncode}: {stderr_snippet}")

            # Locate content_list JSON
            content_list_path = Path(tmpdir) / stem / "auto" / f"{stem}_content_list.json"

            # MinerU may sanitise the stem (spaces → underscores, etc.)
            if not content_list_path.exists():
                # Search recursively for *_content_list.json as a safety net
                candidates = list(Path(tmpdir).rglob("*_content_list.json"))
                if not candidates:
                    raise FileNotFoundError(
                        f"MinerU output JSON not found in {tmpdir}. "
                        f"Expected: {content_list_path}"
                    )
                content_list_path = candidates[0]
                log.debug("MineruParser: found content_list at %s", content_list_path)

            with open(content_list_path, encoding="utf-8") as fh:
                content_list = json.load(fh)

            if not isinstance(content_list, list):
                raise ValueError(
                    f"MinerU content_list is not a list (got {type(content_list).__name__})"
                )

            return _map_mineru_content_list(content_list, abs_path)

        finally:
            # Always clean up the temp directory
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception as cleanup_err:
                log.debug("MineruParser: tmpdir cleanup failed: %s", cleanup_err)


# ---------------------------------------------------------------------------
# Module-level public API
# ---------------------------------------------------------------------------


def parse_with_mineru(file_path: str, format: str = "pdf") -> Dict[str, Any]:  # noqa: A002
    """
    Parse a document using MinerU (magic-pdf) subprocess.
    Falls back to PyMuPDF for text-based PDFs.

    Returns same schema as docling_parser:
        {"paragraphs": [...], "tables": [...], "metadata": {...}}
    """
    return _parser_instance.parse(file_path, format=format)


# ---------------------------------------------------------------------------
# Singleton parser instance
# ---------------------------------------------------------------------------

_parser_instance = MineruParser()


def parse_pdf_structured(file_path: str) -> Dict[str, Any]:
    """
    Parse a PDF using MinerU with PyMuPDF fallback.
    Same output schema as parse_docx_structured from docling_parser.

    Parameters
    ----------
    file_path : str
        Path to the PDF file to parse.

    Returns
    -------
    dict
        Keys: "paragraphs", "tables", "metadata"
    """
    return parse_with_mineru(file_path, format="pdf")
