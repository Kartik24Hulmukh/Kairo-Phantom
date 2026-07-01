"""
Passive context preloader for Kairo Eye.
Listens for AppChangedEvent from AppWatcher and pre-parses document context
so it's ready when the user presses Alt+M.
"""

import threading
import time
import logging
from typing import Optional, Dict, Any

log = logging.getLogger("kairo-eye.passive-preloader")


class PassivePreloader:
    """Pre-loads document context in background when app switches."""

    CACHE_TTL_SECONDS = 60

    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._cache_times: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._preload_thread: Optional[threading.Thread] = None

    def on_app_changed(self, app_name: str, file_path: str, domain: str) -> None:
        """Called by AppWatcher/FarscryService when active app changes."""
        if domain not in ("word", "excel", "code") or not file_path:
            return
        t = threading.Thread(
            target=self._preload_context,
            args=(app_name, file_path, domain),
            daemon=True,
            name=f"kairo-preload-{domain}",
        )
        t.start()
        self._preload_thread = t

    def _preload_context(self, app_name: str, file_path: str, domain: str) -> None:
        """Background thread: parse document context and cache it."""
        try:
            start = time.perf_counter()
            context = self._extract_context(domain, file_path)
            elapsed_ms = (time.perf_counter() - start) * 1000
            with self._lock:
                self._cache[file_path] = context
                self._cache_times[file_path] = time.time()
            log.info(f"[PassivePreloader] {domain}:{file_path} preloaded in {elapsed_ms:.1f}ms")
        except Exception as e:
            log.warning(f"[PassivePreloader] Preload failed for {file_path}: {e}")

    def _extract_context(self, domain: str, file_path: str) -> dict:
        """Extract context for the given domain."""
        if domain == "word":
            try:
                from sidecar.masters.word.context_extractor import WordContextExtractor

                extractor = WordContextExtractor()
                ctx = extractor.extract(file_path)
                return {
                    "domain": "word",
                    "context": ctx.__dict__ if hasattr(ctx, "__dict__") else str(ctx),
                }
            except Exception as e:
                return {"domain": "word", "context": {}, "error": str(e)}
        elif domain == "excel":
            try:
                from sidecar.masters.excel_master import ExcelContextExtractor

                extractor = ExcelContextExtractor()
                ctx = extractor.extract(file_path, active_cell="A1")
                return {"domain": "excel", "context": ctx.to_dict()}
            except Exception as e:
                return {"domain": "excel", "context": {}, "error": str(e)}
        return {"domain": domain, "context": {}}

    def get_cached_context(self, file_path: str) -> Optional[dict]:
        """Return cached context if still fresh, else None."""
        with self._lock:
            cached_time = self._cache_times.get(file_path)
            if cached_time and (time.time() - cached_time) < self.CACHE_TTL_SECONDS:
                return self._cache.get(file_path)
        return None

    def invalidate(self, file_path: str) -> None:
        """Invalidate cache for a file (e.g. after write)."""
        with self._lock:
            self._cache.pop(file_path, None)
            self._cache_times.pop(file_path, None)


_preloader: Optional[PassivePreloader] = None


def get_preloader() -> PassivePreloader:
    global _preloader
    if _preloader is None:
        _preloader = PassivePreloader()
    return _preloader
