"""
Kami PDF Export Pipeline for Kairo Phantom Domain 4.

Converts Markdown content to professionally typeset PDF using reportlab.
Supports 10 themes, cover pages, clickable TOC, CJK text rendering.
All rendering is 100% offline — no subprocess, no CDN calls.

If reportlab is not installed, export() writes the markdown as a .txt file
with a warning header and returns that path instead.
"""

from __future__ import annotations

import datetime
import logging
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("kairo-sidecar.kami_pdf_exporter")

# ---------------------------------------------------------------------------
# Optional reportlab import — ALL reportlab symbols guarded by try/except
# ---------------------------------------------------------------------------

_REPORTLAB_AVAILABLE: bool = False

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
        PageBreak,
        HRFlowable,
        KeepTogether,  # noqa: F401
    )
    from reportlab.platypus.tableofcontents import TableOfContents  # noqa: F401
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY, TA_RIGHT
    from reportlab.pdfbase import pdfmetrics  # noqa: F401
    from reportlab.pdfbase.ttfonts import TTFont  # noqa: F401

    _REPORTLAB_AVAILABLE = True
except ImportError:
    # Provide stubs so type checkers are quiet — never called when flag is False
    A4 = (595.28, 841.89)  # type: ignore[assignment]
    inch = 72.0  # type: ignore[assignment]
    TA_CENTER = 1  # type: ignore[assignment]
    TA_LEFT = 0  # type: ignore[assignment]
    TA_JUSTIFY = 4  # type: ignore[assignment]
    TA_RIGHT = 2  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Theme Definitions
# ---------------------------------------------------------------------------


@dataclass
class KamiTheme:
    """
    Visual theme configuration for Kami PDF exports.

    Attributes:
        name:           Human-readable theme identifier.
        primary_color:  RGB tuple (0–255 each) for headings / accent elements.
        bg_color:       RGB tuple for page background.
        font_family:    Body text font name (reportlab built-in or registered).
        heading_font:   Heading font name.
        body_size:      Body text point size.
        heading_size:   H1 heading point size (H2 = heading_size - 2, H3 = heading_size - 4).
        margin_inches:  Page margin in inches applied to all four sides.
    """

    name: str
    primary_color: Tuple[int, int, int]
    bg_color: Tuple[int, int, int]
    font_family: str
    heading_font: str
    body_size: float
    heading_size: float
    margin_inches: float


def _rgb(r: int, g: int, b: int):
    """Return a reportlab Color from 0-255 RGB components, or a plain tuple when not available."""
    if _REPORTLAB_AVAILABLE:
        return colors.Color(r / 255.0, g / 255.0, b / 255.0)
    return (r / 255.0, g / 255.0, b / 255.0)


# Supported themes — 10 total
THEMES: Dict[str, KamiTheme] = {
    "warm-academic": KamiTheme(
        name="warm-academic",
        primary_color=(101, 56, 22),  # dark brown
        bg_color=(250, 243, 224),  # warm cream #FAF3E0
        font_family="Times-Roman",
        heading_font="Times-BoldItalic",
        body_size=11.0,
        heading_size=20.0,
        margin_inches=1.1,
    ),
    "classic-thesis": KamiTheme(
        name="classic-thesis",
        primary_color=(0, 0, 128),  # navy
        bg_color=(255, 255, 255),
        font_family="Times-Roman",
        heading_font="Times-BoldItalic",
        body_size=11.0,
        heading_size=18.0,
        margin_inches=1.25,
    ),
    "tufte": KamiTheme(
        name="tufte",
        primary_color=(60, 60, 60),  # near-black
        bg_color=(255, 255, 255),
        font_family="Times-Roman",
        heading_font="Times-Bold",
        body_size=10.0,
        heading_size=16.0,
        margin_inches=1.5,  # Tufte's characteristic wide margins
    ),
    "ieee-journal": KamiTheme(
        name="ieee-journal",
        primary_color=(0, 102, 153),  # IEEE blue #006699
        bg_color=(255, 255, 255),
        font_family="Times-Roman",
        heading_font="Times-Bold",
        body_size=10.0,
        heading_size=14.0,
        margin_inches=0.75,
    ),
    "elegant-book": KamiTheme(
        name="elegant-book",
        primary_color=(20, 20, 20),
        bg_color=(253, 252, 248),  # off-white
        font_family="Times-Roman",
        heading_font="Times-Bold",
        body_size=12.0,
        heading_size=22.0,
        margin_inches=1.4,
    ),
    "chinese-red": KamiTheme(
        name="chinese-red",
        primary_color=(204, 0, 0),  # Chinese red #CC0000
        bg_color=(255, 255, 255),
        font_family="Helvetica",
        heading_font="Helvetica-Bold",
        body_size=11.0,
        heading_size=18.0,
        margin_inches=1.0,
    ),
    "ink-wash": KamiTheme(
        name="ink-wash",
        primary_color=(30, 30, 40),  # dark ink
        bg_color=(240, 240, 238),  # light gray
        font_family="Times-Roman",
        heading_font="Times-Bold",
        body_size=11.0,
        heading_size=18.0,
        margin_inches=1.1,
    ),
    "github-light": KamiTheme(
        name="github-light",
        primary_color=(3, 102, 214),  # GitHub blue #0366D6
        bg_color=(255, 255, 255),
        font_family="Helvetica",
        heading_font="Helvetica-Bold",
        body_size=10.5,
        heading_size=18.0,
        margin_inches=1.0,
    ),
    "nord-frost": KamiTheme(
        name="nord-frost",
        primary_color=(94, 129, 172),  # Nord frost #5E81AC
        bg_color=(236, 239, 244),  # Nord snow #ECEFF4
        font_family="Helvetica",
        heading_font="Helvetica-Bold",
        body_size=10.5,
        heading_size=18.0,
        margin_inches=1.0,
    ),
    "ocean-breeze": KamiTheme(
        name="ocean-breeze",
        primary_color=(0, 137, 150),  # teal accent
        bg_color=(225, 245, 248),  # light blue-green
        font_family="Helvetica",
        heading_font="Helvetica-Bold",
        body_size=10.5,
        heading_size=18.0,
        margin_inches=1.0,
    ),
}

# Default fallback theme
_DEFAULT_THEME = "github-light"


# ---------------------------------------------------------------------------
# Kami PDF Exporter
# ---------------------------------------------------------------------------


class KamiPdfExporter:
    """
    Converts Markdown strings to styled PDFs using reportlab.

    Usage::

        exporter = KamiPdfExporter()
        path = exporter.export(
            markdown_content="# Hello\n\nWorld",
            output_path="/tmp/out.pdf",
            theme="nord-frost",
            title="My Document",
            author="Alice",
        )
    """

    def __init__(self) -> None:
        self._reportlab_ok = _REPORTLAB_AVAILABLE
        if not self._reportlab_ok:
            log.warning(
                "reportlab is not installed — KamiPdfExporter will fall back to .txt output. "
                "Install it with: pip install reportlab"
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def export(
        self,
        markdown_content: str,
        output_path: str,
        theme: str = "github-light",
        title: str = "Untitled",
        author: str = "Kairo Phantom",
        subtitle: str = "",
    ) -> str:
        """
        Convert markdown_content to a PDF at output_path.

        Args:
            markdown_content: Raw Markdown string.
            output_path:      Destination file path (must end in .pdf).
            theme:            One of the 10 supported theme names.
            title:            Document title for cover page and metadata.
            author:           Author name for cover page and PDF metadata.
            subtitle:         Optional subtitle shown on cover page.

        Returns:
            Absolute path of the written file (.pdf or .txt fallback).
        """
        output_path = str(Path(output_path).resolve())
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        selected_theme = THEMES.get(theme, THEMES[_DEFAULT_THEME])
        log.info(f"KamiPdfExporter: theme={selected_theme.name}, output={output_path}")

        if not self._reportlab_ok:
            return self._export_txt_fallback(markdown_content, output_path, title, author, subtitle)

        blocks = self._parse_markdown(markdown_content)
        headings = [b for b in blocks if b["type"] in ("h1", "h2", "h3")]

        try:
            self._render_pdf(
                blocks=blocks,
                headings=headings,
                output_path=output_path,
                theme=selected_theme,
                title=title,
                author=author,
                subtitle=subtitle,
            )
            log.info(f"PDF export complete: {output_path}")
            return output_path
        except Exception as exc:
            log.error(f"PDF rendering failed: {exc}", exc_info=True)
            # Fallback to txt on render error
            txt_path = Path(output_path).with_suffix(".txt")
            return self._export_txt_fallback(
                markdown_content,
                str(txt_path),
                title,
                author,
                subtitle,
                extra_warning=f"PDF render failed: {exc}",
            )

    def export_batch(
        self,
        markdown_dir: str,
        output_dir: str,
        formats: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        """
        Export all .md files in markdown_dir to output_dir.

        Args:
            markdown_dir: Directory containing .md files.
            output_dir:   Destination directory for output files.
            formats:      List of format strings (e.g. ['pdf', 'txt']).
                          Defaults to ['pdf'].

        Returns:
            Dict mapping input filename → output path.  Failed exports map
            to an error string prefixed with 'ERROR:'.
        """
        if formats is None:
            formats = ["pdf"]

        markdown_dir_p = Path(markdown_dir).resolve()
        output_dir_p = Path(output_dir).resolve()
        output_dir_p.mkdir(parents=True, exist_ok=True)

        results: Dict[str, str] = {}

        md_files = list(markdown_dir_p.glob("*.md"))
        if not md_files:
            log.warning(f"No .md files found in {markdown_dir_p}")
            return results

        for md_file in md_files:
            try:
                content = md_file.read_text(encoding="utf-8", errors="replace")
                stem = md_file.stem
                title = stem.replace("-", " ").replace("_", " ").title()

                for fmt in formats:
                    fmt_lower = fmt.lower()
                    if fmt_lower == "pdf":
                        out_path = str(output_dir_p / f"{stem}.pdf")
                        result = self.export(
                            markdown_content=content,
                            output_path=out_path,
                            title=title,
                        )
                        results[f"{md_file.name}:{fmt}"] = result
                    elif fmt_lower == "txt":
                        out_path = str(output_dir_p / f"{stem}.txt")
                        result = self._export_txt_fallback(
                            content, out_path, title, "Kairo Phantom", ""
                        )
                        results[f"{md_file.name}:{fmt}"] = result
                    else:
                        # Attempt unipress subprocess for other formats
                        out_path = self._try_unipress_export(
                            str(md_file), str(output_dir_p), fmt_lower
                        )
                        results[f"{md_file.name}:{fmt}"] = out_path

            except Exception as exc:
                log.error(f"Batch export failed for {md_file.name}: {exc}", exc_info=True)
                results[md_file.name] = f"ERROR: {exc}"

        return results

    # ------------------------------------------------------------------
    # Markdown Parser
    # ------------------------------------------------------------------

    def _parse_markdown(self, content: str) -> List[Dict[str, Any]]:
        """
        Parse a Markdown string into a flat list of block dicts.

        Each block has:
            {
                'type': 'h1' | 'h2' | 'h3' | 'p' | 'bullet' | 'code' | 'table',
                'content': str,          # raw text (stripped markdown syntax)
                'raw': str,              # original line(s) before stripping
                'rows': List[List[str]], # populated for 'table' blocks
            }

        Parsing is line-based and handles:
        - ATX headings (# H1, ## H2, ### H3)
        - Unordered bullet lists (-, *, +)
        - Fenced code blocks (``` ... ```)
        - Pipe-delimited tables
        - Everything else → paragraph
        """
        blocks: List[Dict[str, Any]] = []
        lines = content.splitlines()
        i = 0

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # --- Fenced code block ---
            if stripped.startswith("```"):
                code_lines: List[str] = []
                lang = stripped[3:].strip()
                i += 1
                while i < len(lines):
                    cl = lines[i]
                    if cl.strip().startswith("```"):
                        i += 1
                        break
                    code_lines.append(cl)
                    i += 1
                code_text = "\n".join(code_lines)
                blocks.append(
                    {"type": "code", "content": code_text, "raw": code_text, "lang": lang}
                )
                continue

            # --- ATX headings ---
            heading_match = re.match(r"^(#{1,6})\s+(.*)", stripped)
            if heading_match:
                level_str = heading_match.group(1)
                heading_text = heading_match.group(2).strip()
                level = len(level_str)
                htype = f"h{min(level, 3)}"  # map h4-h6 → h3
                blocks.append(
                    {"type": htype, "content": heading_text, "raw": stripped, "level": level}
                )
                i += 1
                continue

            # --- Horizontal rule (---, ***, ___) ---
            if re.match(r"^[-*_]{3,}\s*$", stripped):
                blocks.append({"type": "hr", "content": "", "raw": stripped})
                i += 1
                continue

            # --- Bullet list item (-, *, +) ---
            bullet_match = re.match(r"^[-*+]\s+(.*)", stripped)
            if bullet_match:
                bullet_text = bullet_match.group(1).strip()
                blocks.append({"type": "bullet", "content": bullet_text, "raw": stripped})
                i += 1
                continue

            # --- Numbered list item ---
            numbered_match = re.match(r"^\d+\.\s+(.*)", stripped)
            if numbered_match:
                item_text = numbered_match.group(1).strip()
                blocks.append({"type": "bullet", "content": item_text, "raw": stripped})
                i += 1
                continue

            # --- Table (pipe-delimited) ---
            if "|" in stripped and stripped.startswith("|"):
                table_lines: List[str] = []
                while i < len(lines) and "|" in lines[i] and lines[i].strip().startswith("|"):
                    table_lines.append(lines[i].strip())
                    i += 1
                rows: List[List[str]] = []
                for tl in table_lines:
                    # Remove leading/trailing pipes and split
                    cells = [c.strip() for c in tl.strip("|").split("|")]
                    # Skip separator rows (e.g. |---|---|)
                    if all(re.match(r"^:?-+:?$", c) for c in cells if c):
                        continue
                    rows.append(cells)
                if rows:
                    blocks.append(
                        {
                            "type": "table",
                            "content": "",
                            "raw": "\n".join(table_lines),
                            "rows": rows,
                        }
                    )
                continue

            # --- Blockquote ---
            if stripped.startswith(">"):
                quote_text = re.sub(r"^>\s?", "", stripped)
                blocks.append({"type": "blockquote", "content": quote_text, "raw": stripped})
                i += 1
                continue

            # --- Empty line — skip ---
            if not stripped:
                i += 1
                continue

            # --- Paragraph (default) ---
            # Accumulate consecutive non-special lines into one paragraph
            para_lines: List[str] = [stripped]
            i += 1
            while i < len(lines):
                next_line = lines[i].strip()
                if not next_line:
                    i += 1
                    break
                # Stop if the next line is a special block
                if (
                    next_line.startswith("#")
                    or next_line.startswith("```")
                    or re.match(r"^[-*+]\s+", next_line)
                    or re.match(r"^\d+\.\s+", next_line)
                    or ("|" in next_line and next_line.startswith("|"))
                    or re.match(r"^[-*_]{3,}\s*$", next_line)
                    or next_line.startswith(">")
                ):
                    break
                para_lines.append(next_line)
                i += 1

            para_text = " ".join(para_lines)
            blocks.append({"type": "p", "content": para_text, "raw": para_text})

        return blocks

    # ------------------------------------------------------------------
    # PDF Rendering (reportlab)
    # ------------------------------------------------------------------

    def _render_pdf(
        self,
        blocks: List[Dict[str, Any]],
        headings: List[Dict[str, Any]],
        output_path: str,
        theme: KamiTheme,
        title: str,
        author: str,
        subtitle: str,
    ) -> None:
        """
        Build and write the full PDF document to output_path.
        Sections: cover page → TOC → content.
        """
        margin = theme.margin_inches * inch

        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=margin,
            rightMargin=margin,
            topMargin=margin,
            bottomMargin=margin,
            title=title,
            author=author,
        )

        # Build a custom stylesheet for this theme
        styles = self._build_styles(theme)

        story: List[Any] = []

        # 1. Cover page
        self._build_cover_page(story, theme, styles, title, author, subtitle)
        story.append(PageBreak())

        # 2. Table of contents
        if headings:
            self._build_toc(story, theme, styles, headings)
            story.append(PageBreak())

        # 3. Content
        self._build_content(story, theme, styles, blocks)

        doc.build(story)

    def _build_styles(self, theme: KamiTheme) -> Dict[str, Any]:
        """
        Create a custom style dictionary for the given theme.
        Returns a dict of style name → ParagraphStyle (or TableStyle).
        """
        getSampleStyleSheet()
        pc = theme.primary_color
        primary_rl = colors.Color(pc[0] / 255, pc[1] / 255, pc[2] / 255)
        dark_gray = colors.Color(0.2, 0.2, 0.2)

        def ps(name: str, **kwargs) -> ParagraphStyle:
            """Convenience wrapper to create ParagraphStyle."""
            return ParagraphStyle(name=name, **kwargs)

        styles: Dict[str, Any] = {}

        # Body / Normal
        styles["Normal"] = ps(
            "KamiNormal",
            fontName=theme.font_family,
            fontSize=theme.body_size,
            leading=theme.body_size * 1.45,
            textColor=dark_gray,
            alignment=TA_JUSTIFY,
            spaceAfter=6,
        )

        # Headings
        styles["H1"] = ps(
            "KamiH1",
            fontName=theme.heading_font,
            fontSize=theme.heading_size,
            leading=theme.heading_size * 1.2,
            textColor=primary_rl,
            spaceBefore=16,
            spaceAfter=8,
            alignment=TA_LEFT,
        )
        styles["H2"] = ps(
            "KamiH2",
            fontName=theme.heading_font,
            fontSize=max(theme.heading_size - 3, 12),
            leading=max(theme.heading_size - 3, 12) * 1.2,
            textColor=primary_rl,
            spaceBefore=12,
            spaceAfter=6,
            alignment=TA_LEFT,
        )
        styles["H3"] = ps(
            "KamiH3",
            fontName=theme.heading_font,
            fontSize=max(theme.heading_size - 6, 10),
            leading=max(theme.heading_size - 6, 10) * 1.2,
            textColor=colors.Color(
                min(pc[0] / 255 + 0.15, 1.0),
                min(pc[1] / 255 + 0.15, 1.0),
                min(pc[2] / 255 + 0.15, 1.0),
            ),
            spaceBefore=10,
            spaceAfter=4,
            alignment=TA_LEFT,
        )

        # Bullet
        styles["Bullet"] = ps(
            "KamiBullet",
            fontName=theme.font_family,
            fontSize=theme.body_size,
            leading=theme.body_size * 1.4,
            textColor=dark_gray,
            leftIndent=18,
            bulletIndent=6,
            spaceAfter=3,
        )

        # Code
        styles["Code"] = ps(
            "KamiCode",
            fontName="Courier",
            fontSize=max(theme.body_size - 1.5, 8),
            leading=max(theme.body_size - 1.5, 8) * 1.35,
            textColor=colors.Color(0.15, 0.15, 0.15),
            backColor=colors.Color(0.95, 0.95, 0.93),
            leftIndent=12,
            rightIndent=12,
            spaceBefore=6,
            spaceAfter=6,
            borderPadding=6,
        )

        # Blockquote
        styles["Blockquote"] = ps(
            "KamiBlockquote",
            fontName=theme.font_family,
            fontSize=theme.body_size,
            leading=theme.body_size * 1.4,
            textColor=colors.Color(0.35, 0.35, 0.35),
            leftIndent=24,
            rightIndent=12,
            italics=1,
            spaceAfter=6,
        )

        # Cover title
        styles["CoverTitle"] = ps(
            "KamiCoverTitle",
            fontName=theme.heading_font,
            fontSize=theme.heading_size + 10,
            leading=(theme.heading_size + 10) * 1.2,
            textColor=primary_rl,
            alignment=TA_CENTER,
            spaceBefore=0,
            spaceAfter=12,
        )
        styles["CoverSubtitle"] = ps(
            "KamiCoverSubtitle",
            fontName=theme.font_family,
            fontSize=theme.heading_size - 2,
            leading=(theme.heading_size - 2) * 1.3,
            textColor=dark_gray,
            alignment=TA_CENTER,
            spaceBefore=4,
            spaceAfter=8,
        )
        styles["CoverAuthor"] = ps(
            "KamiCoverAuthor",
            fontName=theme.font_family,
            fontSize=theme.body_size + 1,
            leading=(theme.body_size + 1) * 1.4,
            textColor=dark_gray,
            alignment=TA_CENTER,
            spaceBefore=4,
            spaceAfter=4,
        )
        styles["CoverDate"] = ps(
            "KamiCoverDate",
            fontName=theme.font_family,
            fontSize=theme.body_size - 1,
            leading=(theme.body_size - 1) * 1.4,
            textColor=colors.Color(0.5, 0.5, 0.5),
            alignment=TA_CENTER,
        )

        # TOC entry styles
        styles["TOCEntry1"] = ps(
            "KamiTOC1",
            fontName=theme.font_family,
            fontSize=theme.body_size + 1,
            leading=(theme.body_size + 1) * 1.4,
            textColor=primary_rl,
            leftIndent=0,
            spaceAfter=4,
        )
        styles["TOCEntry2"] = ps(
            "KamiTOC2",
            fontName=theme.font_family,
            fontSize=theme.body_size,
            leading=theme.body_size * 1.4,
            textColor=dark_gray,
            leftIndent=18,
            spaceAfter=3,
        )
        styles["TOCEntry3"] = ps(
            "KamiTOC3",
            fontName=theme.font_family,
            fontSize=theme.body_size - 1,
            leading=(theme.body_size - 1) * 1.4,
            textColor=dark_gray,
            leftIndent=36,
            spaceAfter=2,
        )
        styles["TOCHeading"] = ps(
            "KamiTOCHeading",
            fontName=theme.heading_font,
            fontSize=theme.heading_size - 4,
            leading=(theme.heading_size - 4) * 1.3,
            textColor=primary_rl,
            spaceBefore=0,
            spaceAfter=12,
            alignment=TA_LEFT,
        )

        return styles

    def _build_cover_page(
        self,
        story: List[Any],
        theme: KamiTheme,
        styles: Dict[str, Any],
        title: str,
        author: str,
        subtitle: str,
    ) -> None:
        """
        Append cover page elements to story.

        Layout (top-to-bottom):
            [vertical spacer] → title → subtitle → decorative rule →
            author line → date line → [bottom spacer]
        """
        pc = theme.primary_color
        primary_rl = colors.Color(pc[0] / 255, pc[1] / 255, pc[2] / 255)

        # Push title to about 30% down the page
        story.append(Spacer(1, 2.2 * inch))

        # Title
        safe_title = self._escape_xml(title)
        story.append(Paragraph(safe_title, styles["CoverTitle"]))

        # Subtitle
        if subtitle:
            safe_subtitle = self._escape_xml(subtitle)
            story.append(Spacer(1, 0.15 * inch))
            story.append(Paragraph(safe_subtitle, styles["CoverSubtitle"]))

        # Decorative horizontal rule
        story.append(Spacer(1, 0.25 * inch))
        story.append(
            HRFlowable(
                width="60%",
                thickness=2,
                color=primary_rl,
                hAlign="CENTER",
                spaceAfter=0.2 * inch,
            )
        )
        story.append(Spacer(1, 0.2 * inch))

        # Author
        safe_author = self._escape_xml(author)
        story.append(Paragraph(safe_author, styles["CoverAuthor"]))

        # Date
        date_str = datetime.date.today().strftime("%B %d, %Y")
        story.append(Spacer(1, 0.1 * inch))
        story.append(Paragraph(date_str, styles["CoverDate"]))

        # Footer spacer
        story.append(Spacer(1, 1.5 * inch))

    def _build_toc(
        self,
        story: List[Any],
        theme: KamiTheme,
        styles: Dict[str, Any],
        headings: List[Dict[str, Any]],
    ) -> None:
        """
        Append a Table of Contents section to story.

        Each heading is rendered as a row with a dotted leader between
        the heading text and a placeholder page number.  (reportlab's
        TableOfContents widget requires two-pass build; we use a manual
        static TOC for compatibility with single-pass SimpleDocTemplate.)
        """
        story.append(Paragraph("Table of Contents", styles["TOCHeading"]))
        story.append(
            HRFlowable(
                width="100%",
                thickness=0.5,
                color=colors.Color(0.7, 0.7, 0.7),
                spaceAfter=8,
            )
        )
        story.append(Spacer(1, 0.1 * inch))

        for heading in headings:
            h_type = heading.get("type", "h1")
            h_text = heading.get("content", "")
            safe_h_text = self._escape_xml(h_text)

            # Select indentation and style based on heading level
            if h_type == "h1":
                toc_style = styles["TOCEntry1"]
            elif h_type == "h2":
                toc_style = styles["TOCEntry2"]
            else:
                toc_style = styles["TOCEntry3"]

            # Build a two-column table: [heading text | dots + page]
            # Page placeholder is blank — we can't know page numbers in single-pass
            dot_leader = " " + ("." * 60)
            entry_text = f"{safe_h_text}{dot_leader}"

            story.append(Paragraph(entry_text, toc_style))

        story.append(Spacer(1, 0.2 * inch))

    def _build_content(
        self,
        story: List[Any],
        theme: KamiTheme,
        styles: Dict[str, Any],
        blocks: List[Dict[str, Any]],
    ) -> None:
        """
        Render all parsed content blocks into reportlab flowables.

        Block types handled:
            h1, h2, h3  → Paragraph with heading style
            p           → Paragraph with body style
            bullet      → Paragraph with bullet style + bullet char
            code        → Preformatted Paragraph in monospace
            table       → reportlab Table with styled grid
            blockquote  → Indented italic paragraph
            hr          → HRFlowable
        """
        pc = theme.primary_color
        primary_rl = colors.Color(pc[0] / 255, pc[1] / 255, pc[2] / 255)
        bullet_char = "\u2022"  # •

        for block in blocks:
            btype = block.get("type", "p")
            content = block.get("content", "")
            safe_content = self._escape_xml(content)

            if btype == "h1":
                story.append(Paragraph(safe_content, styles["H1"]))
                story.append(
                    HRFlowable(
                        width="100%",
                        thickness=1,
                        color=primary_rl,
                        spaceAfter=4,
                    )
                )

            elif btype == "h2":
                story.append(Paragraph(safe_content, styles["H2"]))

            elif btype == "h3":
                story.append(Paragraph(safe_content, styles["H3"]))

            elif btype == "p":
                if safe_content.strip():
                    story.append(Paragraph(safe_content, styles["Normal"]))
                    story.append(Spacer(1, 3))

            elif btype == "bullet":
                bullet_para = Paragraph(
                    f"{bullet_char}&nbsp;&nbsp;{safe_content}",
                    styles["Bullet"],
                )
                story.append(bullet_para)

            elif btype == "code":
                # Replace newlines with <br/> for reportlab Paragraph
                code_html = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                code_html = code_html.replace("\n", "<br/>")
                story.append(Spacer(1, 4))
                story.append(Paragraph(f"<font name='Courier'>{code_html}</font>", styles["Code"]))
                story.append(Spacer(1, 4))

            elif btype == "blockquote":
                story.append(Paragraph(f"<i>{safe_content}</i>", styles["Blockquote"]))
                story.append(Spacer(1, 3))

            elif btype == "table":
                rows = block.get("rows", [])
                if rows:
                    self._append_table(story, rows, styles, theme)

            elif btype == "hr":
                story.append(Spacer(1, 6))
                story.append(
                    HRFlowable(
                        width="80%",
                        thickness=0.5,
                        color=colors.Color(0.6, 0.6, 0.6),
                        hAlign="CENTER",
                        spaceAfter=6,
                    )
                )

    def _append_table(
        self,
        story: List[Any],
        rows: List[List[str]],
        styles: Dict[str, Any],
        theme: KamiTheme,
    ) -> None:
        """
        Render a parsed Markdown table as a styled reportlab Table.
        The first row is treated as headers (bold, colored background).
        """
        pc = theme.primary_color
        colors.Color(
            min(pc[0] / 255 + 0.1, 1.0),
            min(pc[1] / 255 + 0.1, 1.0),
            min(pc[2] / 255 + 0.1, 1.0),
        )
        body_style = styles["Normal"]
        header_style = ParagraphStyle(
            "KamiTableHeader",
            fontName=theme.heading_font,
            fontSize=theme.body_size,
            leading=theme.body_size * 1.3,
            textColor=colors.white,
        )

        table_data: List[List[Any]] = []
        for row_idx, row in enumerate(rows):
            cell_style = header_style if row_idx == 0 else body_style
            cell_row = [Paragraph(self._escape_xml(str(cell)), cell_style) for cell in row]
            table_data.append(cell_row)

        if not table_data:
            return

        # Compute column widths — distribute available width
        page_w, _ = A4
        margin = theme.margin_inches * inch
        available_w = page_w - 2 * margin
        ncols = max(len(r) for r in table_data)
        col_width = available_w / ncols if ncols > 0 else available_w

        tbl = Table(table_data, colWidths=[col_width] * ncols, repeatRows=1)

        pc_rl = colors.Color(pc[0] / 255, pc[1] / 255, pc[2] / 255)
        tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), pc_rl),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), theme.heading_font),
                    ("FONTSIZE", (0, 0), (-1, -1), theme.body_size),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.Color(0.96, 0.96, 0.96)],
                    ),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.Color(0.75, 0.75, 0.75)),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("PADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, 0), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ]
            )
        )

        story.append(Spacer(1, 6))
        story.append(tbl)
        story.append(Spacer(1, 10))

    # ------------------------------------------------------------------
    # Unipress subprocess helper (batch only)
    # ------------------------------------------------------------------

    def _try_unipress_export(self, md_path: str, output_dir: str, fmt: str) -> str:
        """
        Attempt to invoke unipress CLI for non-PDF/txt formats.
        Returns output path if successful, or an ERROR: prefixed string.
        """
        import subprocess  # stdlib — no network

        unipress_bin = shutil.which("unipress")
        if not unipress_bin:
            return f"ERROR: unipress not found; cannot export {fmt}"

        stem = Path(md_path).stem
        out_path = str(Path(output_dir) / f"{stem}.{fmt}")

        try:
            proc = subprocess.run(
                [unipress_bin, md_path, "--output", out_path, "--format", fmt],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if proc.returncode == 0:
                return out_path
            else:
                return f"ERROR: unipress exited with code {proc.returncode}: {proc.stderr[:200]}"
        except subprocess.TimeoutExpired:
            return f"ERROR: unipress timed out exporting {fmt}"
        except Exception as exc:
            return f"ERROR: unipress failed: {exc}"

    # ------------------------------------------------------------------
    # Plain-text fallback (no reportlab)
    # ------------------------------------------------------------------

    def _export_txt_fallback(
        self,
        markdown_content: str,
        output_path: str,
        title: str,
        author: str,
        subtitle: str,
        extra_warning: str = "",
    ) -> str:
        """
        Write markdown_content as a UTF-8 plain-text file with a warning
        header explaining why PDF was not produced.
        """
        # Ensure .txt extension
        txt_path = Path(output_path)
        if txt_path.suffix.lower() == ".pdf":
            txt_path = txt_path.with_suffix(".txt")
        txt_path_str = str(txt_path)

        warning_lines = [
            "=" * 72,
            "WARNING: PDF generation was not possible.",
        ]
        if extra_warning:
            warning_lines.append(f"Reason: {extra_warning}")
        else:
            warning_lines.append(
                "Reason: reportlab is not installed. " "Install it with: pip install reportlab"
            )
        warning_lines += [
            f"Title:  {title}",
            f"Author: {author}",
            f"Date:   {datetime.date.today().isoformat()}",
            "=" * 72,
            "",
        ]
        header = "\n".join(warning_lines)

        try:
            with open(txt_path_str, "w", encoding="utf-8") as fh:
                fh.write(header)
                fh.write(markdown_content)
            log.info(f"Wrote plain-text fallback to {txt_path_str}")
        except Exception as exc:
            log.error(f"Even txt fallback failed: {exc}")

        return txt_path_str

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _escape_xml(text: str) -> str:
        """
        Escape characters that would break reportlab's Paragraph XML parser.
        Handles &, <, > and also strips problematic control characters.
        """
        # Replace control characters (except newline/tab) with space
        text = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]", " ", text)
        text = text.replace("&", "&amp;")
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")
        # Collapse excessive whitespace while preserving single newlines
        text = re.sub(r"  +", " ", text)
        return text
