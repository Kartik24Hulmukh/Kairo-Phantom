"""
ODT Parser — OpenDocument Text support for Kairo Sidecar.

Uses the real `odfpy` library to open .odt files, extract text, styles,
and paragraphs, and produce a Kairo internal representation compatible
with WordContext.

Can also save back to ODT with basic formatting.
"""

import logging
import os
from typing import List, Dict, Any

log = logging.getLogger("kairo-sidecar.odt_parser")

# Real odfpy imports — no mock
try:
    from odf.opendocument import load as odf_load
    from odf.opendocument import OpenDocumentText
    from odf import text as odf_text
    from odf import style as odf_style

    _ODFPY_AVAILABLE = True
except ImportError:
    _ODFPY_AVAILABLE = False
    odf_load = None  # type: ignore
    OpenDocumentText = None  # type: ignore
    odf_text = None  # type: ignore
    odf_style = None  # type: ignore


def _error(msg: str) -> dict:
    return {"ok": False, "error": msg}


def parse_odt(file_path: str) -> dict:
    """
    Parse an ODT file and return Kairo internal representation.

    Returns:
        {
            "ok": True,
            "data": {
                "paragraphs": List[Dict[str, Any]],
                "styles": List[str],
                "tables": List[Dict[str, Any]],
                "metadata": Dict[str, Any],
            }
        }
    """
    if not _ODFPY_AVAILABLE:
        return _error("odfpy library not installed")

    if not os.path.exists(file_path):
        return _error(f"ODT file not found: {file_path}")

    try:
        doc = odf_load(file_path)
    except Exception as exc:
        return _error(f"Failed to open ODT file: {exc}")

    if doc is None:
        return _error("ODT file could not be loaded (returned None)")

    return _parse_odt_document(doc)


def _parse_odt_document(doc) -> dict:
    """Parse an odfpy document into Kairo internal representation."""
    paragraphs = []
    tables = []
    styles_seen = set()

    # Extract style names from the document
    style_names = set()
    try:
        for s in doc.styles.getElementsByType(odf_style.Style):
            name_attr = s.getAttribute("name")
            if name_attr:
                style_names.add(name_attr)
    except Exception as exc:
        log.debug(f"Failed to extract ODT styles: {exc}")

    # Walk through the document body
    body = None
    try:
        body = doc.text
    except Exception:
        pass

    if body is None:
        return _error("ODT document has no text body")

    para_idx = 0
    table_idx = 0

    # Iterate through all elements in the body
    for child in body.childNodes:
        tag = getattr(child, "qname", (None, None))[1] if hasattr(child, "qname") else str(child)

        if tag == "p":
            # Paragraph
            para_data = _extract_paragraph(child, para_idx, style_names)
            paragraphs.append(para_data)
            styles_seen.add(para_data["style"])
            para_idx += 1

        elif tag == "h":
            # Heading
            para_data = _extract_heading(child, para_idx, style_names)
            paragraphs.append(para_data)
            styles_seen.add(para_data["style"])
            para_idx += 1

        elif tag == "table":
            # Table
            table_data = _extract_table(child, table_idx)
            tables.append(table_data)
            table_idx += 1

        elif tag == "list":
            # List — extract list items as paragraphs
            list_items = _extract_list(child, para_idx, style_names)
            for item in list_items:
                paragraphs.append(item)
                styles_seen.add(item["style"])
                para_idx += 1

    return {
        "ok": True,
        "data": {
            "paragraphs": paragraphs,
            "styles": sorted(styles_seen | style_names),
            "tables": tables,
            "metadata": {
                "format": "odt",
                "total_paragraphs": len(paragraphs),
                "total_tables": len(tables),
            },
        },
    }


def _get_text_from_node(node) -> str:
    """Recursively extract all text from an ODF node."""
    text_parts = []

    if hasattr(node, "data") and isinstance(node.data, str):
        text_parts.append(node.data)

    if hasattr(node, "childNodes"):
        for child in node.childNodes:
            text_parts.append(_get_text_from_node(child))

    return "".join(text_parts)


def _extract_paragraph(node, idx: int, style_names: set) -> Dict[str, Any]:
    """Extract a paragraph element into Kairo representation."""
    text = _get_text_from_node(node).strip()

    style_name = node.getAttribute("stylename") or "Standard"

    # Map ODT style names to Word-compatible names
    mapped_style = _map_odt_style(style_name)

    # Check for bold/italic in the paragraph's spans
    has_bold = False
    has_italic = False
    runs = []

    try:
        for child in node.childNodes:
            child_tag = (
                getattr(child, "qname", (None, None))[1] if hasattr(child, "qname") else None
            )
            if child_tag == "span":
                span_text = _get_text_from_node(child)
                span_style = child.getAttribute("stylename") or ""
                span_bold = "bold" in span_style.lower() or "strong" in span_style.lower()
                span_italic = "italic" in span_style.lower() or "emphasis" in span_style.lower()
                if span_bold:
                    has_bold = True
                if span_italic:
                    has_italic = True
                if span_text:
                    runs.append(
                        {
                            "text": span_text,
                            "bold": span_bold,
                            "italic": span_italic,
                        }
                    )
    except Exception as exc:
        log.debug(f"Failed to extract spans from ODT paragraph: {exc}")

    if not runs and text:
        runs = [{"text": text, "bold": has_bold, "italic": has_italic}]

    return {
        "index": idx,
        "style": mapped_style,
        "text": text[:500],
        "level": None,
        "is_empty": len(text.strip()) == 0,
        "bold": has_bold,
        "italic": has_italic,
        "runs": runs,
    }


def _extract_heading(node, idx: int, style_names: set) -> Dict[str, Any]:
    """Extract a heading element into Kairo representation."""
    text = _get_text_from_node(node).strip()

    # ODT headings have outline-level attribute
    level_str = node.getAttribute("outlinelevel") or "1"
    try:
        level = int(level_str)
    except (ValueError, TypeError):
        level = 1

    style_name = f"Heading {level}"

    return {
        "index": idx,
        "style": style_name,
        "text": text[:500],
        "level": level,
        "is_empty": len(text.strip()) == 0,
        "bold": True,  # Headings are typically bold
        "italic": False,
        "runs": [{"text": text, "bold": True, "italic": False}] if text else [],
    }


def _extract_list(node, base_idx: int, style_names: set) -> List[Dict[str, Any]]:
    """Extract list items as individual paragraphs."""
    items = []
    item_idx = base_idx

    for child in node.childNodes:
        tag = getattr(child, "qname", (None, None))[1] if hasattr(child, "qname") else None
        if tag == "list-item":
            for sub in child.childNodes:
                sub_tag = getattr(sub, "qname", (None, None))[1] if hasattr(sub, "qname") else None
                if sub_tag in ("p", "h"):
                    text = _get_text_from_node(sub).strip()
                    # Determine if it's a numbered or bulleted list
                    list_style = node.getAttribute("stylename") or ""
                    if "number" in list_style.lower() or "decimal" in list_style.lower():
                        style = "List Number"
                    else:
                        style = "List Bullet"

                    items.append(
                        {
                            "index": item_idx,
                            "style": style,
                            "text": text[:500],
                            "level": 0,
                            "is_empty": len(text.strip()) == 0,
                            "bold": False,
                            "italic": False,
                            "runs": [{"text": text, "bold": False, "italic": False}]
                            if text
                            else [],
                        }
                    )
                    item_idx += 1

    return items


def _extract_table(node, idx: int) -> Dict[str, Any]:
    """Extract a table element into Kairo representation."""
    rows = 0
    cols = 0
    header_text = []

    try:
        for child in node.childNodes:
            tag = getattr(child, "qname", (None, None))[1] if hasattr(child, "qname") else None
            if tag == "table-row":
                rows += 1
                row_cells = 0
                cell_texts = []
                for cell in child.childNodes:
                    cell_tag = (
                        getattr(cell, "qname", (None, None))[1] if hasattr(cell, "qname") else None
                    )
                    if cell_tag == "table-cell":
                        row_cells += 1
                        cell_text = _get_text_from_node(cell).strip()
                        cell_texts.append(cell_text[:50])
                cols = max(cols, row_cells)
                if rows == 1:
                    header_text = cell_texts
    except Exception as exc:
        log.debug(f"Failed to extract ODT table: {exc}")

    return {
        "index": idx,
        "rows": rows,
        "cols": cols,
        "after_paragraph": -1,
        "header_text": header_text,
    }


def _map_odt_style(odt_style_name: str) -> str:
    """Map ODT style names to Word-compatible style names."""
    name_lower = odt_style_name.lower()

    if "heading" in name_lower:
        # Try to extract heading level
        import re

        match = re.search(r"heading\s*(\d+)", name_lower)
        if match:
            return f"Heading {match.group(1)}"
        return "Heading 1"

    if "title" in name_lower:
        return "Title"

    if "standard" in name_lower or "normal" in name_lower or "default" in name_lower:
        return "Normal"

    if "textbody" in name_lower:
        return "Normal"

    # Return as-is if no mapping found
    return odt_style_name


def save_odt(file_path: str, paragraphs: List[Dict[str, Any]]) -> dict:
    """
    Save paragraphs back to an ODT file with basic formatting.

    Args:
        file_path: Output file path
        paragraphs: List of paragraph dicts with 'text', 'style', 'bold', 'italic'

    Returns:
        {"ok": True, "data": {"path": file_path, "paragraph_count": N}}
    """
    if not _ODFPY_AVAILABLE:
        return _error("odfpy library not installed")

    try:
        doc = OpenDocumentText()

        # Create basic styles
        s = odf_style.Style(name="Standard", family="paragraph")
        doc.styles.addElement(s)

        for level in range(1, 4):
            hs = odf_style.Style(name=f"Heading_{level}", family="paragraph")
            hs.addElement(
                odf_style.TextProperties(fontweight="bold", fontsize=f"{16 - (level - 1) * 2}pt")
            )
            doc.styles.addElement(hs)

        # Add paragraphs
        for para in paragraphs:
            text = para.get("text", "")
            style = para.get("style", "Normal")
            para.get("runs", [])

            if style.startswith("Heading"):
                try:
                    level = int(style.split()[-1])
                except (ValueError, IndexError):
                    level = 1
                h = odf_text.H(outlinelevel=str(level), text=text)
                h.setAttribute("stylename", f"Heading_{min(level, 3)}")
                doc.text.addElement(h)
            else:
                p = odf_text.P(text=text)
                p.setAttribute("stylename", "Standard")
                doc.text.addElement(p)

        doc.save(file_path)

    except Exception as exc:
        return _error(f"Failed to write ODT file: {exc}")

    return {
        "ok": True,
        "data": {
            "path": file_path,
            "paragraph_count": len(paragraphs),
        },
    }


def odt_to_kairo_context(file_path: str, cursor_paragraph_index: int = 0) -> dict:
    """
    Convert an ODT file to a Kairo WordContext-compatible dict.
    """
    result = parse_odt(file_path)
    if not result["ok"]:
        return result

    data = result["data"]
    paragraphs = data["paragraphs"]

    para_styles = list(set(p["style"] for p in paragraphs if p["style"]))

    total = len(paragraphs)
    if cursor_paragraph_index < 0 or cursor_paragraph_index >= total:
        cursor_paragraph_index = max(0, total - 1) if total > 0 else 0

    return {
        "ok": True,
        "data": {
            "styles": {
                "paragraph": para_styles,
                "character": [],
                "table": [],
            },
            "paragraphs": paragraphs,
            "tables": data["tables"],
            "theme_fonts": {"major": "Liberation Sans", "minor": "Liberation Sans"},
            "list_sequences": [
                {"index": p["index"], "style": p["style"], "text": p["text"][:100]}
                for p in paragraphs
                if "List" in p["style"]
            ],
            "document_purpose": "general",
            "cursor_paragraph_index": cursor_paragraph_index,
            "total_paragraphs": total,
            "metadata": data["metadata"],
        },
    }
