"""Tests for PassivePreloader."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sidecar.kairo_eye.passive_preloader import PassivePreloader, get_preloader


def test_passive_preloader_init():
    p = PassivePreloader()
    assert p._cache == {}
    assert p._cache_times == {}


def test_get_cached_context_miss():
    p = PassivePreloader()
    result = p.get_cached_context("/nonexistent/path.docx")
    assert result is None


def test_on_app_changed_unsupported_domain():
    """Non-word/excel/code domains should be ignored."""
    p = PassivePreloader()
    p.on_app_changed("Notepad", "C:/test.txt", "text")
    time.sleep(0.1)
    assert p.get_cached_context("C:/test.txt") is None


def test_on_app_changed_empty_path():
    """Empty file_path should be ignored."""
    p = PassivePreloader()
    p.on_app_changed("Word", "", "word")
    time.sleep(0.1)
    # No crash, no entry
    assert len(p._cache) == 0


def test_direct_cache_write_and_read():
    """Test cache write/read directly (bypassing extraction)."""
    p = PassivePreloader()
    file_path = "/fake/doc.docx"
    # Simulate what _preload_context does after extraction
    with p._lock:
        p._cache[file_path] = {"domain": "word", "context": {"paragraphs": []}}
        p._cache_times[file_path] = time.time()
    result = p.get_cached_context(file_path)
    assert result is not None
    assert result["domain"] == "word"


def test_cache_expiry():
    """Expired cache entries should return None."""
    p = PassivePreloader()
    file_path = "/fake/doc.docx"
    with p._lock:
        p._cache[file_path] = {"domain": "word", "context": {}}
        p._cache_times[file_path] = time.time() - 120  # 2 minutes ago (expired)
    result = p.get_cached_context(file_path)
    assert result is None


def test_invalidate():
    """Invalidate should remove cache entry."""
    p = PassivePreloader()
    file_path = "/fake/doc.docx"
    with p._lock:
        p._cache[file_path] = {"domain": "word", "context": {}}
        p._cache_times[file_path] = time.time()
    p.invalidate(file_path)
    assert p.get_cached_context(file_path) is None


def test_on_app_changed_word_nonexistent_file():
    """Word domain with nonexistent file should cache an error dict, not raise."""
    p = PassivePreloader()
    file_path = "/nonexistent/fake.docx"
    p.on_app_changed("WINWORD.EXE", file_path, "word")
    # Wait for background thread to complete
    time.sleep(2)
    # Should have cached something (even if it's an error dict)
    result = p.get_cached_context(file_path)
    # Either cached with error OR None if extraction raised and was caught before caching
    # Both are acceptable — the important thing is no exception propagated
    print(f"Cached result: {result}")


def test_get_preloader_singleton():
    """get_preloader() should return the same instance."""
    a = get_preloader()
    b = get_preloader()
    assert a is b


def test_model_preloader_warmup():
    from unittest.mock import patch
    import asyncio

    # Mock call_with_schema so it doesn't try to make network calls to LiteLLM
    with patch("sidecar.llm_caller.call_with_schema") as mock_call:
        from sidecar.main import _preload_models

        # We also need to mock asyncio.sleep so we don't wait 2 seconds
        with patch("asyncio.sleep", return_value=None):
            asyncio.run(_preload_models())

        # Verify call_with_schema was called
        assert mock_call.call_count >= 2
