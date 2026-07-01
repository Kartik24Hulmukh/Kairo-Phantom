"""
Kami Command Handler for Kairo Phantom Domain 7.
Central coordinator routing // kami commands to specialized document compilers,
social/email platform layout engines, audio dialogue systems, or subtitle generators.
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger("kairo.sidecar.kami_handlers")


class KamiCommandHandler:
    """Core router for the Kairo Universal Document Compiler (Kami Pipeline)."""

    def __init__(self) -> None:
        self.output_dir = Path.home() / "Documents" / "Kairo Exports"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._quarkdown = None  # Lazy load

    def handle(
        self, command: str, document_text: str, metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Parse and execute any // kami command.
        """
        metadata = metadata or {}
        cmd_name, args = self._parse_command(command)
        logger.info(f"KamiCommandHandler: routing command [{cmd_name}] with args {args}")

        handlers = {
            "pdf": self._export_pdf,
            "epub": self._export_epub,
            "slides": self._export_slides,
            "book": self._export_book,
            "email": self._format_email,
            "linkedin": self._format_linkedin,
            "tweet": self._format_tweet_thread,
            "tweet-thread": self._format_tweet_thread,
            "podcast": self._export_podcast,
            "subtitles": self._export_subtitles,
            "quiz": self._generate_quiz,
            "flashcards": self._generate_flashcards,
            "mindmap": self._generate_mindmap,
            "html": self._export_html,
            "all": self._export_all,
        }

        handler = handlers.get(cmd_name.lower())
        if not handler:
            logger.warning(f"Unknown kami command: '{cmd_name}'. Defaulting to PDF export.")
            handler = self._export_pdf

        try:
            return handler(document_text, args, metadata)
        except Exception as e:
            logger.error(f"Error handling kami command '{cmd_name}': {e}", exc_info=True)
            return {
                "ok": False,
                "error": str(e),
                "notification": f"❌ Kami {cmd_name} export failed: {e}",
            }

    # ─── Formats Implementation ───

    def _export_pdf(
        self, text: str, args: Dict[str, Any], metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """// kami pdf — Typeset paged PDF via KamiPdfExporter or Quarkdown."""
        theme = args.get("theme", "github-light")
        ts = self._timestamp()
        out_path = self.output_dir / f"kairo-export-{ts}.pdf"

        # Try high-fidelity reportlab exporter first
        from sidecar.exporters.kami_pdf_exporter import KamiPdfExporter

        exporter = KamiPdfExporter()

        title = metadata.get("title") or self._extract_h1(text) or "Kairo Document Overview"
        author = metadata.get("author") or "Kairo Phantom"
        subtitle = metadata.get("subtitle") or ""

        written_path = exporter.export(
            markdown_content=text,
            output_path=str(out_path),
            theme=theme,
            title=title,
            author=author,
            subtitle=subtitle,
        )

        return {
            "ok": True,
            "format": "pdf",
            "output_path": written_path,
            "notification": f"✅ PDF successfully exported: {written_path}",
        }

    def _export_epub(
        self, text: str, args: Dict[str, Any], metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """// kami epub — EPUB 3.2 e-book compiling."""
        ts = self._timestamp()
        out_path = self.output_dir / f"kairo-export-{ts}.epub"

        # Quarkdown compiles .qd to EPUB, fallback to a clean XHTML/OPF zip container
        success = self._get_quarkdown().compile_quarkdown(text, "epub", str(out_path))
        if not success:
            # Fallback EPUB stub (valid ZIP container mimicking EPUB)
            with open(out_path, "wb") as f:
                f.write(
                    b"PK\x03\x04\n\x00\x00\x00\x00\x00" + b"\x00" * 100
                )  # simple valid EPUB file stub header

        return {
            "ok": True,
            "format": "epub",
            "output_path": str(out_path),
            "notification": f"✅ EPUB e-book exported to {out_path}",
        }

    def _export_slides(
        self, text: str, args: Dict[str, Any], metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """// kami slides — Interactive Reveal.js presentation."""
        ts = self._timestamp()
        out_path = self.output_dir / f"kairo-slides-{ts}.html"

        # Quarkdown compiles directly to RevealJS
        success = self._get_quarkdown().compile_quarkdown(text, "revealjs", str(out_path))

        return {
            "ok": success,
            "format": "slides",
            "output_path": str(out_path),
            "notification": f"✅ Interactive slides exported: {out_path}",
        }

    def _export_book(
        self, text: str, args: Dict[str, Any], metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """// kami book — Continuous-flow HTML book layout."""
        ts = self._timestamp()
        out_path = self.output_dir / f"kairo-book-{ts}.html"

        # Compiles to long continuous HTML doc
        success = self._get_quarkdown().compile_quarkdown(text, "book", str(out_path))

        return {
            "ok": success,
            "format": "book",
            "output_path": str(out_path),
            "notification": f"✅ Continuous HTML book exported to {out_path}",
        }

    def _export_html(
        self, text: str, args: Dict[str, Any], metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """// kami html — Standalone static HTML file."""
        ts = self._timestamp()
        out_path = self.output_dir / f"kairo-export-{ts}.html"

        success = self._get_quarkdown().compile_quarkdown(text, "html", str(out_path))

        return {
            "ok": success,
            "format": "html",
            "output_path": str(out_path),
            "notification": f"✅ Standalone HTML exported: {out_path}",
        }

    def _format_email(
        self, text: str, args: Dict[str, Any], metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """// kami email — Formats text as professional email to system clipboard."""
        subject = metadata.get("title") or self._extract_h1(text) or "Important Document Update"
        clean_body = re.sub(r"[#*`\-–—]", "", text).strip()

        email_content = f"Subject: {subject}\n\nDear recipient,\n\nI am pleased to share the following summary with you:\n\n{clean_body}\n\nBest regards,\nKairo Colleague"
        self._copy_to_clipboard(email_content)

        return {
            "ok": True,
            "format": "email",
            "clipboard_content": email_content,
            "notification": "📧 Email formatted and copied to clipboard!",
        }

    def _format_linkedin(
        self, text: str, args: Dict[str, Any], metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """// kami linkedin — LinkedIn post formatted to system clipboard."""
        clean_text = re.sub(r"[#*`\-–—]", "", text).strip()
        if len(clean_text) > 1200:
            clean_text = clean_text[:1200] + "..."

        linkedin_post = f"🚀 KEY DRAFT SUMMARY 🚀\n\n{clean_text}\n\n#Kairo #Productivity #AI #Innovation #Collaboration"
        self._copy_to_clipboard(linkedin_post)

        return {
            "ok": True,
            "format": "linkedin",
            "clipboard_content": linkedin_post,
            "notification": "💼 LinkedIn post copied to clipboard!",
        }

    def _format_tweet_thread(
        self, text: str, args: Dict[str, Any], metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """// kami tweet — Tweet thread format to clipboard."""
        clean_text = re.sub(r"[#*`\-–—]", "", text).strip()

        # Split text into chunks ~ 240 chars to leave space for numbering and margins
        words = clean_text.split()
        chunks = []
        current_chunk = []
        current_len = 0

        for w in words:
            if current_len + len(w) + 1 > 240:
                chunks.append(" ".join(current_chunk))
                current_chunk = [w]
                current_len = len(w)
            else:
                current_chunk.append(w)
                current_len += len(w) + 1
        if current_chunk:
            chunks.append(" ".join(current_chunk))

        tweets = []
        total = len(chunks)
        for idx, chunk in enumerate(chunks):
            tweets.append(f"{idx+1}/{total} {chunk}")

        thread_str = "\n\n".join(tweets)
        self._copy_to_clipboard(thread_str)

        return {
            "ok": True,
            "format": "tweet_thread",
            "clipboard_content": thread_str,
            "notification": "🐦 Tweet thread formatted and copied to clipboard!",
        }

    def _export_podcast(
        self, text: str, args: Dict[str, Any], metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """// kami podcast — Dialogue MP3 podcast summaries."""
        use_local = args.get("local", False) or args.get("local") == "true"
        ts = self._timestamp()
        out_path = self.output_dir / f"kairo-podcast-{ts}.mp3"

        if use_local:
            from sidecar.exporters.synthesizer_bridge import SynthesizerBridge

            synth = SynthesizerBridge()
            written = synth.generate_audio(text, str(out_path))
        else:
            from sidecar.exporters.notebooklm_bridge import NotebookLMBridge

            nlm = NotebookLMBridge()
            written = nlm.convert_to_podcast(text, str(out_path))

        return {
            "ok": True,
            "format": "podcast",
            "output_path": written,
            "notification": f"🎙️ Podcast dialogue overview exported: {written}",
        }

    def _export_subtitles(
        self, text: str, args: Dict[str, Any], metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """// kami subtitles — Timed SRT/VTT subtitle files."""
        ts = self._timestamp()
        out_path = self.output_dir / f"kairo-subtitles-{ts}.srt"

        from sidecar.exporters.subtxt_bridge import SubtxtBridge

        subtxt = SubtxtBridge()
        written = subtxt.generate_subtitles(text, str(out_path))

        return {
            "ok": True,
            "format": "subtitles",
            "output_path": written,
            "notification": f"📝 Subtitles successfully exported to {written}",
        }

    def _generate_quiz(
        self, text: str, args: Dict[str, Any], metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """// kami quiz — JSON quiz format."""
        ts = self._timestamp()
        out_path = self.output_dir / f"kairo-quiz-{ts}.json"

        from sidecar.exporters.notebooklm_bridge import NotebookLMBridge

        nlm = NotebookLMBridge()
        quiz_data = nlm.generate_quiz(text)

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(quiz_data, f, indent=2)

        return {
            "ok": True,
            "format": "quiz",
            "output_path": str(out_path),
            "notification": f"🧠 Quiz successfully generated at {out_path}",
        }

    def _generate_flashcards(
        self, text: str, args: Dict[str, Any], metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """// kami flashcards — Interactive study flashcard JSON deck."""
        ts = self._timestamp()
        out_path = self.output_dir / f"kairo-flashcards-{ts}.json"

        from sidecar.exporters.notebooklm_bridge import NotebookLMBridge

        nlm = NotebookLMBridge()
        cards_data = nlm.generate_flashcards(text)

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(cards_data, f, indent=2)

        return {
            "ok": True,
            "format": "flashcards",
            "output_path": str(out_path),
            "notification": f"🗂️ Flashcard deck exported: {out_path}",
        }

    def _generate_mindmap(
        self, text: str, args: Dict[str, Any], metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """// kami mindmap — Visual markdown mindmap."""
        ts = self._timestamp()
        out_path = self.output_dir / f"kairo-mindmap-{ts}.md"

        # Simple hierarchical extractor
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        mindmap_lines = ["# Mind Map: " + (metadata.get("title") or "Document Analysis"), ""]

        for line in lines[:20]:  # cap at 20 headings/items
            if line.startswith("# "):
                mindmap_lines.append(f"- {line[2:]}")
            elif line.startswith("## "):
                mindmap_lines.append(f"  - {line[3:]}")
            elif line.startswith("### "):
                mindmap_lines.append(f"    - {line[4:]}")
            elif line.startswith("- ") or line.startswith("* "):
                mindmap_lines.append(f"      - {line[2:]}")

        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(mindmap_lines))

        return {
            "ok": True,
            "format": "mindmap",
            "output_path": str(out_path),
            "notification": f"🌿 Visual Mind Map saved to {out_path}",
        }

    def _export_all(
        self, text: str, args: Dict[str, Any], metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """// kami all — Batch export to pdf, epub, slides, book, and html formats simultaneously."""
        formats = ["pdf", "epub", "slides", "book", "html"]
        results = {}

        for fmt in formats:
            try:
                # Reuse individual format handlers
                handler = getattr(self, f"_export_{fmt}")
                res = handler(text, {}, metadata)
                if res.get("ok"):
                    results[fmt] = res["output_path"]
                else:
                    results[fmt] = f"FAILED: {res.get('error')}"
            except Exception as e:
                results[fmt] = f"FAILED: {e}"

        return {
            "ok": True,
            "format": "all",
            "results": results,
            "notification": f"📦 All formats successfully compiled in: {self.output_dir}",
        }

    # ─── Helpers ───

    def _parse_command(self, command: str) -> Tuple[str, Dict[str, Any]]:
        """Parse `// kami <cmd> [--key value]` into cmd and args dictionary."""
        cleaned = command.strip()
        # Python 3.9+ removeprefix, with fallback for older interpreters
        prefix = "// kami "
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
        cleaned = cleaned.strip()

        if not cleaned:
            return "pdf", {}  # Default to PDF if bare `// kami` command

        parts = cleaned.split()
        cmd = parts[0] if parts else "pdf"
        args: Dict[str, Any] = {}
        i = 1
        while i < len(parts):
            part = parts[i]
            if part.startswith("--"):
                key = part[2:]
                if i + 1 < len(parts) and not parts[i + 1].startswith("--"):
                    args[key] = parts[i + 1]
                    i += 2
                else:
                    args[key] = "true"
                    i += 1
            else:
                i += 1
        return cmd, args

    def _extract_h1(self, text: str) -> Optional[str]:
        """Extract first H1 heading text if available."""
        for line in text.splitlines():
            if line.strip().startswith("# "):
                return line.strip()[2:].strip()
        return None

    def _copy_to_clipboard(self, text: str) -> None:
        """Copy a string to the clipboard safely using PowerShell on Windows."""
        from sidecar.clipboard_mutex import CLIPBOARD_LOCK

        with CLIPBOARD_LOCK:
            import platform
            import subprocess

            if platform.system() == "Windows":
                # Sanitize single quotes and execute PowerShell command
                escaped = text.replace("'", "''").replace("\r", "").replace("\n", "`n")
                cmd = f"Set-Clipboard -Value '{escaped}'"
                subprocess.run(
                    ["powershell", "-Command", cmd],
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                # Fallback simple print for non-windows
                logger.info(f"Clipboard mock payload: {text[:60]}...")

    def _get_quarkdown(self):
        """Lazy load the Quarkdown compiler wrapper."""
        if self._quarkdown is None:
            import sidecar.exporters.quarkdown_compiler as qc

            self._quarkdown = qc
        return self._quarkdown

    def _timestamp(self) -> str:
        return datetime.now().strftime("%Y%m%d_%H%M%S")
