"""
RTF Parser — Rich Text Format support for Kairo Sidecar.

Uses the real `striprtf` library to extract text and basic formatting from
.rtf files, and produces a Kairo internal representation (list of paragraphs
with style info) compatible with WordContext.

Can also save back to RTF with basic formatting (bold, italic, headings).
"""

import logging
import re
from typing import List, Dict, Any

log = logging.getLogger("kairo-sidecar.rtf_parser")

# Real striprtf import — no mock
try:
    from striprtf.striprtf import rtf_to_text

    _STRIPRTF_AVAILABLE = True
except ImportError:
    _STRIPRTF_AVAILABLE = False
    rtf_to_text = None  # type: ignore


def _error(msg: str) -> dict:
    return {"ok": False, "error": msg}


def parse_rtf(file_path: str) -> dict:
    """
    Parse an RTF file and return Kairo internal representation.

    Returns:
        {
            "ok": True,
            "data": {
                "paragraphs": List[Dict[str, Any]],
                "styles": List[str],
                "metadata": Dict[str, Any],
            }
        }
    """
    if not _STRIPRTF_AVAILABLE:
        return _error("striprtf library not installed")

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            rtf_content = f.read()
    except FileNotFoundError:
        return _error(f"RTF file not found: {file_path}")
    except Exception as exc:
        return _error(f"Failed to read RTF file: {exc}")

    if not rtf_content.strip():
        return _error("RTF file is empty")

    # Verify it looks like RTF
    if not rtf_content.strip().startswith("{\\rtf"):
        return _error("File does not appear to be valid RTF (missing \\rtf header)")

    return _parse_rtf_content(rtf_content)


def _parse_rtf_content(rtf_content: str) -> dict:
    """Parse RTF content string into Kairo internal representation."""
    # Extract plain text using real striprtf
    plain_text = rtf_to_text(rtf_content)

    # Extract formatting information from RTF control words
    paragraphs = _extract_paragraphs_with_formatting(rtf_content, plain_text)

    # Collect unique styles
    styles_seen = set()
    for p in paragraphs:
        styles_seen.add(p["style"])

    return {
        "ok": True,
        "data": {
            "paragraphs": paragraphs,
            "styles": sorted(styles_seen),
            "metadata": {
                "format": "rtf",
                "total_paragraphs": len(paragraphs),
                "total_chars": len(plain_text),
            },
        },
    }


def _extract_paragraphs_with_formatting(rtf_content: str, plain_text: str) -> List[Dict[str, Any]]:
    """
    Extract paragraphs with basic formatting info from RTF.

    Detects:
    - Headings (heading1, heading2, heading3 via \\headingN or \\sN styles)
    - Bold (\\b)
    - Italic (\\i)
    - Normal paragraphs
    """
    paragraphs = []

    # Split RTF by paragraph markers (\\par)
    # Each \\par indicates a paragraph break
    rtf_parts = re.split(r"\\par\b", rtf_content)

    for idx, part in enumerate(rtf_parts):
        # Extract text from this paragraph section
        para_text = rtf_to_text(part).strip() if part.strip() else ""
        if not para_text and idx > 0:
            # Empty paragraph — still count it
            para_text = ""

        # Detect heading style from RTF style commands
        style = "Normal"
        level = None

        # Check for heading styles: \heading1, \heading2, etc. or \s1, \s2 (style IDs)
        heading_match = re.search(r"\\heading(\d)\b", part)
        if heading_match:
            level = int(heading_match.group(1))
            style = f"Heading {level}"
        else:
            # Check for \sN style references (common in Word-generated RTF)
            style_match = re.search(r"\\s(\d+)\b", part)
            if style_match:
                style_num = int(style_match.group(1))
                # Map common style numbers to heading levels
                if style_num <= 3:
                    level = style_num
                    style = f"Heading {style_num}"

        # Detect bold and italic in this paragraph
        has_bold = bool(re.search(r"\\b\b", part))
        has_italic = bool(re.search(r"\\i\b", part))

        # Check for list/bullet formatting
        if re.search(r"\\listoverride\b|\\pnlvlbody\b|\\pnlvlblt\b", part):
            if "bullet" in part.lower() or "\\pnlvlblt" in part:
                style = "List Bullet"
            else:
                style = "List Number"

        paragraphs.append(
            {
                "index": idx,
                "style": style,
                "text": para_text[:500],  # Truncate for context
                "level": level,
                "is_empty": len(para_text.strip()) == 0,
                "bold": has_bold,
                "italic": has_italic,
                "runs": [{"text": para_text, "bold": has_bold, "italic": has_italic}]
                if para_text
                else [],
            }
        )

    # Remove trailing empty paragraph (RTF often has a trailing \par)
    while paragraphs and paragraphs[-1]["is_empty"] and paragraphs[-1]["index"] > 0:
        paragraphs.pop()

    # Re-index
    for i, p in enumerate(paragraphs):
        p["index"] = i

    return paragraphs


def save_rtf(file_path: str, paragraphs: List[Dict[str, Any]]) -> dict:
    """
    Save paragraphs back to an RTF file with basic formatting.

    Args:
        file_path: Output file path
        paragraphs: List of paragraph dicts with 'text', 'style', 'bold', 'italic'

    Returns:
        {"ok": True, "data": {"path": file_path, "paragraph_count": N}}
    """
    if not _STRIPRTF_AVAILABLE:
        return _error("striprtf library not installed")

    rtf_lines = []
    rtf_lines.append("{\\rtf1\\ansi\\deff0")
    rtf_lines.append("{\\fonttbl{\\f0 Times New Roman;}}")
    rtf_lines.append("{\\stylesheet")
    rtf_lines.append("{\\s0 Normal;}")
    rtf_lines.append("{\\s1 Heading 1;}")
    rtf_lines.append("{\\s2 Heading 2;}")
    rtf_lines.append("{\\s3 Heading 3;}")
    rtf_lines.append("}")

    for para in paragraphs:
        text = para.get("text", "")
        style = para.get("style", "Normal")
        bold = para.get("bold", False)
        italic = para.get("italic", False)
        runs = para.get("runs", [])

        # Escape special RTF characters
        escaped_text = _escape_rtf_text(text)

        # Build formatting prefix
        fmt = ""
        style_num = 0
        if style.startswith("Heading"):
            try:
                level = int(style.split()[-1])
                style_num = min(level, 3)
                fmt += f"\\s{style_num}"
            except (ValueError, IndexError):
                pass
        elif style == "List Bullet":
            fmt += "\\s0"
        elif style == "List Number":
            fmt += "\\s0"

        if bold:
            fmt += "\\b"
        if italic:
            fmt += "\\i"

        # If runs are provided, use them for per-run formatting
        if runs:
            run_parts = []
            for run in runs:
                run_text = _escape_rtf_text(run.get("text", ""))
                run_fmt = ""
                if run.get("bold", False):
                    run_fmt += "\\b"
                if run.get("italic", False):
                    run_fmt += "\\i"
                if run_fmt:
                    run_parts.append(f"{{{run_fmt} {run_text}}}")
                else:
                    run_parts.append(run_text)
            para_text = "".join(run_parts)
        else:
            if fmt:
                para_text = f"{{{fmt} {escaped_text}}}"
            else:
                para_text = escaped_text

        rtf_lines.append(para_text + "\\par")

    rtf_lines.append("}")

    rtf_content = "\n".join(rtf_lines)

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(rtf_content)
    except Exception as exc:
        return _error(f"Failed to write RTF file: {exc}")

    return {
        "ok": True,
        "data": {
            "path": file_path,
            "paragraph_count": len(paragraphs),
        },
    }


def _escape_rtf_text(text: str) -> str:
    """Escape special characters for RTF format."""
    if not text:
        return ""
    # Escape backslash, braces, and convert unicode to RTF escapes
    text = text.replace("\\", "\\\\")
    text = text.replace("{", "\\{")
    text = text.replace("}", "\\}")
    # Convert non-ASCII to \uN? format
    result = []
    for char in text:
        if ord(char) > 127:
            result.append(f"\\u{ord(char)}?")
        else:
            result.append(char)
    return "".join(result)


def rtf_to_kairo_context(file_path: str, cursor_paragraph_index: int = 0) -> dict:
    """
    Convert an RTF file to a Kairo WordContext-compatible dict.

    Returns a dict with the same shape as WordContext for integration
    with the WordMaster pipeline.
    """
    result = parse_rtf(file_path)
    if not result["ok"]:
        return result

    data = result["data"]
    paragraphs = data["paragraphs"]

    # Build styles dict compatible with WordContext
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
            "tables": [],
            "theme_fonts": {"major": "Times New Roman", "minor": "Times New Roman"},
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
