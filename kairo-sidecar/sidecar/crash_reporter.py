"""
Crash reporter for Kairo Phantom Python sidecar.
On unhandled exception: writes structured JSON to ~/.kairo-phantom/crashes/
NEVER sends data externally.
"""

import sys
import json
import traceback
import platform
import time
import logging
import os
import hashlib
from pathlib import Path
from typing import Optional

log = logging.getLogger("kairo.crash-reporter")

CRASH_DIR = Path.home() / ".kairo-phantom" / "crashes"


def install_crash_handler() -> None:
    """Install as sys.excepthook to catch all unhandled exceptions."""
    sys.excepthook = _crash_handler
    log.debug("[CrashReporter] Crash handler installed")


def _crash_handler(exc_type, exc_value, exc_tb) -> None:
    """Write crash report and print user-friendly message."""
    crash_path = _write_crash_report(exc_type, exc_value, exc_tb)
    print("\n[Kairo Phantom] An unexpected error occurred.", file=sys.stderr)
    if crash_path:
        print(f"Crash report saved to: {crash_path}", file=sys.stderr)
    print(
        "Please report this at: https://github.com/KairoPhantom/Kairo-Phantom/issues",
        file=sys.stderr,
    )
    sys.__excepthook__(exc_type, exc_value, exc_tb)


import re


def scrub_pii(text: str) -> str:
    """Scrub common PII patterns (email, phone, SSN) from a string."""
    # Scrub email addresses
    text = re.sub(r"[\w\.-]+@[\w\.-]+\.\w+", "[EMAIL]", text)
    # Scrub phone numbers (simple pattern)
    text = re.sub(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b", "[PHONE]", text)
    # Scrub typical SSN
    text = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[SSN]", text)
    # Scrub local user directory paths (e.g. C:\Users\Username\... -> C:\Users\[USER]\...)
    text = re.sub(r"(?i)(users)([\\/])[^\\/]+", lambda m: f"{m.group(1)}{m.group(2)}[USER]", text)
    return text


def _build_source_map(exc_tb) -> list:
    """
    Build a symbolicated source map from a traceback — enriches frames with
    source file hash and code context (±2 lines) for offline crash debugging.
    """
    import traceback as tb_module

    frames = []
    if exc_tb is None:
        return frames
    for frame_summary in tb_module.extract_tb(exc_tb):
        frame = {
            "file": scrub_pii(frame_summary.filename),
            "line": frame_summary.lineno,
            "function": frame_summary.name,
            "code": scrub_pii(frame_summary.line or ""),
            "file_hash": None,
            "context": [],
        }
        # Add source context (±2 lines) and file hash for symbolication
        try:
            if frame_summary.filename and os.path.isfile(frame_summary.filename):
                with open(frame_summary.filename, "r", encoding="utf-8", errors="ignore") as f:
                    source_lines = f.readlines()
                file_hash = hashlib.sha256("".join(source_lines).encode()).hexdigest()[:16]
                frame["file_hash"] = file_hash

                start = max(0, frame_summary.lineno - 3)
                end = min(len(source_lines), frame_summary.lineno + 2)
                frame["context"] = [scrub_pii(source_lines[i].rstrip()) for i in range(start, end)]
        except Exception:
            pass
        frames.append(frame)
    return frames


def _write_crash_report(exc_type, exc_value, exc_tb) -> Optional[Path]:
    """Write structured JSON crash report with PII scrubbed and symbolicated source map."""
    if os.environ.get("KAIRO_OFFLINE") == "1":
        return None
    CRASH_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time())
    crash_file = CRASH_DIR / f"crash_{timestamp}.json"

    msg = scrub_pii(str(exc_value))
    tb_list = traceback.format_exception(exc_type, exc_value, exc_tb)
    tb_scrubbed = [scrub_pii(line) for line in tb_list]

    # Build exception chain (Python 3.11+ __cause__ / __context__)
    exception_chain = []
    current = exc_value
    seen = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        exception_chain.append(
            {
                "type": type(current).__name__,
                "message": scrub_pii(str(current)),
                "chained_via": "__cause__"
                if current.__cause__
                else ("__context__" if current.__context__ else None),
            }
        )
        current = current.__cause__ or current.__context__

    report = {
        "timestamp": timestamp,
        "version": "3.9.0",
        "platform": {
            "os": platform.system(),
            "os_version": platform.version(),
            "python": platform.python_version(),
            "machine": platform.machine(),
        },
        "exception": {
            "type": exc_type.__name__ if exc_type else "Unknown",
            "message": msg,
            "traceback": tb_scrubbed,
            "exception_chain": exception_chain,
        },
        "source_map": _build_source_map(exc_tb),
    }
    try:
        crash_file.write_text(json.dumps(report, indent=2, default=str))
        log.info(f"[CrashReporter] Crash report written to {crash_file}")
    except Exception as e:
        log.error(f"[CrashReporter] Failed to write crash report: {e}")
    return crash_file


def write_manual_crash(message: str, extra: dict = None) -> Optional[Path]:
    """Manually record a non-fatal error as a crash report."""
    if os.environ.get("KAIRO_OFFLINE") == "1":
        return None
    report = {
        "timestamp": int(time.time()),
        "version": "3.9.0",
        "type": "manual",
        "message": message,
        "extra": extra or {},
    }
    CRASH_DIR.mkdir(parents=True, exist_ok=True)
    crash_file = CRASH_DIR / f"crash_{int(time.time())}.json"
    crash_file.write_text(json.dumps(report, indent=2))
    return crash_file
