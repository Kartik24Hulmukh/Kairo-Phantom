"""
provenance_emit.py — Provenance emission layer for domain master tracing.

Provides:
  - ProvenanceEmitter: writes JSONL traces to a trace directory
  - @track decorator: wraps domain master methods to emit traces + receipts
  - get_emitter(): singleton accessor for the global emitter

Each trace entry contains:
  - timestamp, domain, method, args_summary, result_summary, receipt_id
  - receipt_id links to a provenance receipt (SHA-256 of trace content)

This is the Python-side observability layer. The Rust-side audit_chain.rs
provides the cryptographic chain. Together they form the provenance system.
"""

import os
import json
import time
import hashlib
import functools
from typing import Optional

# Default trace directory
_DEFAULT_TRACE_DIR = os.environ.get(
    "KAIRO_TRACE_DIR", os.path.join(os.path.expanduser("~"), ".kairo-phantom", "traces")
)

# Singleton emitter
_emitter: Optional["ProvenanceEmitter"] = None


class ProvenanceEmitter:
    """Emits JSONL traces and provenance receipts for domain master calls."""

    def __init__(self, trace_dir: str | None = None):
        self.trace_dir = trace_dir or _DEFAULT_TRACE_DIR
        os.makedirs(self.trace_dir, exist_ok=True)
        self.trace_file = os.path.join(self.trace_dir, f"traces_{int(time.time())}.jsonl")
        self._trace_count = 0

    def emit(
        self,
        domain: str,
        method: str,
        args_summary: str,
        result_summary: str,
        metadata: dict | None = None,
    ) -> str:
        """Emit a trace entry and return the receipt_id."""
        entry = {
            "timestamp": time.time(),
            "domain": domain,
            "method": method,
            "args_summary": args_summary,
            "result_summary": result_summary,
            "metadata": metadata or {},
        }
        # Generate receipt_id as SHA-256 of the trace entry
        entry_str = json.dumps(entry, sort_keys=True)
        receipt_id = hashlib.sha256(entry_str.encode()).hexdigest()[:16]
        entry["receipt_id"] = receipt_id

        # Write to JSONL file
        with open(self.trace_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

        self._trace_count += 1
        return receipt_id

    @property
    def trace_count(self) -> int:
        return self._trace_count

    def get_traces(self) -> list[dict]:
        """Read all traces from the current trace file."""
        if not os.path.exists(self.trace_file):
            return []
        traces = []
        with open(self.trace_file) as f:
            for line in f:
                if line.strip():
                    traces.append(json.loads(line))
        return traces

    def clear(self):
        """Clear the trace file."""
        self.trace_file = os.path.join(self.trace_dir, f"traces_{int(time.time())}.jsonl")
        self._trace_count = 0


def get_emitter(trace_dir: str | None = None) -> ProvenanceEmitter:
    """Get or create the singleton ProvenanceEmitter."""
    global _emitter
    if _emitter is None or trace_dir is not None:
        _emitter = ProvenanceEmitter(trace_dir)
    return _emitter


def track(domain: str):
    """
    Decorator that wraps a domain master method to emit a provenance trace.

    Usage:
        @track("code")
        def process(self, ...):
            ...

    The decorated method will:
    1. Execute normally
    2. Emit a JSONL trace with domain, method, args, result
    3. Return the original result (trace is side-effect)
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Summarize args (first arg is usually self)
            args_summary = str(args[1:])[:200] if len(args) > 1 else str(kwargs)[:200]

            # Execute the function
            result = func(*args, **kwargs)

            # Summarize result
            result_summary = str(result)[:200] if result is not None else "None"

            # Emit trace
            try:
                emitter = get_emitter()
                emitter.emit(
                    domain=domain,
                    method=func.__name__,
                    args_summary=args_summary,
                    result_summary=result_summary,
                )
            except Exception:
                pass  # Tracing is non-fatal — never break production code

            return result

        return wrapper

    return decorator
