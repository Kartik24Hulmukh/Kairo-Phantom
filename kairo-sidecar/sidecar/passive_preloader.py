"""
passive_preloader.py — Kairo Phantom Passive Model Preloader
=============================================================
Warms up LiteLLM models on sidecar startup by sending a silent 5-token completion
to kairo-standard (and kairo-fast) to eliminate first-request cold start.

Runs entirely in a daemon background thread — never blocks startup.

Usage:
    from sidecar.passive_preloader import start_background_warmup
    start_background_warmup()  # non-blocking, returns immediately
"""

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from typing import List

log = logging.getLogger("kairo-sidecar.passive_preloader")

LITELLM_URL = "http://localhost:4000/v1/chat/completions"
WARMUP_MODELS: List[str] = ["kairo-standard", "kairo-fast"]  # warm in priority order
WARMUP_PROMPT = "OK"  # minimal prompt — just enough to trigger model weight loading
STARTUP_DELAY_S = 3.0  # wait for LiteLLM proxy to be ready before first warmup
INTER_MODEL_DELAY_S = 2.0  # delay between warming up successive models


def _warmup_model(model: str) -> bool:
    """
    Send a silent warmup request to the LiteLLM proxy for the given model.
    Returns True if the model responded successfully; False otherwise.
    Failures are non-critical — logged at DEBUG level only.
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": WARMUP_PROMPT}],
        "max_tokens": 3,
        "temperature": 0.0,
    }
    try:
        req = urllib.request.Request(
            LITELLM_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            resp.read()  # consume response body
        log.info("PassivePreloader: %s warmed up successfully", model)
        return True
    except urllib.error.HTTPError as e:
        # HTTP errors (e.g. 404 model not found) are non-fatal
        log.debug(
            "PassivePreloader: %s returned HTTP %d (non-critical: %s)", model, e.code, e.reason
        )
        return False
    except Exception as e:
        log.debug("PassivePreloader: %s warmup failed (non-critical): %s", model, e)
        return False


def _warmup_all() -> None:
    """Warm up all models sequentially with a delay between each."""
    time.sleep(STARTUP_DELAY_S)  # give LiteLLM proxy time to start
    for model in WARMUP_MODELS:
        success = _warmup_model(model)
        log.debug("PassivePreloader: %s warmup result: %s", model, "OK" if success else "SKIPPED")
        time.sleep(INTER_MODEL_DELAY_S)
    log.info("PassivePreloader: all model warmups complete")


def start_background_warmup() -> threading.Thread:
    """
    Launch passive model warmup in a daemon background thread.
    Non-blocking — returns immediately. The thread silently stops
    when the main process exits.

    Returns:
        The warmup thread (for testing/monitoring purposes).
    """
    t = threading.Thread(
        target=_warmup_all,
        daemon=True,
        name="kairo-passive-preloader",
    )
    t.start()
    log.info("PassivePreloader: background warmup thread started (models: %s)", WARMUP_MODELS)
    return t
