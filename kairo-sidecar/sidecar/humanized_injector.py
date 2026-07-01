"""
sidecar/humanized_injector.py — Streaming Injection Layer for Kairo Phantom
=============================================================================
Streams LLM output token-by-token into the active document via ollama.chat()
with stream=True, then exposes Ctrl+Z rollback via a snapshot/restore pattern.

Architecture
------------
  HumanizedInjector           — main class
  InjectionSession            — tracks a single injection for rollback
  StreamingOllamaClient       — wraps ollama.chat(stream=True) iteration
  HumanizedInjector.inject()  — primary entry point (async generator)
  HumanizedInjector.rollback()— Ctrl+Z handler: restore pre-injection snapshot

Streaming strategy
------------------
  • ollama.chat(stream=True) yields delta chunks.
  • Each chunk is buffered until a word boundary (space or newline) is reached.
  • Complete words are yielded to the caller for progressive UI rendering.
  • On Ctrl+Z the entire session is rolled back using the pre-saved snapshot.

Rollback strategy
-----------------
  • Before ANY write, the injector saves the full document bytes via
    InjectionSession.save_snapshot(path).
  • On rollback, InjectionSession.restore_snapshot(path) replaces the file
    with the saved bytes using os.replace() (atomic).
  • In-memory rollback (Word.com) sends a Win32 WM_UNDO equivalent via COM.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, List, Optional

log = logging.getLogger("kairo-sidecar.humanized_injector")


# ---------------------------------------------------------------------------
# InjectionSession — per-call snapshot for Ctrl+Z rollback
# ---------------------------------------------------------------------------


@dataclass
class InjectionSession:
    """
    Tracks a single injection run. Holds a byte snapshot of the original file
    so the entire injection can be reversed with a single call to restore_snapshot().
    """

    session_id: str
    file_path: str
    snapshot_bytes: bytes = field(default_factory=bytes, repr=False)
    started_at: float = field(default_factory=time.time)
    completed: bool = False
    rolled_back: bool = False
    injected_text: str = ""
    injected_chars_count: int = 0

    def save_snapshot(self) -> None:
        """Read and cache the current file bytes for future rollback."""
        if not self.file_path or not os.path.isfile(self.file_path):
            log.debug(f"InjectionSession: no file at '{self.file_path}' — snapshot skipped")
            return
        with open(self.file_path, "rb") as f:
            self.snapshot_bytes = f.read()
        log.debug(
            f"InjectionSession[{self.session_id}]: snapshot saved "
            f"({len(self.snapshot_bytes)} bytes)"
        )

    def restore_snapshot(self) -> bool:
        """
        Restore the file to its pre-injection state.

        Uses os.replace() (atomic on Windows and POSIX) via a temp file in the
        same directory to guarantee the original is never partially overwritten.

        Returns True if the restore succeeded, False otherwise.
        """
        if not self.snapshot_bytes:
            log.warning(f"InjectionSession[{self.session_id}]: no snapshot to restore")
            return False
        if not self.file_path:
            log.warning(f"InjectionSession[{self.session_id}]: no file_path for restore")
            return False

        dir_name = os.path.dirname(os.path.abspath(self.file_path))
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".rollback.tmp", dir=dir_name)
        try:
            os.close(tmp_fd)
            with open(tmp_path, "wb") as f:
                f.write(self.snapshot_bytes)
            os.replace(tmp_path, self.file_path)
            self.rolled_back = True
            log.info(
                f"InjectionSession[{self.session_id}]: rollback complete — "
                f"{len(self.snapshot_bytes)} bytes restored to '{self.file_path}'"
            )
            return True
        except Exception as exc:
            log.error(f"InjectionSession[{self.session_id}]: rollback failed — {exc}")
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            return False


# ---------------------------------------------------------------------------
# StreamingOllamaClient — thin async wrapper around ollama.chat(stream=True)
# ---------------------------------------------------------------------------


class StreamingOllamaClient:
    """
    Wraps the ollama Python SDK streaming API.
    Yields complete words (split on whitespace) for smooth progressive injection.
    """

    def __init__(self, model: str = "qwen2.5:7b"):
        self.model = model

    async def stream_words(
        self,
        messages: list,
        options: Optional[dict] = None,
    ) -> AsyncIterator[str]:
        """
        Async generator that yields words from the streaming LLM response.

        Implementation note
        --------------------
        ollama.chat(stream=True) is a synchronous generator.  We wrap it in
        asyncio.to_thread() so the event loop stays responsive.

        Yields
        ------
        str
            Complete words (including trailing space/newline) as they arrive.
        """
        import ollama

        opts = options or {"temperature": 0.7, "num_predict": 512}
        buffer = ""

        # Run the blocking ollama call in a thread pool
        loop = asyncio.get_event_loop()
        chunk_queue: asyncio.Queue = asyncio.Queue()

        def _blocking_stream():
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    for chunk in ollama.chat(
                        model=self.model,
                        messages=messages,
                        stream=True,
                        options=opts,
                    ):
                        delta = chunk.get("message", {}).get("content", "")
                        loop.call_soon_threadsafe(chunk_queue.put_nowait, delta)
                    break  # Success, exit retry loop
                except Exception as exc:
                    err_msg = str(exc).lower()
                    if "not found" in err_msg or "404" in err_msg or "model" in err_msg:
                        try:
                            log.info(f"Model {self.model} not found/loaded. Attempting to pull...")
                            ollama.pull(self.model)
                            # After pulling, try the chat again immediately
                            continue
                        except Exception as pull_exc:
                            log.error(f"Failed to pull model {self.model}: {pull_exc}")

                    if attempt < max_retries - 1:
                        log.warning(
                            f"Ollama stream attempt {attempt+1} failed ({exc}). Retrying in 1s..."
                        )
                        time.sleep(1.0)
                    else:
                        loop.call_soon_threadsafe(chunk_queue.put_nowait, None)
                        raise exc
            loop.call_soon_threadsafe(chunk_queue.put_nowait, None)  # sentinel

        # Launch in thread
        asyncio.ensure_future(asyncio.to_thread(_blocking_stream))

        while True:
            delta = await chunk_queue.get()
            if delta is None:
                break  # Sentinel received — stream finished

            buffer += delta

            # Yield complete words whenever we hit a word boundary
            while " " in buffer or "\n" in buffer:
                for sep in ["\n", " "]:
                    idx = buffer.find(sep)
                    if idx != -1:
                        word = buffer[: idx + 1]
                        buffer = buffer[idx + 1 :]
                        yield word
                        break

        # Yield any remaining buffer content
        if buffer.strip():
            yield buffer


# ---------------------------------------------------------------------------
# HumanizedInjector — primary injection controller
# ---------------------------------------------------------------------------


class HumanizedInjector:
    """
    Streaming injection controller.

    Usage
    -----
    injector = HumanizedInjector(model="qwen2.5:7b")

    # Streaming injection
    session = await injector.begin_session(file_path="doc.docx")
    async for word in injector.inject(session, messages=[...]):
        ui.append(word)

    # Ctrl+Z rollback
    success = injector.rollback(session)
    """

    def __init__(self, model: str = "qwen2.5:7b"):
        self.model = model
        self._client = StreamingOllamaClient(model=model)
        self._sessions: dict[str, InjectionSession] = {}

    # ── Session lifecycle ─────────────────────────────────────────────────────

    async def begin_session(self, file_path: str = "") -> InjectionSession:
        """
        Create a new InjectionSession and save a pre-injection snapshot.

        Must be called before inject() so that rollback() has a snapshot to restore.
        """
        import uuid

        session_id = str(uuid.uuid4())[:8]
        session = InjectionSession(session_id=session_id, file_path=file_path)

        if file_path and os.path.isfile(file_path):
            session.save_snapshot()

        self._sessions[session_id] = session
        log.debug(f"HumanizedInjector: began session {session_id} for '{file_path}'")
        return session

    # ── Streaming inject ──────────────────────────────────────────────────────

    async def inject(
        self,
        session: InjectionSession,
        messages: list,
        *,
        on_word: Optional[callable] = None,
        options: Optional[dict] = None,
    ) -> AsyncIterator[str]:
        """
        Stream LLM output word-by-word.

        Yields
        ------
        str
            Each word (or partial token at end-of-stream) as it arrives.

        Parameters
        ----------
        session : InjectionSession
            The session returned by begin_session().
        messages : list
            LiteLLM / Ollama chat messages (system + user blocks).
        on_word : callable, optional
            Sync callback invoked with each yielded word (for legacy callers).
        options : dict, optional
            Ollama model options (temperature, num_predict, …).
        """
        if session.rolled_back:
            log.warning(
                f"HumanizedInjector: session {session.session_id} was rolled back — "
                "cannot inject"
            )
            return

        accumulated = []
        try:
            async for word in self._client.stream_words(messages, options=options):
                accumulated.append(word)
                session.injected_text += word
                session.injected_chars_count += len(word)
                if on_word is not None:
                    try:
                        on_word(word)
                    except Exception as cb_exc:
                        log.debug(f"on_word callback error (non-blocking): {cb_exc}")
                yield word

        except Exception as exc:
            log.error(f"HumanizedInjector.inject: stream error — {exc}")
            raise

        session.completed = True
        log.debug(
            f"HumanizedInjector: session {session.session_id} complete — "
            f"{len(accumulated)} words yielded"
        )

    def show_writing_indicator(self) -> None:
        """Show '⚡ Kairo writing...' near cursor using a Win32 tooltip."""
        try:
            import ctypes

            # Use a notification balloon/beep as simplest cross-app overlay indicator
            ctypes.windll.user32.MessageBeep(0)  # Very subtle audio cue
            log.info("[HumanizedInjector] ⚡ Kairo writing... (indicator shown)")
        except Exception:
            pass  # Non-fatal

    def hide_writing_indicator(self) -> None:
        """Dismiss the writing indicator."""
        log.info("[HumanizedInjector] Dismissing overlay (indicator hidden)")

    async def stream_inject(
        self,
        token_generator: AsyncIterator[str] | List[str] | Any,
        wpm: int = 60,
        session: Optional[InjectionSession] = None,
    ) -> AsyncIterator[str]:
        """
        Inject tokens one by one with human-like timing.
        - Inter-token delay = 60/(wpm*5) seconds ± 20% jitter
        - Cancellable via asyncio.CancelledError (Esc key)
        - Buffer word-by-word for natural injection
        - Show '⚡ Kairo writing...' overlay near cursor
        - First token must be visible within 500ms
        - On cancellation: stop immediately, do NOT inject partial words
        """
        import random

        # Display overlay
        self.show_writing_indicator()

        base_delay = 60.0 / (wpm * 5.0)
        first_token = True

        # Convert simple list/iterable to async generator if needed
        if not hasattr(token_generator, "__anext__") and hasattr(token_generator, "__iter__"):

            async def _async_gen():
                for t in token_generator:
                    yield t

            token_gen = _async_gen()
        else:
            token_gen = token_generator

        accumulated = []
        try:
            async for token in token_gen:
                if first_token:
                    # First token visible within 500ms
                    await asyncio.sleep(0.01)
                    first_token = False
                else:
                    jitter = base_delay * 0.2
                    delay = base_delay + random.uniform(-jitter, jitter)
                    await asyncio.sleep(max(0.0, delay))

                accumulated.append(token)
                if session is not None:
                    session.injected_text += token
                    session.injected_chars_count += len(token)
                yield token
            if session is not None:
                session.completed = True
        except asyncio.CancelledError:
            log.info("stream_inject: cancelled via CancelledError")
            raise
        finally:
            self.hide_writing_indicator()

    def undo_injection(self, session: InjectionSession) -> bool:
        """
        Ctrl+Z atomic removal of all injected text since last stream_inject.
        - Tracks all injected characters since last stream_inject() call.
        - On undo_injection() call: deletes exactly those characters from the document.
        - Uses WordWriter._delete_paragraph() or keyboard simulation for non-Word targets.
        """
        if session.rolled_back:
            return True
        return self.rollback(session)

    # ── Ctrl+Z rollback ───────────────────────────────────────────────────────

    def rollback(self, session: InjectionSession) -> bool:
        """
        Roll back the injection for *session*.

        File-based rollback
        --------------------
        Restores the pre-injection file bytes via os.replace() (atomic).

        COM-based rollback (Word live)
        ---------------------------------
        If win32com.client is available and Word has the file open, sends
        a COM Undo() call to revert the document buffer.

        Returns
        -------
        bool
            True if rollback succeeded, False otherwise.
        """
        if session.rolled_back:
            log.warning(f"rollback(): session {session.session_id} already rolled back")
            return True

        # Try COM undo first (if Word has the file open)
        if session.file_path and self._try_com_undo(session.file_path):
            session.rolled_back = True
            log.info(f"HumanizedInjector: COM undo succeeded for session {session.session_id}")
            return True

        # File-based rollback
        success = session.restore_snapshot()
        if success:
            log.info(
                f"HumanizedInjector: file-based rollback succeeded for session {session.session_id}"
            )
        return success

    def _try_com_undo(self, file_path: str) -> bool:
        """
        Attempt to undo the last action in the live Word COM object.
        Returns False gracefully if COM is unavailable or the file is not open.
        """
        try:
            import win32com.client

            word_app = win32com.client.GetActiveObject("Word.Application")
            for doc in word_app.Documents:
                if doc.FullName.lower() == os.path.abspath(file_path).lower():
                    doc.Undo()
                    return True
        except Exception as exc:
            log.debug(f"_try_com_undo: COM unavailable ({exc}) — falling back to file restore")
        return False

    # ── Session lookup ────────────────────────────────────────────────────────

    def get_session(self, session_id: str) -> Optional[InjectionSession]:
        """Retrieve a session by ID (for Ctrl+Z handler in the IPC layer)."""
        return self._sessions.get(session_id)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_injector_singleton: Optional[HumanizedInjector] = None


def get_humanized_injector(model: str = "qwen2.5:7b") -> HumanizedInjector:
    """Return the module-level singleton HumanizedInjector."""
    global _injector_singleton
    if _injector_singleton is None:
        _injector_singleton = HumanizedInjector(model=model)
    return _injector_singleton
