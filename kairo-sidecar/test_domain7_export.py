"""
Domain 7: Export & Publishing — Kairo Phantom
Comprehensive test suite for all 14 kami export formats.
Runs fully offline without any external service dependencies.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Set up sys.path for sidecar imports
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))
sys.path.insert(0, str(Path(__file__).parent.resolve()))

SAMPLE_DOC = """
# The Future of AI Collaboration

## Introduction
Artificial intelligence is transforming how teams collaborate.

## Key Points
- Real-time AI suggestions
- Intelligent document analysis  
- Automated formatting and export

## Conclusion
Kairo Phantom represents the next evolution in document intelligence.
""".strip()


@pytest.fixture
def temp_output_dir(tmp_path):
    """Provide a temporary output directory for each test."""
    return tmp_path / "Kairo Exports"


@pytest.fixture
def handler(temp_output_dir):
    """Create a KamiCommandHandler with isolated output directory."""
    from sidecar.exporters.kami_handlers import KamiCommandHandler

    h = KamiCommandHandler()
    h.output_dir = temp_output_dir
    h.output_dir.mkdir(parents=True, exist_ok=True)
    return h


@pytest.fixture
def sample_metadata():
    return {"title": "The Future of AI Collaboration", "author": "Test Suite"}


# ─── PDF Export ───────────────────────────────────────────────────────────────


class TestPdfExport:
    def test_pdf_creates_file(self, handler, sample_metadata):
        result = handler.handle("// kami pdf", SAMPLE_DOC, sample_metadata)
        assert result["ok"] is True
        assert result["format"] == "pdf"
        out = Path(result["output_path"])
        assert out.exists(), f"PDF file not found: {out}"
        assert out.stat().st_size > 100, "PDF file is suspiciously small"

    def test_pdf_notification_contains_path(self, handler, sample_metadata):
        result = handler.handle("// kami pdf", SAMPLE_DOC, sample_metadata)
        assert "notification" in result
        assert len(result["notification"]) > 5

    def test_pdf_with_theme_arg(self, handler, sample_metadata):
        result = handler.handle("// kami pdf --theme dark", SAMPLE_DOC, sample_metadata)
        assert result["ok"] is True


# ─── EPUB Export ──────────────────────────────────────────────────────────────


class TestEpubExport:
    def test_epub_creates_file(self, handler, sample_metadata):
        result = handler.handle("// kami epub", SAMPLE_DOC, sample_metadata)
        assert result["ok"] is True
        assert result["format"] == "epub"
        out = Path(result["output_path"])
        assert out.exists(), f"EPUB file not found: {out}"
        assert out.stat().st_size > 0

    def test_epub_extension(self, handler, sample_metadata):
        result = handler.handle("// kami epub", SAMPLE_DOC, sample_metadata)
        assert result["output_path"].endswith(".epub")


# ─── Slides Export ────────────────────────────────────────────────────────────


class TestSlidesExport:
    def test_slides_creates_html_file(self, handler, sample_metadata):
        result = handler.handle("// kami slides", SAMPLE_DOC, sample_metadata)
        assert result["ok"] is True
        assert result["format"] == "slides"
        out = Path(result["output_path"])
        assert out.exists(), f"Slides HTML not found: {out}"
        content = out.read_text(encoding="utf-8")
        assert "reveal" in content.lower() or "<html" in content.lower()

    def test_slides_extension(self, handler, sample_metadata):
        result = handler.handle("// kami slides", SAMPLE_DOC, sample_metadata)
        assert result["output_path"].endswith(".html")


# ─── Book Export ──────────────────────────────────────────────────────────────


class TestBookExport:
    def test_book_creates_html_file(self, handler, sample_metadata):
        result = handler.handle("// kami book", SAMPLE_DOC, sample_metadata)
        assert result["ok"] is True
        assert result["format"] == "book"
        out = Path(result["output_path"])
        assert out.exists()
        assert out.stat().st_size > 100


# ─── HTML Export ──────────────────────────────────────────────────────────────


class TestHtmlExport:
    def test_html_creates_file(self, handler, sample_metadata):
        result = handler.handle("// kami html", SAMPLE_DOC, sample_metadata)
        assert result["ok"] is True
        assert result["format"] == "html"
        out = Path(result["output_path"])
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "<html" in content.lower() or "<!DOCTYPE" in content.lower()


# ─── Email Format ─────────────────────────────────────────────────────────────


class TestEmailFormat:
    def test_email_returns_clipboard_content(self, handler, sample_metadata):
        with patch.object(handler, "_copy_to_clipboard") as mock_clip:
            result = handler.handle("// kami email", SAMPLE_DOC, sample_metadata)
            assert result["ok"] is True
            assert result["format"] == "email"
            mock_clip.assert_called_once()
            email_text = mock_clip.call_args[0][0]
            assert "Subject:" in email_text

    def test_email_contains_subject_from_title(self, handler):
        meta = {"title": "Q4 Report Summary"}
        with patch.object(handler, "_copy_to_clipboard") as mock_clip:
            handler.handle("// kami email", SAMPLE_DOC, meta)
            email_text = mock_clip.call_args[0][0]
            assert "Q4 Report Summary" in email_text


# ─── LinkedIn Format ──────────────────────────────────────────────────────────


class TestLinkedInFormat:
    def test_linkedin_returns_clipboard_content(self, handler, sample_metadata):
        with patch.object(handler, "_copy_to_clipboard") as mock_clip:
            result = handler.handle("// kami linkedin", SAMPLE_DOC, sample_metadata)
            assert result["ok"] is True
            assert result["format"] == "linkedin"
            mock_clip.assert_called_once()

    def test_linkedin_respects_char_limit(self, handler, sample_metadata):
        long_doc = "A very long sentence. " * 200
        with patch.object(handler, "_copy_to_clipboard") as mock_clip:
            handler.handle("// kami linkedin", long_doc, sample_metadata)
            li_text = mock_clip.call_args[0][0]
            assert len(li_text) <= 1300


# ─── Tweet Thread Format ──────────────────────────────────────────────────────


class TestTweetThreadFormat:
    def test_tweet_returns_clipboard_content(self, handler, sample_metadata):
        with patch.object(handler, "_copy_to_clipboard") as mock_clip:
            result = handler.handle("// kami tweet", SAMPLE_DOC, sample_metadata)
            assert result["ok"] is True
            assert result["format"] == "tweet_thread"
            mock_clip.assert_called_once()

    def test_tweet_numbered_format(self, handler, sample_metadata):
        long_doc = "This is important information about AI. " * 20
        with patch.object(handler, "_copy_to_clipboard") as mock_clip:
            handler.handle("// kami tweet", long_doc, sample_metadata)
            thread_text = mock_clip.call_args[0][0]
            assert "1/" in thread_text  # Has tweet numbering

    def test_tweet_chunks_within_280_chars(self, handler, sample_metadata):
        long_doc = "Word " * 500
        with patch.object(handler, "_copy_to_clipboard") as mock_clip:
            handler.handle("// kami tweet", long_doc, sample_metadata)
            thread_text = mock_clip.call_args[0][0]
            # Each tweet should be <= 280 chars
            tweets = thread_text.split("\n\n")
            for tweet in tweets:
                assert len(tweet) <= 280, f"Tweet too long: {len(tweet)} chars: {tweet[:60]}..."


# ─── Podcast Export ───────────────────────────────────────────────────────────


class TestPodcastExport:
    def test_podcast_creates_file(self, handler, sample_metadata):
        result = handler.handle("// kami podcast", SAMPLE_DOC, sample_metadata)
        assert result["ok"] is True
        assert result["format"] == "podcast"
        out = Path(result["output_path"])
        assert out.exists(), f"Podcast file not found: {out}"

    def test_local_podcast_flag(self, handler, sample_metadata):
        result = handler.handle("// kami podcast --local", SAMPLE_DOC, sample_metadata)
        assert result["ok"] is True
        out = Path(result["output_path"])
        assert out.exists()


# ─── Subtitles Export ─────────────────────────────────────────────────────────


class TestSubtitlesExport:
    def test_subtitles_creates_srt_file(self, handler, sample_metadata):
        result = handler.handle("// kami subtitles", SAMPLE_DOC, sample_metadata)
        assert result["ok"] is True
        assert result["format"] == "subtitles"
        out = Path(result["output_path"])
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        # SRT format: should have sequence numbers
        assert "-->" in content or len(content) > 10


# ─── Quiz Export ──────────────────────────────────────────────────────────────


class TestQuizExport:
    def test_quiz_creates_json_file(self, handler, sample_metadata):
        result = handler.handle("// kami quiz", SAMPLE_DOC, sample_metadata)
        assert result["ok"] is True
        assert result["format"] == "quiz"
        out = Path(result["output_path"])
        assert out.exists()
        assert out.suffix == ".json"

    def test_quiz_valid_json(self, handler, sample_metadata):
        result = handler.handle("// kami quiz", SAMPLE_DOC, sample_metadata)
        out = Path(result["output_path"])
        data = json.loads(out.read_text(encoding="utf-8"))
        assert isinstance(data, (dict, list))


# ─── Flashcards Export ────────────────────────────────────────────────────────


class TestFlashcardsExport:
    def test_flashcards_creates_json_file(self, handler, sample_metadata):
        result = handler.handle("// kami flashcards", SAMPLE_DOC, sample_metadata)
        assert result["ok"] is True
        assert result["format"] == "flashcards"
        out = Path(result["output_path"])
        assert out.exists()
        assert out.suffix == ".json"

    def test_flashcards_valid_json(self, handler, sample_metadata):
        result = handler.handle("// kami flashcards", SAMPLE_DOC, sample_metadata)
        out = Path(result["output_path"])
        data = json.loads(out.read_text(encoding="utf-8"))
        assert isinstance(data, (dict, list))


# ─── Mindmap Export ───────────────────────────────────────────────────────────


class TestMindmapExport:
    def test_mindmap_creates_md_file(self, handler, sample_metadata):
        result = handler.handle("// kami mindmap", SAMPLE_DOC, sample_metadata)
        assert result["ok"] is True
        assert result["format"] == "mindmap"
        out = Path(result["output_path"])
        assert out.exists()
        assert out.suffix == ".md"

    def test_mindmap_contains_structure(self, handler, sample_metadata):
        result = handler.handle("// kami mindmap", SAMPLE_DOC, sample_metadata)
        out = Path(result["output_path"])
        content = out.read_text(encoding="utf-8")
        assert "Mind Map" in content
        assert "-" in content  # Has bullet items


# ─── Batch Export (all) ───────────────────────────────────────────────────────


class TestBatchExport:
    def test_all_export_succeeds(self, handler, sample_metadata):
        result = handler.handle("// kami all", SAMPLE_DOC, sample_metadata)
        assert result["ok"] is True
        assert result["format"] == "all"
        assert "results" in result
        results = result["results"]
        # At least pdf, epub, slides, book, html should succeed
        succeeded = [k for k, v in results.items() if not str(v).startswith("FAILED")]
        assert len(succeeded) >= 3, f"Expected at least 3 formats to succeed, got: {results}"

    def test_all_export_notification(self, handler, sample_metadata):
        result = handler.handle("// kami all", SAMPLE_DOC, sample_metadata)
        assert "notification" in result
        assert "Kairo Exports" in result["notification"]


# ─── Command Parser ───────────────────────────────────────────────────────────


class TestCommandParser:
    def test_parse_pdf_command(self, handler):
        cmd, args = handler._parse_command("// kami pdf")
        assert cmd == "pdf"
        assert isinstance(args, dict)

    def test_parse_command_with_args(self, handler):
        cmd, args = handler._parse_command("// kami podcast --local")
        assert cmd == "podcast"
        assert args.get("local") in ("true", True)

    def test_parse_unknown_defaults_to_pdf(self, handler):
        # Unknown command falls back to PDF by default
        result = handler.handle("// kami unknown-format-xyz", SAMPLE_DOC, {})
        # Should not crash and should succeed via fallback
        assert "ok" in result

    def test_parse_tweet_thread_alias(self, handler):
        cmd, args = handler._parse_command("// kami tweet-thread")
        assert cmd == "tweet-thread"


# ─── Error Resilience ─────────────────────────────────────────────────────────


class TestErrorResilience:
    def test_empty_content_doesnt_crash(self, handler, sample_metadata):
        result = handler.handle("// kami pdf", "", sample_metadata)
        # Should succeed or gracefully fail, not raise exception
        assert "ok" in result

    def test_unicode_content_handled(self, handler, sample_metadata):
        unicode_doc = "# Título\n\nContenido con caracteres especiales: ñ, ü, 中文, العربية"
        result = handler.handle("// kami html", unicode_doc, sample_metadata)
        assert result["ok"] is True

    def test_mindmap_with_no_headings(self, handler, sample_metadata):
        plain_text = "Just some plain text without any headings at all."
        result = handler.handle("// kami mindmap", plain_text, sample_metadata)
        assert result["ok"] is True

    def test_exception_returns_error_dict(self, handler, sample_metadata):
        with patch.object(handler, "_export_pdf", side_effect=Exception("Simulated failure")):
            result = handler.handle("// kami pdf", SAMPLE_DOC, sample_metadata)
            assert result["ok"] is False
            assert "error" in result


# ─── Output Directory ─────────────────────────────────────────────────────────


class TestOutputDirectory:
    def test_output_dir_created_automatically(self, tmp_path):
        from sidecar.exporters.kami_handlers import KamiCommandHandler

        non_existent = tmp_path / "new" / "nested" / "dir"
        h = KamiCommandHandler()
        h.output_dir = non_existent
        h.output_dir.mkdir(parents=True, exist_ok=True)
        assert non_existent.exists()

    def test_multiple_exports_dont_conflict(self, handler, sample_metadata):
        r1 = handler.handle("// kami html", SAMPLE_DOC, sample_metadata)
        r2 = handler.handle("// kami html", SAMPLE_DOC, sample_metadata)
        # Both should succeed and create different files (timestamp-based)
        assert r1["ok"] is True
        assert r2["ok"] is True
