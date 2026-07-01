import logging
from pathlib import Path
from typing import Optional

from sidecar.parsers.docx_parser import parse_docx
from sidecar.parsers.xlsx_parser import parse_xlsx
from sidecar.parsers.pptx_parser import parse_pptx

from sidecar.parsers.pdf_parser import parse_pdf

log = logging.getLogger("kairo-sidecar.context_extractor")


def extract_context(file_path: str, active_cell: Optional[str] = None) -> dict:
    """
    Route to correct reader based on file extension.
    Returns unified context dict for LLM prompt building.
    """
    ext = Path(file_path).suffix.lower()
    log.info(f"Extracting context from format '{ext}' for path: {file_path}")

    if ext == ".docx":
        return parse_docx(file_path)
    elif ext in (".xlsx", ".xlsm"):
        return parse_xlsx(file_path, active_cell)
    elif ext == ".pptx":
        return parse_pptx(file_path)
    elif ext in (".txt", ".md"):
        try:
            text = Path(file_path).read_text(encoding="utf-8", errors="replace")
            return {"full_text": text, "format": ext.lstrip(".")}
        except Exception as e:
            return {"error": f"Failed to read text file: {e}"}
    elif ext == ".pdf":
        return parse_pdf(file_path)
    else:
        return {"error": f"Unsupported format: {ext}", "ext": ext}
