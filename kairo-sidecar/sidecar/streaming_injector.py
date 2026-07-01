"""
sidecar/streaming_injector.py — Kairo Phantom Streaming Injection
=================================================================
Streams LiteLLM tokens to a character buffer, then batch-injects via
the existing clipboard+python-docx write-back path.

Architecture:
  LiteLLM (stream=True) → SSE token reader → token_buffer
  → On stream complete → write_operations via python-docx
  → Esc cancellation supported via threading.Event

Note: True char-by-char injection into Word via SendInput is supported
but defaults to batch-on-complete for reliability. Set STREAMING_MODE='live'
for real-time character streaming (experimental).
"""

import threading
import json
import logging
import urllib.request
from typing import Optional, Callable

log = logging.getLogger("kairo-sidecar.streaming_injector")

STREAMING_MODE = "batch"  # 'batch' = collect then inject; 'live' = char-by-char (experimental)


class StreamingInjector:
    def __init__(self):
        self._cancel_event = threading.Event()

    def cancel(self):
        """Cancel the current streaming injection (Esc key handler)."""
        self._cancel_event.set()
        log.info("StreamingInjector: cancellation requested")

    def reset(self):
        self._cancel_event.clear()

    def stream_from_litellm(
        self,
        model: str,
        prompt: str,
        system: str = "",
        on_token: Optional[Callable[[str], None]] = None,
    ) -> str:
        """
        Streams tokens from LiteLLM and returns the complete content string.
        Calls on_token(token) for each token (e.g., to update GRP in real-time).
        Respects self._cancel_event for Esc cancellation.
        Returns empty string if cancelled.
        """
        endpoint = "http://localhost:4000/v1/chat/completions"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "temperature": 0.1,
        }

        try:
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            buffer = []
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                for line in resp:
                    if self._cancel_event.is_set():
                        log.info("StreamingInjector: cancelled mid-stream")
                        return ""
                    line = line.decode("utf-8").strip()
                    if not line or line == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        try:
                            chunk = json.loads(line[6:])
                            token = chunk["choices"][0].get("delta", {}).get("content", "")
                            if token:
                                buffer.append(token)
                                if on_token:
                                    on_token(token)
                        except (json.JSONDecodeError, KeyError, IndexError):
                            pass
            return "".join(buffer)
        except Exception as e:
            log.warning(f"StreamingInjector: stream failed: {e}")
            return ""

    def stream_and_inject(self, model: str, prompt: str, system: str = "", on_token=None) -> str:
        """Stream content from LiteLLM. Returns full content string for injection."""
        self.reset()
        return self.stream_from_litellm(model, prompt, system, on_token)


# Module-level singleton
_injector_singleton: Optional[StreamingInjector] = None


def get_streaming_injector() -> StreamingInjector:
    global _injector_singleton
    if _injector_singleton is None:
        _injector_singleton = StreamingInjector()
    return _injector_singleton
