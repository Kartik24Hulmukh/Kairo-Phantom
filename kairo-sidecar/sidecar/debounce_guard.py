"""
sidecar/debounce_guard.py — Kairo Phantom Input Debounce Guard
=============================================================
Enforces a debounce/throttling period (default 200ms) on keyboard events (Alt+M).
Prevents duplicate invocations when Alt+M is pressed rapidly.
"""

import time
import logging

log = logging.getLogger("kairo-sidecar.debounce_guard")


class DebounceGuard:
    def __init__(self, interval_seconds: float = 0.2):
        self.interval = interval_seconds
        self.last_triggered = 0.0

    def should_process(self) -> bool:
        """
        Returns True if the event should be processed (not debounced).
        Returns False if the event occurs within the debounce window.
        """
        now = time.time()
        elapsed = now - self.last_triggered
        if elapsed >= self.interval:
            self.last_triggered = now
            return True
        log.warning(
            f"DebounceGuard: debounced request (elapsed={elapsed*1000:.1f}ms < {self.interval*1000:.1f}ms)"
        )
        return False
