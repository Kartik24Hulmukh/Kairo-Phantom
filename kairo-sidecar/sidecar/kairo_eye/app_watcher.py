import os
import time
import logging
import threading
from enum import Enum
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger("kairo-sidecar.app_watcher")


class Domain(str, Enum):
    WORD = "word"
    EXCEL = "excel"
    POWERPOINT = "powerpoint"
    CODE = "code"
    BROWSER = "browser"
    TERMINAL = "terminal"
    EMAIL = "email"
    PDF = "pdf"
    NOTES = "notes"
    DESIGN = "design"
    MEDIA = "media"
    DATA = "data"
    UNKNOWN = "unknown"


class AppProfile:
    def __init__(self, domain: Domain, app_name: str, file_path: Optional[str] = None):
        self.domain = domain
        self.app_name = app_name
        self.file_path = file_path
        self.detected_at = time.time()
        self.preload_ready = False


class AppWatcher:
    """
    Monitors active application and routes to correct domain master.
    Polls every 500ms. Pre-loads context in background on app switch.
    """

    def __init__(self):
        self._current_profile: AppProfile = AppProfile(Domain.UNKNOWN, "Unknown")
        self._preload_cache: Dict[str, Any] = {}  # keyed by file_path
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="kairo-preload")
        self._lock = threading.RLock()
        self._running = False
        self._poll_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Public lifecycle
    # ------------------------------------------------------------------

    def start(self):
        """Start the 500ms polling loop in a background thread."""
        self._running = True
        self._poll_thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="kairo-app-watcher"
        )
        self._poll_thread.start()
        log.info("AppWatcher: started polling loop")

    def stop(self):
        """Stop the polling loop."""
        self._running = False
        if self._poll_thread:
            self._poll_thread.join(timeout=2.0)
        self._executor.shutdown(wait=False)
        log.info("AppWatcher: stopped")

    # ------------------------------------------------------------------
    # Polling loop
    # ------------------------------------------------------------------

    def _poll_loop(self):
        prev_profile_key = None
        while self._running:
            try:
                profile = self._detect_active_app()
                profile_key = f"{profile.app_name}:{profile.file_path}"
                if profile_key != prev_profile_key:
                    log.info(
                        f"AppWatcher: app changed to {profile.domain} "
                        f"({profile.app_name}) file={profile.file_path}"
                    )
                    with self._lock:
                        self._current_profile = profile
                    # Start background preload for document-based domains
                    if profile.file_path and profile.domain in (
                        Domain.WORD,
                        Domain.EXCEL,
                        Domain.POWERPOINT,
                        Domain.PDF,
                    ):
                        self._executor.submit(self._preload_context, profile)
                    prev_profile_key = profile_key
            except Exception as e:
                log.debug(f"AppWatcher poll error: {e}")
            time.sleep(0.5)  # 500ms poll

    # ------------------------------------------------------------------
    # Active-app detection
    # ------------------------------------------------------------------

    def _detect_active_app(self) -> AppProfile:
        """Detect the currently active application using Windows APIs."""
        import sys

        if sys.platform == "win32":
            return self._detect_windows()
        # Linux/macOS fallback
        return AppProfile(Domain.UNKNOWN, "Unknown")

    def _detect_windows(self) -> AppProfile:
        """Windows-specific app detection using ctypes/win32."""
        try:
            import ctypes
            import ctypes.wintypes

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return AppProfile(Domain.UNKNOWN, "Unknown")

            # Get window title
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buf, 512)
            window_title = buf.value

            # Get process name
            pid = ctypes.wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            h_process = kernel32.OpenProcess(
                0x0400 | 0x0010, False, pid
            )  # PROCESS_QUERY_INFO | PROCESS_VM_READ

            exe_buf = ctypes.create_unicode_buffer(512)
            if h_process:
                try:
                    psapi = ctypes.windll.psapi
                    psapi.GetModuleFileNameExW(h_process, None, exe_buf, 512)
                finally:
                    kernel32.CloseHandle(h_process)

            process_path = exe_buf.value.lower()
            process_name = os.path.basename(process_path)

            return self._classify_process(process_name, window_title)
        except Exception as e:
            log.debug(f"Windows detection failed: {e}")
            return AppProfile(Domain.UNKNOWN, "Unknown")

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def _classify_process(self, process_name: str, window_title: str) -> AppProfile:
        """Map process name to Domain."""
        p = process_name.lower()
        t = window_title.lower()

        # Microsoft Office
        if "winword" in p:
            file_path = self._extract_file_from_title(window_title, [".docx", ".doc", ".rtf"])
            return AppProfile(Domain.WORD, "Microsoft Word", file_path)
        elif "excel" in p:
            file_path = self._extract_file_from_title(window_title, [".xlsx", ".xlsm", ".csv"])
            return AppProfile(Domain.EXCEL, "Microsoft Excel", file_path)
        elif "powerpnt" in p:
            file_path = self._extract_file_from_title(window_title, [".pptx", ".pptm"])
            return AppProfile(Domain.POWERPOINT, "Microsoft PowerPoint", file_path)
        elif "outlook" in p or "thunderbird" in p:
            return AppProfile(Domain.EMAIL, process_name)
        # Browsers
        elif any(b in p for b in ["chrome", "msedge", "firefox", "safari", "brave"]):
            url = self._extract_url_from_title(window_title)
            return AppProfile(Domain.BROWSER, process_name, url)
        # Code editors — VS Code, Cursor, Windsurf, PyCharm family, IntelliJ (idea64),
        # WebStorm, GoLand, Rider, CLion, Visual Studio, Vim, Neovim, Sublime, Atom
        elif any(
            c in p
            for c in [
                "code",
                "cursor",
                "windsurf",
                "pycharm",
                "intellij",
                "idea64",
                "idea",
                "webstorm",
                "goland",
                "rider",
                "clion",
                "devenv",  # Visual Studio
                "vim",
                "nvim",
                "sublime",
                "atom",
            ]
        ):
            file_path = self._extract_file_from_title(
                window_title,
                [".py", ".ts", ".js", ".rs", ".go", ".java", ".cs", ".cpp", ".c"],
            )
            return AppProfile(Domain.CODE, process_name, file_path)
        # Terminals
        elif any(
            t_name in p
            for t_name in [
                "windowsterminal",
                "cmd",
                "powershell",
                "wt",
                "conhost",
                "alacritty",
                "wezterm",
            ]
        ):
            return AppProfile(Domain.TERMINAL, process_name)
        # PDF viewers — Adobe Reader (AcroRd32/Acrobat), Foxit, SumatraPDF
        elif any(
            pdf in p
            for pdf in [
                "acrobat",
                "acrord",  # AcroRd32.exe + Acrobat.exe
                "foxit",
                "sumatrapdf",
                "pdfxchange",
            ]
        ):
            file_path = self._extract_file_from_title(window_title, [".pdf"])
            return AppProfile(Domain.PDF, process_name, file_path)
        # Design tools — Figma, Penpot, Canva, Adobe XD, Photoshop, Illustrator, Sketch, Affinity, Inkscape
        elif any(
            d in p
            for d in [
                "figma",
                "penpot",
                "canva",
                "xd",
                "photoshop",
                "illustrator",
                "sketch",
                "affinity",
                "inkscape",
                "gimp",
            ]
        ):
            return AppProfile(Domain.DESIGN, process_name)
        # Notes apps
        elif any(n in p for n in ["obsidian", "notion", "logseq", "bear", "roam"]):
            file_path = self._extract_file_from_title(window_title, [".md", ".txt"])
            return AppProfile(Domain.NOTES, process_name, file_path)
        # Media editors — DaVinci Resolve, Premiere Pro, After Effects, Final Cut, Audacity
        elif any(
            m in p
            for m in [
                "davinci",
                "resolve",
                "premiere",
                "afterfx",
                "aftereffects",
                "audacity",
                "davinciresolve",
                "finalcut",
                "capcut",
            ]
        ):
            return AppProfile(Domain.MEDIA, process_name)
        # Jupyter/data
        elif any(j in p for j in ["jupyter", "rstudio", "databricks"]):
            return AppProfile(Domain.DATA, process_name)
        # Title-based fallbacks
        elif ".docx" in t or ".doc" in t:
            return AppProfile(
                Domain.WORD,
                process_name,
                self._extract_file_from_title(window_title, [".docx", ".doc"]),
            )
        elif ".xlsx" in t or ".csv" in t:
            return AppProfile(
                Domain.EXCEL,
                process_name,
                self._extract_file_from_title(window_title, [".xlsx", ".csv"]),
            )
        elif ".pptx" in t:
            return AppProfile(
                Domain.POWERPOINT,
                process_name,
                self._extract_file_from_title(window_title, [".pptx"]),
            )
        elif ".pdf" in t:
            return AppProfile(
                Domain.PDF,
                process_name,
                self._extract_file_from_title(window_title, [".pdf"]),
            )

        return AppProfile(Domain.UNKNOWN, process_name)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_file_from_title(self, title: str, extensions: list) -> Optional[str]:
        """Extract file path from window title if it contains a known file extension."""
        import re

        for ext in extensions:
            # Match Windows paths: C:\...\filename.ext or just filename.ext
            pattern = (
                rf"([A-Za-z]:\\[^|:\"<>?*]+{re.escape(ext)}" rf"|[\w\s\-_.()]+{re.escape(ext)})"
            )
            m = re.search(pattern, title, re.IGNORECASE)
            if m:
                candidate = m.group(1).strip()
                # Try to resolve to absolute path
                if os.path.isabs(candidate) and os.path.exists(candidate):
                    return candidate
                # Return as-is (might be relative)
                return candidate
        return None

    def _extract_url_from_title(self, title: str) -> Optional[str]:
        """Extract URL hint from browser window title."""
        import re

        m = re.search(r"https?://[^\s|]+", title)
        if m:
            return m.group(0)
        return None

    # ------------------------------------------------------------------
    # Background preload
    # ------------------------------------------------------------------

    def _preload_context(self, profile: AppProfile):
        """Background preload of domain context into cache."""
        try:
            file_path = profile.file_path
            if not file_path:
                return

            cache_key = (
                f"{file_path}:" f"{os.path.getmtime(file_path) if os.path.exists(file_path) else 0}"
            )

            with self._lock:
                if cache_key in self._preload_cache:
                    log.debug(f"AppWatcher: preload cache hit for {file_path}")
                    return

            log.info(f"AppWatcher: preloading context for {profile.domain} - {file_path}")
            context = None

            if profile.domain == Domain.WORD and file_path.endswith((".docx", ".doc")):
                try:
                    from sidecar.masters.word_master import WordContextExtractor

                    extractor = WordContextExtractor()
                    context = extractor.extract(file_path, 0).to_dict()
                except Exception as e:
                    log.warning(f"Word preload failed: {e}")

            elif profile.domain == Domain.EXCEL and file_path.endswith((".xlsx", ".xlsm", ".csv")):
                try:
                    from sidecar.masters.excel_master import ExcelContextExtractor

                    extractor = ExcelContextExtractor()
                    context = extractor.extract(file_path, "A1").to_dict()
                except Exception as e:
                    log.warning(f"Excel preload failed: {e}")

            elif profile.domain == Domain.PDF and file_path.endswith(".pdf"):
                try:
                    from sidecar.parsers.pdf_parser import PDFParser

                    parser = PDFParser()
                    context = parser.parse(file_path)
                except Exception as e:
                    log.warning(f"PDF preload failed: {e}")

            if context is not None:
                with self._lock:
                    self._preload_cache[cache_key] = context
                    # Also store by file_path for quick lookup
                    self._preload_cache[file_path] = context
                log.info(f"AppWatcher: preload complete for {file_path}")
                profile.preload_ready = True
        except Exception as e:
            log.error(f"AppWatcher: preload failed for {profile.file_path}: {e}")

    # ------------------------------------------------------------------
    # Public getters
    # ------------------------------------------------------------------

    def get_current_profile(self) -> AppProfile:
        """Return the current app profile (thread-safe)."""
        with self._lock:
            return self._current_profile

    def get_preloaded_context(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Return preloaded context for a file path, or None if not cached."""
        with self._lock:
            return self._preload_cache.get(file_path)

    def get_domain_for_process(self, process_name: str) -> Domain:
        """Utility method: classify a process name string to a Domain. Used in tests."""
        profile = self._classify_process(process_name, "")
        return profile.domain
