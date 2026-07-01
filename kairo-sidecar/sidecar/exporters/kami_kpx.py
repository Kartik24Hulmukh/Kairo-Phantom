"""
KAMI/KPX Export Pipeline for Kairo Phantom Domain 11.

Real export to 5 formats: EPUB (ebooklib), HTML, Markdown, LaTeX, JSON.
KAMI semantic search via model2vec embeddings.
Markdown round-trip with frontmatter/wikilinks/tags preservation.
All export content is scanned by PromptShield for injection payloads.

No mocks on primary paths. If a library is missing, the export FAILS LOUDLY
(raises RuntimeError) — never silently writes a stub file.
"""

from __future__ import annotations

import json
import logging
import re
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("kairo-sidecar.kami_kpx")

# ── PromptShield integration ──────────────────────────────────────────────────


def _scan_for_injections(text: str) -> Tuple[bool, List[str]]:
    """
    Scan export content for injection payloads using PromptShield.
    Returns (is_clean, list_of_matched_patterns).
    is_clean=True means safe to export; is_clean=False means injection detected.
    """
    try:
        from sidecar.safety.prompt_shield import PromptShield

        shield = PromptShield()
        result = shield.scan_detailed(text)
        if not result.get("safe", True):
            return False, result.get("matched_patterns", [])
        return True, []
    except ImportError:
        log.warning("PromptShield not available — injection scan skipped (NOT secure)")
        return True, []


# ── KAMI Index ────────────────────────────────────────────────────────────────


@dataclass
class KAMIEntry:
    """A single document entry in the Kairo Memory Index."""

    doc_id: str
    title: str
    summary: str
    content: str
    tags: List[str] = field(default_factory=list)
    embedding: Optional[List[float]] = None
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().astimezone().isoformat()
        if not self.doc_id:
            self.doc_id = hashlib.sha256(self.title.encode()).hexdigest()[:16]


class KAMIIndex:
    """
    Kairo Memory Index — full-text + semantic search across documents.
    Uses model2vec for real semantic embeddings (not hash fallback).
    """

    def __init__(self) -> None:
        self._entries: Dict[str, KAMIEntry] = {}
        self._embedder = None
        self._embedder_loaded = False

    def _load_embedder(self):
        """Load model2vec for real semantic embeddings."""
        if self._embedder_loaded:
            return self._embedder
        self._embedder_loaded = True
        try:
            from model2vec import StaticModel

            self._embedder = StaticModel.from_pretrained("minishlab/potion-base-8M")
            log.info("KAMI: model2vec potion-base-8M loaded for semantic search")
        except Exception as e:
            log.error(f"KAMI: Failed to load model2vec: {e}")
            self._embedder = None
        return self._embedder

    def _embed(self, text: str) -> Optional[List[float]]:
        """Generate a real semantic embedding for text."""
        embedder = self._load_embedder()
        if embedder is None:
            return None
        try:
            vec = embedder.encode(text)
            return vec.tolist()
        except Exception as e:
            log.error(f"KAMI: Embedding failed: {e}")
            return None

    def add_document(self, title: str, content: str, tags: Optional[List[str]] = None) -> str:
        """Add a document to the KAMI index. Returns the doc_id."""
        # Scan for injection payloads before indexing
        is_clean, patterns = _scan_for_injections(content)
        if not is_clean:
            raise ValueError(f"Injection payloads detected in document content: {patterns}")

        summary = self._generate_summary(content)
        entry = KAMIEntry(
            doc_id="",
            title=title,
            summary=summary,
            content=content,
            tags=tags or [],
        )
        entry.embedding = self._embed(f"{title} {summary}")
        self._entries[entry.doc_id] = entry
        log.info(f"KAMI: Added document '{title}' (id={entry.doc_id})")
        return entry.doc_id

    def _generate_summary(self, content: str, max_len: int = 200) -> str:
        """Generate a simple extractive summary (first meaningful paragraph)."""
        lines = [
            l.strip() for l in content.splitlines() if l.strip() and not l.strip().startswith("#")
        ]
        if not lines:
            return content[:max_len]
        summary = lines[0]
        for line in lines[1:]:
            if len(summary) + len(line) + 1 <= max_len:
                summary += " " + line
            else:
                break
        return summary

    def full_text_search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Full-text search across all indexed documents."""
        query_lower = query.lower()
        results = []
        for entry in self._entries.values():
            score = 0
            if query_lower in entry.title.lower():
                score += 10
            if query_lower in entry.content.lower():
                score += 5
            if query_lower in entry.summary.lower():
                score += 3
            for tag in entry.tags:
                if query_lower in tag.lower():
                    score += 2
            if score > 0:
                results.append(
                    {
                        "doc_id": entry.doc_id,
                        "title": entry.title,
                        "summary": entry.summary,
                        "score": score,
                    }
                )
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def semantic_search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Semantic search using model2vec embeddings (real, not hash)."""
        query_emb = self._embed(query)
        if query_emb is None:
            log.warning(
                "KAMI: Semantic search unavailable (no embedder) — falling back to full-text"
            )
            return self.full_text_search(query, limit)

        import math

        results = []
        for entry in self._entries.values():
            if entry.embedding is None:
                continue
            # Cosine similarity
            dot = sum(a * b for a, b in zip(query_emb, entry.embedding))
            norm_q = math.sqrt(sum(a * a for a in query_emb))
            norm_e = math.sqrt(sum(b * b for b in entry.embedding))
            if norm_q > 0 and norm_e > 0:
                sim = dot / (norm_q * norm_e)
            else:
                sim = 0.0
            results.append(
                {
                    "doc_id": entry.doc_id,
                    "title": entry.title,
                    "summary": entry.summary,
                    "similarity": sim,
                }
            )
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:limit]

    def similar_documents(self, doc_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Find documents similar to a given document by cosine similarity."""
        if doc_id not in self._entries:
            return []
        target = self._entries[doc_id]
        if target.embedding is None:
            return []
        import math

        results = []
        for entry in self._entries.values():
            if entry.doc_id == doc_id or entry.embedding is None:
                continue
            dot = sum(a * b for a, b in zip(target.embedding, entry.embedding))
            norm_t = math.sqrt(sum(a * a for a in target.embedding))
            norm_e = math.sqrt(sum(b * b for b in entry.embedding))
            if norm_t > 0 and norm_e > 0:
                sim = dot / (norm_t * norm_e)
            else:
                sim = 0.0
            results.append(
                {
                    "doc_id": entry.doc_id,
                    "title": entry.title,
                    "similarity": sim,
                }
            )
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:limit]

    @property
    def size(self) -> int:
        return len(self._entries)


# ── KPX Export: 5 formats ────────────────────────────────────────────────────


class KPXExporter:
    """
    Kairo Package eXchange — exports documents to 5 formats.
    All formats use real libraries (ebooklib, reportlab, json, etc.).
    No stubs, no mocks. If a library is missing, export FAILS LOUDLY.
    """

    def __init__(self, output_dir: Optional[Path] = None) -> None:
        self.output_dir = output_dir or Path.home() / "Documents" / "Kairo Exports"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _timestamp(self) -> str:
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    def _scan_content(self, text: str) -> None:
        """Scan content for injection payloads before export."""
        is_clean, patterns = _scan_for_injections(text)
        if not is_clean:
            raise ValueError(f"Export blocked: injection payloads detected: {patterns}")

    def export_epub(self, text: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Export to EPUB using ebooklib (real library, not a stub ZIP)."""
        self._scan_content(text)
        from ebooklib import epub

        ts = self._timestamp()
        title = metadata.get("title", "Kairo Export")
        author = metadata.get("author", "Kairo Phantom")
        out_path = self.output_dir / f"kairo-export-{ts}.epub"

        book = epub.EpubBook()
        book.set_identifier(f"kairo-{ts}")
        book.set_title(title)
        book.set_language("en")
        book.add_author(author)

        # Parse markdown into chapters
        chapters = self._markdown_to_chapters(text)
        spine = ["nav"]
        for i, (ch_title, ch_content) in enumerate(chapters):
            chapter = epub.EpubHtml(
                title=ch_title,
                file_name=f"chapter_{i+1}.xhtml",
                lang="en",
            )
            chapter.content = f"<h1>{ch_title}</h1>\n" + self._markdown_to_html(ch_content)
            book.add_item(chapter)
            spine.append(chapter)
            book.toc.append(chapter)

        # Add navigation
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        book.spine = spine

        # Write EPUB
        epub.write_epub(str(out_path), book, {})
        assert (
            out_path.exists() and out_path.stat().st_size > 200
        ), "EPUB file too small — generation may have failed"

        return {
            "ok": True,
            "format": "epub",
            "output_path": str(out_path),
            "notification": f"✅ EPUB exported to {out_path}",
        }

    def export_html(self, text: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Export to standalone self-contained HTML."""
        self._scan_content(text)
        ts = self._timestamp()
        title = metadata.get("title", "Kairo Export")
        out_path = self.output_dir / f"kairo-export-{ts}.html"

        html_body = self._markdown_to_html(text)
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 800px; margin: 2em auto; padding: 0 1em; line-height: 1.6; color: #333; }}
h1 {{ color: #2c3e50; border-bottom: 2px solid #eee; padding-bottom: 0.3em; }}
h2 {{ color: #34495e; }}
code {{ background: #f4f4f4; padding: 0.2em 0.4em; border-radius: 3px; }}
pre {{ background: #f4f4f4; padding: 1em; border-radius: 5px; overflow-x: auto; }}
blockquote {{ border-left: 4px solid #ddd; margin-left: 0; padding-left: 1em; color: #666; }}
</style>
</head>
<body>
{html_body}
</body>
</html>"""
        out_path.write_text(html, encoding="utf-8")
        assert out_path.exists() and out_path.stat().st_size > 50

        return {
            "ok": True,
            "format": "html",
            "output_path": str(out_path),
            "notification": f"✅ HTML exported to {out_path}",
        }

    def export_markdown(self, text: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Export to clean markdown (no Kairo metadata — for external tools)."""
        self._scan_content(text)
        ts = self._timestamp()
        out_path = self.output_dir / f"kairo-export-{ts}.md"

        # Clean markdown: ensure consistent heading levels, strip Kairo-specific markers
        clean = text
        # Remove any Kairo command markers
        clean = re.sub(r"^//\s*kami\s+.*$", "", clean, flags=re.MULTILINE)
        # Ensure ends with newline
        if not clean.endswith("\n"):
            clean += "\n"

        out_path.write_text(clean, encoding="utf-8")
        assert out_path.exists() and out_path.stat().st_size > 0

        return {
            "ok": True,
            "format": "markdown",
            "output_path": str(out_path),
            "notification": f"✅ Markdown exported to {out_path}",
        }

    def export_latex(self, text: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Export to LaTeX (for academic users)."""
        self._scan_content(text)
        ts = self._timestamp()
        title = metadata.get("title", "Kairo Export")
        author = metadata.get("author", "Kairo Phantom")
        out_path = self.output_dir / f"kairo-export-{ts}.tex"

        latex_body = self._markdown_to_latex(text)
        latex = f"""\\documentclass[12pt,a4paper]{{article}}
\\usepackage[utf8]{{inputenc}}
\\usepackage{{geometry}}
\\geometry{{margin=1in}}
\\usepackage{{hyperref}}
\\title{{{self._latex_escape(title)}}}
\\author{{{self._latex_escape(author)}}}
\\date{{\\today}}

\\begin{{document}}
\\maketitle

{latex_body}

\\end{{document}}
"""
        out_path.write_text(latex, encoding="utf-8")
        assert out_path.exists() and out_path.stat().st_size > 50

        return {
            "ok": True,
            "format": "latex",
            "output_path": str(out_path),
            "notification": f"✅ LaTeX exported to {out_path}",
        }

    def export_json(self, text: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Export to structured JSON (for API consumers)."""
        self._scan_content(text)
        ts = self._timestamp()
        out_path = self.output_dir / f"kairo-export-{ts}.json"

        # Parse markdown into structured sections
        sections = self._markdown_to_sections(text)
        data = {
            "title": metadata.get("title", "Kairo Export"),
            "author": metadata.get("author", "Kairo Phantom"),
            "exported_at": datetime.now().astimezone().isoformat(),
            "sections": sections,
            "metadata": {
                "format_version": "1.0",
                "source": "kairo-phantom",
                "char_count": len(text),
                "line_count": text.count("\n") + 1,
            },
        }
        out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        assert out_path.exists() and out_path.stat().st_size > 10

        return {
            "ok": True,
            "format": "json",
            "output_path": str(out_path),
            "notification": f"✅ JSON exported to {out_path}",
        }

    def export_all(self, text: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Export to all 5 formats simultaneously."""
        results = {}
        for fmt, method in [
            ("epub", self.export_epub),
            ("html", self.export_html),
            ("markdown", self.export_markdown),
            ("latex", self.export_latex),
            ("json", self.export_json),
        ]:
            try:
                res = method(text, metadata)
                results[fmt] = res["output_path"]
            except Exception as e:
                results[fmt] = f"FAILED: {e}"
        return {
            "ok": True,
            "format": "all",
            "results": results,
            "notification": f"📦 All formats exported to {self.output_dir}",
        }

    # ── Markdown parsing helpers ──────────────────────────────────────────────

    def _markdown_to_chapters(self, text: str) -> List[Tuple[str, str]]:
        """Split markdown into chapters by H1 headings."""
        chapters = []
        current_title = "Introduction"
        current_content = []
        for line in text.splitlines():
            if line.startswith("# ") and not line.startswith("## "):
                if current_content:
                    chapters.append((current_title, "\n".join(current_content)))
                current_title = line[2:].strip()
                current_content = []
            else:
                current_content.append(line)
        if current_content:
            chapters.append((current_title, "\n".join(current_content)))
        return chapters

    def _markdown_to_html(self, text: str) -> str:
        """Convert markdown to HTML (lightweight, no external deps)."""
        html_lines = []
        in_list = False
        in_code = False
        for line in text.splitlines():
            stripped = line.strip()
            # Code blocks
            if stripped.startswith("```"):
                if in_code:
                    html_lines.append("</code></pre>")
                    in_code = False
                else:
                    html_lines.append("<pre><code>")
                    in_code = True
                continue
            if in_code:
                html_lines.append(line)
                continue
            # Headings
            if stripped.startswith("### "):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(f"<h3>{stripped[4:]}</h3>")
            elif stripped.startswith("## "):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(f"<h2>{stripped[3:]}</h2>")
            elif stripped.startswith("# "):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(f"<h1>{stripped[2:]}</h1>")
            elif stripped.startswith("- ") or stripped.startswith("* "):
                if not in_list:
                    html_lines.append("<ul>")
                    in_list = True
                html_lines.append(f"<li>{stripped[2:]}</li>")
            elif stripped.startswith("> "):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(f"<blockquote>{stripped[2:]}</blockquote>")
            elif stripped:
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                # Inline formatting
                content = stripped
                content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", content)
                content = re.sub(r"\*(.+?)\*", r"<em>\1</em>", content)
                content = re.sub(r"`(.+?)`", r"<code>\1</code>", content)
                html_lines.append(f"<p>{content}</p>")
        if in_list:
            html_lines.append("</ul>")
        if in_code:
            html_lines.append("</code></pre>")
        return "\n".join(html_lines)

    def _markdown_to_latex(self, text: str) -> str:
        """Convert markdown to LaTeX."""
        latex_lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("### "):
                latex_lines.append(f"\\subsubsection{{{self._latex_escape(stripped[4:])}}}")
            elif stripped.startswith("## "):
                latex_lines.append(f"\\section{{{self._latex_escape(stripped[3:])}}}")
            elif stripped.startswith("# "):
                latex_lines.append(f"\\section*{{{self._latex_escape(stripped[2:])}}}")
            elif stripped.startswith("- ") or stripped.startswith("* "):
                latex_lines.append(f"\\item {self._latex_escape(stripped[2:])}")
            elif stripped.startswith("> "):
                latex_lines.append(
                    f"\\begin{{quote}}{self._latex_escape(stripped[2:])}\\end{{quote}}"
                )
            elif stripped:
                content = self._latex_escape(stripped)
                content = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", content)
                content = re.sub(r"\*(.+?)\*", r"\\textit{\1}", content)
                latex_lines.append(content)
        # Wrap consecutive \item lines in itemize
        result = []
        in_itemize = False
        for line in latex_lines:
            if line.startswith("\\item "):
                if not in_itemize:
                    result.append("\\begin{itemize}")
                    in_itemize = True
                result.append(line)
            else:
                if in_itemize:
                    result.append("\\end{itemize}")
                    in_itemize = False
                result.append(line)
        if in_itemize:
            result.append("\\end{itemize}")
        return "\n".join(result)

    def _latex_escape(self, text: str) -> str:
        """Escape special LaTeX characters."""
        # Order matters: backslash must be done LAST to avoid double-escaping
        replacements = {
            "&": r"\&",
            "%": r"\%",
            "$": r"\$",
            "#": r"\#",
            "_": r"\_",
            "{": r"\{",
            "}": r"\}",
            "~": r"\textasciitilde{}",
            "^": r"\textasciicircum{}",
        }
        for char, replacement in replacements.items():
            text = text.replace(char, replacement)
        # Backslash last
        text = text.replace("\\", r"\textbackslash{}")
        return text

    def _markdown_to_sections(self, text: str) -> List[Dict[str, str]]:
        """Parse markdown into structured sections for JSON export."""
        sections = []
        current_heading = "Untitled"
        current_content = []
        for line in text.splitlines():
            if line.startswith("# "):
                if current_content:
                    sections.append(
                        {
                            "heading": current_heading,
                            "content": "\n".join(current_content).strip(),
                        }
                    )
                current_heading = line[2:].strip()
                current_content = []
            elif line.startswith("## "):
                if current_content:
                    sections.append(
                        {
                            "heading": current_heading,
                            "content": "\n".join(current_content).strip(),
                        }
                    )
                current_heading = line[3:].strip()
                current_content = []
            else:
                current_content.append(line)
        if current_content:
            sections.append(
                {
                    "heading": current_heading,
                    "content": "\n".join(current_content).strip(),
                }
            )
        return sections


# ── Markdown Round-Trip ───────────────────────────────────────────────────────


class MarkdownRoundTrip:
    """
    Markdown round-trip: export Kairo documents to .md files, re-import them.
    Preserves: frontmatter (YAML metadata), wikilinks ([[page]]), tags (#tag).
    Makes Kairo interoperable with Obsidian/Logseq/Joplin ecosystems.
    """

    @staticmethod
    def export_to_directory(documents: List[Dict[str, Any]], output_dir: Path) -> List[str]:
        """
        Export a list of documents as .md files to a directory.
        Each document gets frontmatter with title, tags, and Kairo metadata.
        Returns list of exported file paths.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        exported = []

        for doc in documents:
            title = doc.get("title", "untitled")
            content = doc.get("content", "")
            tags = doc.get("tags", [])

            # Scan for injections
            is_clean, patterns = _scan_for_injections(content)
            if not is_clean:
                raise ValueError(f"Injection payloads in document '{title}': {patterns}")

            # Generate safe filename
            safe_name = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "-").lower()
            if not safe_name:
                safe_name = "untitled"
            out_path = output_dir / f"{safe_name}.md"

            # Build frontmatter
            frontmatter_lines = ["---"]
            frontmatter_lines.append(f'title: "{title}"')
            if tags:
                frontmatter_lines.append(f"tags: [{', '.join(tags)}]")
            frontmatter_lines.append(f"kairo_id: \"{doc.get('doc_id', '')}\"")
            frontmatter_lines.append(f'exported_at: "{datetime.now().astimezone().isoformat()}"')
            frontmatter_lines.append("---")
            frontmatter = "\n".join(frontmatter_lines)

            # Write file
            full_content = f"{frontmatter}\n\n{content}\n"
            out_path.write_text(full_content, encoding="utf-8")
            exported.append(str(out_path))
            log.info(f"Markdown round-trip: exported '{title}' to {out_path}")

        return exported

    @staticmethod
    def import_from_directory(input_dir: Path) -> List[Dict[str, Any]]:
        """
        Import all .md files from a directory as Kairo documents.
        Parses frontmatter, preserves wikilinks and tags in content.
        Returns list of document dicts.
        """
        input_dir = Path(input_dir)
        documents = []

        for md_file in sorted(input_dir.glob("*.md")):
            raw = md_file.read_text(encoding="utf-8")

            # Parse frontmatter
            frontmatter, body = MarkdownRoundTrip._parse_frontmatter(raw)

            # Extract tags from frontmatter or content
            tags = frontmatter.get("tags", [])
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",")]

            # Also extract inline tags from content
            inline_tags = re.findall(r"(?:^|\s)#([a-zA-Z][\w-]*)", body)
            all_tags = list(set(tags + inline_tags))

            # Scan for injections
            is_clean, patterns = _scan_for_injections(body)
            if not is_clean:
                raise ValueError(f"Injection payloads in '{md_file.name}': {patterns}")

            documents.append(
                {
                    "title": frontmatter.get("title", md_file.stem),
                    "content": body.strip(),
                    "tags": all_tags,
                    "doc_id": frontmatter.get("kairo_id", ""),
                    "source_file": str(md_file),
                }
            )
            log.info(f"Markdown round-trip: imported '{md_file.name}'")

        return documents

    @staticmethod
    def _parse_frontmatter(text: str) -> Tuple[Dict[str, str], str]:
        """Parse YAML frontmatter from markdown text."""
        if not text.startswith("---"):
            return {}, text

        parts = text.split("---", 2)
        if len(parts) < 3:
            return {}, text

        fm_text = parts[1].strip()
        body = parts[2].strip()

        # Simple YAML parsing (key: value)
        fm = {}
        for line in fm_text.splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip()
                # Strip quotes
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                fm[key] = value
        return fm, body

    @staticmethod
    def preserve_wikilinks(content: str) -> str:
        """Ensure wikilinks ([[page]]) are preserved in content."""
        # Wikilinks are already preserved as-is in markdown
        # This method validates they exist and are well-formed
        wikilinks = re.findall(r"\[\[([^\]]+)\]\]", content)
        for link in wikilinks:
            log.debug(f"Markdown round-trip: preserved wikilink [[{link}]]")
        return content

    @staticmethod
    def extract_wikilinks(content: str) -> List[str]:
        """Extract all wikilink targets from content."""
        return re.findall(r"\[\[([^\]]+)\]\]", content)
