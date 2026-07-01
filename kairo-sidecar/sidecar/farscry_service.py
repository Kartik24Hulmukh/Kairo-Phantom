"""
sidecar/farscry_service.py — FarScry App Watcher Service
==========================================================
Polls the Windows foreground window and emits AppChangedEvent notifications
via asyncio.Queue for the rest of the sidecar to consume.

Why Python (instead of only Rust)?
-----------------------------------
The Python sidecar needs to know the active app so it can:
  a) Select the correct Domain Master (word / excel / powerpoint / …)
  b) Update the IntentGate domain hint
  c) Debounce rapid app-switching noise

The Rust phantom-core already does this for the injector layer.  This Python
service replicates the same logic so the sidecar can run independently (e.g.
during hot-reload / development) without requiring the Rust binary to be up.

Architecture
------------
  FarScryService            — main polling service (asyncio-aware)
  AppChangedEvent           — event dataclass
  farscry_app_name()        — convenience function: synchronous one-shot query
  farscry_subscribe()       — returns asyncio.Queue[AppChangedEvent]

Polling interval: 250ms (matches Rust app_watcher default).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, List

log = logging.getLogger("kairo-sidecar.farscry")

# ---------------------------------------------------------------------------
# Win32 process-name mapping (mirrors Rust app_watcher.rs)
# ---------------------------------------------------------------------------

_PROCESS_LABELS: Dict[str, str] = {
    "winword": "Microsoft Word",
    "excel": "Microsoft Excel",
    "powerpnt": "Microsoft PowerPoint",
    "outlook": "Microsoft Outlook",
    "code": "Visual Studio Code",
    "notepad++": "Notepad++",
    "notepad": "Notepad",
    "chrome": "Google Chrome",
    "msedge": "Microsoft Edge",
    "firefox": "Mozilla Firefox",
    "acrobat": "Adobe Acrobat",
    "powershell": "PowerShell",
    "windowsterminal": "Windows Terminal",
    "cmd": "Command Prompt",
}


def _label_for_process(process_name: str) -> str:
    """Return a friendly app label for a given process name."""
    lower = process_name.lower().replace(".exe", "")
    for prefix, label in _PROCESS_LABELS.items():
        if lower.startswith(prefix):
            return label
    return "Unknown"


def _domain_for_label(label: str) -> str:
    """Map an app label to a Kairo domain key."""
    _LABEL_TO_DOMAIN: Dict[str, str] = {
        "Microsoft Word": "word",
        "Microsoft Excel": "excel",
        "Microsoft PowerPoint": "powerpoint",
        "Microsoft Outlook": "word",  # email body is Word-like
        "Visual Studio Code": "code",
        "Notepad++": "code",
        "Notepad": "notes",
        "Google Chrome": "browser",
        "Microsoft Edge": "browser",
        "Mozilla Firefox": "browser",
        "Adobe Acrobat": "pdf",
        "PowerShell": "terminal",
        "Windows Terminal": "terminal",
        "Command Prompt": "terminal",
    }
    return _LABEL_TO_DOMAIN.get(label, "general")


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class AppChangedEvent:
    """Emitted each time the active application changes."""

    process_name: str
    app_label: str
    domain: str
    pid: int
    window_title: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class KairoEyeContext:
    app_name: str
    window_title: str
    domain: str
    cursor_region_text: str  # OCR of 200x200px around cursor
    confidence: float
    assembled_ms: float


# ---------------------------------------------------------------------------
# Platform-specific foreground window probe
# ---------------------------------------------------------------------------


class _Win32Probe:
    """
    Single-call foreground window query using ctypes.

    Returns (pid, process_name, window_title) or raises OSError if unavailable.
    """

    def __init__(self):
        try:
            import ctypes
            import ctypes.wintypes

            self._ctypes = ctypes
            self._wintypes = ctypes.wintypes
            self._kernel32 = ctypes.windll.kernel32
            self._user32 = ctypes.windll.user32
            self._psapi = ctypes.windll.psapi
            self._available = True
        except Exception as e:
            log.warning(f"_Win32Probe: ctypes unavailable ({e}); FarScry will run in stub mode")
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def query(self):
        """
        Returns (pid: int, process_name: str, window_title: str) or None.
        """
        if not self._available:
            return None

        try:
            import ctypes
            import ctypes.wintypes as wt

            user32 = self._user32
            kernel32 = self._kernel32
            psapi = self._psapi

            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None

            # Resolve PID
            pid = wt.DWORD(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if not pid.value:
                return None

            # Open process
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            PROCESS_VM_READ = 0x0010
            hproc = kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ,
                False,
                pid.value,
            )
            if not hproc:
                return None

            # GetModuleBaseName for process name
            name_buf = ctypes.create_unicode_buffer(260)
            name_len = psapi.GetModuleBaseNameW(hproc, None, name_buf, 260)
            kernel32.CloseHandle(hproc)
            process_name = name_buf.value if name_len else ""

            # Window title
            title_buf = ctypes.create_unicode_buffer(512)
            title_len = user32.GetWindowTextW(hwnd, title_buf, 512)
            window_title = title_buf.value if title_len else ""

            return (int(pid.value), process_name, window_title)

        except Exception as e:
            log.debug(f"_Win32Probe.query error: {e}")
            return None


# ---------------------------------------------------------------------------
# FarScry Service
# ---------------------------------------------------------------------------


class FarScryService:
    """
    Asyncio-compatible foreground window watcher with Kairo Eye cursor-OCR context.

    Usage
    -----
    service = FarScryService()
    queue = service.subscribe()
    asyncio.create_task(service.run())

    # In consumer:
    event = await queue.get()
    print(event.app_label, event.domain)
    """

    POLL_INTERVAL: float = 0.25  # seconds
    MAX_SUBSCRIBERS: int = 32
    CACHE_TTL_MS: int = 100

    def __init__(self, poll_interval: float = POLL_INTERVAL):
        self._poll_interval = poll_interval
        self._probe = _Win32Probe()
        self._queues: List[asyncio.Queue] = []
        self._last_pid: int = 0
        self._running: bool = False
        self._current_event: Optional[AppChangedEvent] = None
        self._cache: Optional[KairoEyeContext] = None
        self._cache_time: float = 0

    def subscribe(self) -> asyncio.Queue:
        """
        Return a new asyncio.Queue that will receive AppChangedEvent objects.
        The queue is bounded (maxsize=64) to prevent unbounded memory growth.
        """
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._queues.append(q)
        return q

    def current_app(self) -> Optional[AppChangedEvent]:
        """Return the most recent AppChangedEvent (None if not yet polled)."""
        return self._current_event

    def current_domain(self) -> str:
        """Return the current domain string (default: 'general')."""
        return self._current_event.domain if self._current_event else "general"

    async def run(self) -> None:
        """
        Main polling coroutine.  Run with asyncio.create_task().

        Polls every POLL_INTERVAL seconds and publishes AppChangedEvent to
        all subscribed queues when the foreground process changes.
        """
        self._running = True
        log.info(
            f"[FarScry] Starting foreground-app watcher "
            f"(interval={self._poll_interval * 1000:.0f}ms, "
            f"platform={'win32' if self._probe.available else 'stub'})"
        )

        while self._running:
            await asyncio.sleep(self._poll_interval)
            self._tick()

    def stop(self) -> None:
        """Stop the polling loop at the next iteration."""
        self._running = False
        log.info("[FarScry] Stopping foreground-app watcher")

    def _tick(self) -> None:
        """Single poll iteration — called from the asyncio event loop."""
        result = self._probe.query()
        if result is None:
            return

        pid, process_name, window_title = result

        if pid == self._last_pid:
            return  # No change

        self._last_pid = pid
        label = _label_for_process(process_name)
        domain = _domain_for_label(label)

        event = AppChangedEvent(
            process_name=process_name,
            app_label=label,
            domain=domain,
            pid=pid,
            window_title=window_title,
        )
        self._current_event = event
        log.debug(f"[FarScry] App changed → {label} ({process_name}) domain={domain}")

        # Publish to all subscribers (best-effort: skip full queues)
        for q in list(self._queues):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                log.debug("[FarScry] Subscriber queue full — event dropped")

    async def get_context(self) -> KairoEyeContext:
        """
        Check cache (100ms TTL)
        Assemble KairoEyeContext with foreground app and OCR text around cursor
        """
        t0 = time.perf_counter()
        now = time.time() * 1000
        if self._cache and (now - self._cache_time) < self.CACHE_TTL_MS:
            return self._cache

        app_evt = self.current_app()
        app_name = app_evt.process_name if app_evt else "Unknown"
        window_title = app_evt.window_title if app_evt else "Unknown"
        domain = app_evt.domain if app_evt else "general"

        ocr_text = ""
        try:
            ocr_text = self._capture_and_ocr()
        except Exception as e:
            log.debug(f"OCR failed: {e}")

        elapsed_ms = (time.perf_counter() - t0) * 1000

        ctx = KairoEyeContext(
            app_name=app_name,
            window_title=window_title,
            domain=domain,
            cursor_region_text=ocr_text,
            confidence=0.9,
            assembled_ms=elapsed_ms,
        )
        self._cache = ctx
        self._cache_time = now
        return ctx

    def _run_ocr(self, image_bytes: bytes) -> str:
        """Run OCR on image bytes with graceful degradation."""
        try:
            import pytesseract
            from PIL import Image
            import io

            img = Image.open(io.BytesIO(image_bytes))
            return pytesseract.image_to_string(img, timeout=2)
        except ImportError:
            log.debug(
                "[FarscryService] pytesseract not installed — OCR unavailable, using empty string"
            )
            return ""
        except Exception as e:
            log.debug(f"[FarscryService] OCR failed: {e}")
            return ""

    def _capture_and_ocr(self) -> str:
        """Capture a 200x200px region around the cursor and perform OCR."""
        try:
            import pyautogui
            import io

            x, y = pyautogui.position()
            left = max(0, x - 100)
            top = max(0, y - 100)
            screenshot = pyautogui.screenshot(region=(left, top, 200, 200))
            # Convert PIL image to bytes for _run_ocr
            buf = io.BytesIO()
            screenshot.save(buf, format="PNG")
            return self._run_ocr(buf.getvalue())
        except ImportError:
            log.debug("[FarscryService] pyautogui not installed — screen capture unavailable")
            return ""
        except Exception as e:
            log.debug(f"[FarscryService] Screen capture failed: {e}")
            return ""


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------


def farscry_app_name() -> str:
    """
    One-shot synchronous probe: return the foreground process name.
    Returns an empty string if the Win32 API is unavailable.
    """
    probe = _Win32Probe()
    result = probe.query()
    return result[1] if result else ""


def farscry_app_label() -> str:
    """
    One-shot synchronous probe: return the friendly app label.
    Returns "Unknown" if unavailable.
    """
    process_name = farscry_app_name()
    return _label_for_process(process_name) if process_name else "Unknown"


def farscry_domain() -> str:
    """
    One-shot synchronous probe: return the current Kairo domain.
    Returns "general" if unavailable.
    """
    label = farscry_app_label()
    return _domain_for_label(label)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_service_singleton: Optional[FarScryService] = None


def get_farscry_service() -> FarScryService:
    """Return the module-level singleton FarScryService (created on first call)."""
    global _service_singleton
    if _service_singleton is None:
        _service_singleton = FarScryService()
    return _service_singleton
