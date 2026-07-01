from __future__ import annotations
import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum
import httpx
from .vlm_config import get_vlm_config

logger = logging.getLogger(__name__)


class DownloadState(str, Enum):
    NOT_STARTED = "not_started"
    DOWNLOADING = "downloading"
    COMPLETE = "complete"
    FAILED = "failed"
    VERIFYING = "verifying"


@dataclass
class DownloadProgress:
    state: DownloadState
    bytes_downloaded: int = 0
    total_bytes: int = 0
    speed_mbps: float = 0.0
    eta_seconds: float = 0.0
    error: str = ""

    @property
    def percent(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return min(100.0, (self.bytes_downloaded / self.total_bytes) * 100)

    @property
    def is_complete(self) -> bool:
        return self.state == DownloadState.COMPLETE

    @property
    def is_active(self) -> bool:
        return self.state in (DownloadState.DOWNLOADING, DownloadState.VERIFYING)


class TrayProgressNotifier:
    def __init__(self):
        self.PIPE_NAME = chr(92) + chr(92) + "." + chr(92) + "pipe" + chr(92) + "kairo"

    def notify(self, progress):
        try:
            payload = json.dumps(
                dict(
                    type="vlm_download_progress",
                    state=progress.state.value,
                    percent=round(progress.percent, 1),
                    error=progress.error,
                )
            )
            import win32file

            handle = win32file.CreateFile(
                self.PIPE_NAME, win32file.GENERIC_WRITE, 0, None, win32file.OPEN_EXISTING, 0, None
            )
            win32file.WriteFile(handle, (payload + chr(10)).encode())
            win32file.CloseHandle(handle)
        except Exception:
            pass


class VlmDownloadManager:
    def __init__(self, config, notifier=None):
        self.config = config
        self.notifier = notifier or TrayProgressNotifier()
        self._progress = DownloadProgress(state=DownloadState.NOT_STARTED)
        self._lock = asyncio.Lock()

    @property
    def progress(self):
        return self._progress

    @property
    def target_model_tag(self):
        spec = self.config.selected_model
        return spec.ollama_pull_tag or spec.ollama_name

    def _ollama_has_model(self, name):
        try:
            resp = httpx.get(self.config.ollama_url + "/api/tags", timeout=5.0)
            resp.raise_for_status()
            data = resp.json()
            for m in data.get("models", list()):
                mn = m.get("name", "")
                if mn == name or mn.startswith(name):
                    return True
        except Exception:
            return False
        return False

    @property
    def is_model_ready(self):
        return self._ollama_has_model(self.target_model_tag)

    async def ensure_model_available(self, on_progress=None):
        async with self._lock:
            if self.is_model_ready:
                self._progress = DownloadProgress(state=DownloadState.COMPLETE)
                logger.info("VLM model already available: %s", self.target_model_tag)
                return True
            logger.info("Pulling Ollama-native VLM model: %s", self.target_model_tag)
            return await self._pull_model(on_progress)

    async def _pull_model(self, on_progress=None):
        tag = self.target_model_tag
        self._progress = DownloadProgress(state=DownloadState.DOWNLOADING)
        last_notify = 0.0
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=None)) as client:
                async with client.stream(
                    "POST", self.config.ollama_url + "/api/pull", json=dict(model=tag, stream=True)
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        evt = json.loads(line)
                        if evt.get("error"):
                            return self._fail(str(evt.get("error")))
                        total = evt.get("total")
                        completed = evt.get("completed")
                        if total:
                            self._progress.total_bytes = int(total)
                            self._progress.bytes_downloaded = int(completed or 0)
                        now = time.monotonic()
                        if now - last_notify >= 1.0:
                            last_notify = now
                            self.notifier.notify(self._progress)
                            if on_progress:
                                on_progress(self._progress)
            self._progress = DownloadProgress(state=DownloadState.COMPLETE)
            self.notifier.notify(self._progress)
            if on_progress:
                on_progress(self._progress)
            logger.info("VLM model pull complete: %s", tag)
            return True
        except httpx.HTTPError as e:
            return self._fail("ollama pull HTTP error: " + str(e))
        except Exception as e:
            logger.error("VLM pull error: %s", e, exc_info=True)
            return self._fail(str(e))

    def _fail(self, message):
        logger.error("VLM model pull failed: %s", message)
        self._progress = DownloadProgress(state=DownloadState.FAILED, error=message)
        self.notifier.notify(self._progress)
        return False


class BackgroundVlmDownloader:
    def __init__(self):
        self.config = get_vlm_config()
        self.manager = VlmDownloadManager(self.config)
        self._thread = None
        self._loop = None

    @property
    def is_ready(self):
        return self.manager.is_model_ready

    @property
    def is_downloading(self):
        return self.manager.progress.is_active

    @property
    def download_progress(self):
        return self.manager.progress

    def start(self, on_progress=None):
        if self.is_ready or self.is_downloading:
            return
        self._thread = threading.Thread(
            target=self._run_async_download,
            args=(on_progress,),
            name="kairo-vlm-download",
            daemon=True,
        )
        self._thread.start()
        logger.info("VLM background pull started")

    def _run_async_download(self, on_progress=None):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(
                self.manager.ensure_model_available(on_progress=on_progress)
            )
        finally:
            self._loop.close()


_downloader = None


def get_background_downloader():
    global _downloader
    if _downloader is None:
        _downloader = BackgroundVlmDownloader()
    return _downloader
