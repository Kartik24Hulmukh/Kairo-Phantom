import logging
import datetime
from pathlib import Path

log = logging.getLogger("kairo-sidecar.pdf_parser")


def parse_pdf(file_path: str) -> dict:
    """
    Parses a PDF file using the Kairo Three-Tier PDF Router:
    1. Average character density is calculated using PyMuPDF (if available).
    2. Routing decision:
       - Avg density > 100 chars/page: PyMuPDF (Tier 1, text-heavy)
       - Avg density 10 to 100 chars/page: Docling (Tier 2, standard table/layout extraction)
       - Avg density < 10 chars/page: MinerU VLM (Tier 3, scanned/VLM-first extraction)
    3. Graceful fallback occurs if the selected parser is not installed or fails:
       MinerU VLM -> Docling -> PyMuPDF.
    """
    file_path_abs = str(Path(file_path).resolve())
    log.info(f"Routing PDF extraction for: {file_path_abs}")

    # Determine average character density
    avg_density = 0.0
    page_count = 0
    total_chars = 0
    pymupdf_available = False

    try:
        import fitz

        pymupdf_available = True
        doc = fitz.open(file_path_abs)
        page_count = len(doc)
        for page in doc:
            total_chars += len(page.get_text())
        doc.close()
        avg_density = total_chars / page_count if page_count > 0 else 0.0
        log.info(
            f"PDF Character density scan: {page_count} pages, {total_chars} total chars. Avg density: {avg_density:.2f} chars/page"
        )
    except ImportError:
        log.warning("PyMuPDF (fitz) is not installed. Unable to calculate density directly.")
    except Exception as e:
        log.error(f"Error calculating character density via PyMuPDF: {e}")

    # Routing logic
    chosen_tier = None
    if pymupdf_available:
        if avg_density > 100:
            chosen_tier = 1
        elif avg_density >= 10:
            chosen_tier = 2
        else:
            chosen_tier = 3
    else:
        # Without PyMuPDF, default to Tier 2 (Docling) if available, else standard fallback
        chosen_tier = 2

    log.info(f"Targeting Tier {chosen_tier} PDF extraction based on density.")

    result = None
    errors = []

    # Execute and Fallback Chain
    tiers_to_try = []
    if chosen_tier == 1:
        tiers_to_try = [1, 2, 3]
    elif chosen_tier == 2:
        tiers_to_try = [2, 1, 3]
    else:
        tiers_to_try = [3, 2, 1]

    for tier in tiers_to_try:
        try:
            if tier == 1:
                log.info("Attempting Tier 1 PDF parsing (PyMuPDF)")
                result = _parse_pdf_pymupdf(file_path_abs)
                if result:
                    result["metadata"]["tier"] = "pymupdf"
                    break
            elif tier == 2:
                log.info("Attempting Tier 2 PDF parsing (Docling)")
                result = _parse_pdf_docling(file_path_abs)
                if result:
                    result["metadata"]["tier"] = "docling"
                    break
            elif tier == 3:
                log.info("Attempting Tier 3 PDF parsing (MinerU VLM)")
                result = _parse_pdf_mineru(file_path_abs)
                if result:
                    result["metadata"]["tier"] = "mineru_vlm"
                    break
        except Exception as e:
            errors.append(f"Tier {tier} failed: {e}")
            log.warning(f"Tier {tier} PDF parser failed: {e}")

    if not result:
        # Ultimate fallback - return raw string or raise
        raise RuntimeError(f"All 3 PDF parsing tiers failed. Errors: {errors}")

    result["metadata"]["file_path"] = file_path_abs
    result["metadata"]["parse_timestamp"] = datetime.datetime.now().isoformat()
    result["metadata"]["avg_character_density"] = avg_density
    result["metadata"]["page_count"] = page_count or len(result.get("paragraphs", []))

    return result


def _parse_pdf_pymupdf(file_path: str) -> dict:
    try:
        import fitz  # PyMuPDF — AGPL, lazy import inside try/except
    except ImportError:
        raise ImportError("PyMuPDF (fitz) is required for PDF extraction")
    doc = fitz.open(file_path)
    paragraphs = []
    tables = []

    p_idx = 0
    for page_num, page in enumerate(doc):
        text = page.get_text(
            "blocks"
        )  # gets list of (x0, y0, x1, y1, "text", block_no, block_type)
        for block in text:
            block_text = block[4].strip()
            if block_text:
                paragraphs.append(
                    {
                        "index": p_idx,
                        "text": block_text,
                        "style": "Normal",
                        "level": 0,
                        "page": page_num + 1,
                        "runs": [{"text": block_text, "bold": False, "italic": False}],
                    }
                )
                p_idx += 1

        # Simple table extraction if fitz has it
        try:
            tabs = page.find_tables()
            for tab in tabs:
                tables.append(
                    {
                        "after_paragraph_index": p_idx - 1,
                        "rows": tab.extract(),
                        "page": page_num + 1,
                    }
                )
        except Exception:
            pass

    doc.close()
    return {
        "paragraphs": paragraphs,
        "tables": tables,
        "metadata": {"total_paragraphs": len(paragraphs), "table_count": len(tables)},
    }


def _parse_pdf_docling(file_path: str) -> dict:
    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    res = converter.convert(file_path)
    markdown_text = res.document.export_to_markdown()

    paragraphs = []
    tables = []
    p_idx = 0

    lines = markdown_text.split("\n")
    for line in lines:
        line_clean = line.strip()
        if line_clean:
            # Check for simple markdown headings
            style = "Normal"
            level = 0
            if line_clean.startswith("#"):
                level = len(line_clean) - len(line_clean.lstrip("#"))
                style = f"Heading{level}"
                line_clean = line_clean.lstrip("#").strip()

            paragraphs.append(
                {
                    "index": p_idx,
                    "text": line_clean,
                    "style": style,
                    "level": level,
                    "page": 1,
                    "runs": [
                        {"text": line_clean, "bold": style.startswith("Heading"), "italic": False}
                    ],
                }
            )
            p_idx += 1

    return {
        "paragraphs": paragraphs,
        "tables": tables,
        "metadata": {"total_paragraphs": len(paragraphs), "table_count": len(tables)},
    }


def _parse_pdf_mineru(file_path: str) -> dict:
    try:
        from sidecar.parsers.mineru_parser import parse_with_mineru

        return parse_with_mineru(file_path)
    except Exception as e:
        log.warning(f"parse_with_mineru failed, trying magic-pdf import fallback: {e}")
        # Keep old import fallback logic
        from magic_pdf.pipe.UNIPipe import UNIPipe

        with open(file_path, "rb") as f:
            pdf_bytes = f.read()

        pipe = UNIPipe(pdf_bytes, "pdf", {})
        pipe.pipe_classify()
        pipe.pipe_analyze()
        model_json = pipe.pipe_to_json()

        paragraphs = []
        tables = []
        p_idx = 0

        for block in model_json:
            block_type = block.get("type", "")
            if block_type in ("text", "title", "heading"):
                text = block.get("text", "").strip()
                style = "Normal"
                level = 0
                if block_type == "title":
                    style = "Heading1"
                    level = 1
                elif block_type == "heading":
                    level = block.get("level", 1)
                    style = f"Heading{level}"

                paragraphs.append(
                    {
                        "index": p_idx,
                        "text": text,
                        "style": style,
                        "level": level,
                        "page": block.get("page_idx", 0) + 1,
                        "runs": [
                            {"text": text, "bold": style.startswith("Heading"), "italic": False}
                        ],
                    }
                )
                p_idx += 1
            elif block_type == "table":
                rows = block.get("table_cells", [])
                tables.append(
                    {
                        "after_paragraph_index": p_idx - 1,
                        "rows": rows,
                        "page": block.get("page_idx", 0) + 1,
                    }
                )

        return {
            "paragraphs": paragraphs,
            "tables": tables,
            "metadata": {"total_paragraphs": len(paragraphs), "table_count": len(tables)},
        }
