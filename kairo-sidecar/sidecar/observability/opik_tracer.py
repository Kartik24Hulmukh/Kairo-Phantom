"""
Opik Tracer — Local Observability Emit Layer (Phase 0.1)

This module provides the observability emit layer for Kairo Phantom.
Since Docker (and therefore self-hosted Opik) is not available in all
environments, this module writes trace data to a local JSONL file
that serves as a queue sink. When Opik is available, the queue can
be flushed to the Opik server.

The trace data is also linked to the Rust-side provenance receipt
system (identity.rs) via the `opik_trace_id` field.

NEVER mock trace data. If the emit fails, it errors loudly.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Callable
from functools import wraps


# Default trace log path — mirrors the Rust receipts.jsonl location
DEFAULT_TRACE_DIR = Path.home() / ".kairo-phantom"
DEFAULT_TRACE_PATH = DEFAULT_TRACE_DIR / "opik_traces.jsonl"


class TraceContext:
    """Context for a single observability trace."""

    def __init__(
        self,
        trace_id: str,
        domain: str,
        action: str,
        input_summary: str = "",
        model: str = "",
    ):
        self.trace_id = trace_id
        self.domain = domain
        self.action = action
        self.input_summary = input_summary
        self.model = model
        self.start_time = time.time()
        self.spans: list[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {}

    def add_span(
        self,
        name: str,
        input_data: str = "",
        output_data: str = "",
        latency_ms: float = 0.0,
        grounded: bool = False,
    ) -> None:
        """Add a span to this trace."""
        self.spans.append(
            {
                "name": name,
                "input": _redact_pii(input_data),
                "output": _redact_pii(output_data),
                "latency_ms": latency_ms,
                "grounded": grounded,
                "timestamp": time.time(),
            }
        )

    def set_metadata(self, key: str, value: Any) -> None:
        self.metadata[key] = value

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the trace to a dictionary for JSONL storage."""
        return {
            "trace_id": self.trace_id,
            "domain": self.domain,
            "action": self.action,
            "input_summary": _redact_pii(self.input_summary),
            "model": self.model,
            "start_time": self.start_time,
            "end_time": time.time(),
            "latency_ms": (time.time() - self.start_time) * 1000,
            "spans": self.spans,
            "metadata": self.metadata,
        }

    @property
    def trace_url(self) -> str:
        """Generate a trace URL. When Opik is running, this is a clickable link."""
        opik_host = os.environ.get("OPIK_HOST", "http://localhost:5173")
        return f"{opik_host}/trace/{self.trace_id}"


class OpikTracer:
    """
    Local observability tracer.

    Writes trace data to a local JSONL file. When Opik self-hosted is
    available (Docker), traces can be flushed to the Opik server.

    Usage:
        tracer = OpikTracer()
        with tracer.trace("word", "generate_response") as ctx:
            ctx.add_span("llm_call", input_data="prompt", output_data="response")
            # ... do work ...
        # Trace is automatically written to JSONL on exit
    """

    def __init__(self, trace_path: Optional[Path] = None):
        self.trace_path = trace_path or DEFAULT_TRACE_PATH
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        """Ensure the trace directory exists. Errors are deferred to emit()."""
        try:
            self.trace_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass  # Will be caught by emit() when trying to write

    def trace(
        self,
        domain: str,
        action: str,
        input_summary: str = "",
        model: str = "",
    ) -> _TraceContextManager:
        """
        Create a new trace context.

        Returns a context manager that writes the trace to JSONL on exit.
        """
        trace_id = f"trace_{uuid.uuid4().hex[:16]}"
        ctx = TraceContext(trace_id, domain, action, input_summary, model)
        return _TraceContextManager(self, ctx)

    def emit(self, ctx: TraceContext) -> str:
        """
        Write a trace to the local JSONL file.

        Returns the trace_id. Raises on write failure — NEVER silently drops.
        """
        trace_dict = ctx.to_dict()

        line = json.dumps(trace_dict, ensure_ascii=False)
        try:
            with open(self.trace_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError as e:
            raise RuntimeError(
                f"OpikTracer: Failed to write trace to {self.trace_path}: {e}. "
                f"Trace data is NOT lost — it's in memory. Fix the file path or permissions."
            ) from e

        return ctx.trace_id

    def read_traces(self) -> list[Dict[str, Any]]:
        """Read all traces from the JSONL file."""
        if not self.trace_path.exists():
            return []
        traces = []
        with open(self.trace_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    traces.append(json.loads(line))
        return traces

    def clear(self) -> None:
        """Clear the trace file (for testing)."""
        if self.trace_path.exists():
            self.trace_path.unlink()


class _TraceContextManager:
    """Context manager for OpikTracer.trace()."""

    def __init__(self, tracer: OpikTracer, ctx: TraceContext):
        self._tracer = tracer
        self._ctx = ctx

    def __enter__(self) -> TraceContext:
        return self._ctx

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is None:
            self._ctx.set_metadata("outcome", "ok")
        else:
            self._ctx.set_metadata("outcome", "error")
            self._ctx.set_metadata("error", str(exc_val))
        self._tracer.emit(self._ctx)


def track(domain: str, action: str = "domain_master_call") -> Callable:
    """
    Decorator that wraps a domain master method with Opik tracing.

    Usage:
        @track("word", "generate_response")
        def generate_response(self, prompt: str) -> str:
            ...
    """

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            tracer = _get_global_tracer()
            input_summary = str(args[1] if len(args) > 1 else kwargs.get("prompt", ""))[:200]
            with tracer.trace(domain, action, input_summary=input_summary) as ctx:
                try:
                    result = fn(*args, **kwargs)
                    ctx.add_span(
                        name=fn.__name__,
                        output_data=str(result)[:200] if result else "",
                        latency_ms=(time.time() - ctx.start_time) * 1000,
                        grounded=True,
                    )
                    return result
                except Exception as e:
                    ctx.add_span(
                        name=f"{fn.__name__}_error",
                        output_data=str(e)[:200],
                        latency_ms=(time.time() - ctx.start_time) * 1000,
                        grounded=False,
                    )
                    raise

        return wrapper

    return decorator


# ── Global tracer instance ────────────────────────────────────────────────────

_global_tracer: Optional[OpikTracer] = None


def _get_global_tracer() -> OpikTracer:
    """Get or create the global tracer instance."""
    global _global_tracer
    if _global_tracer is None:
        _global_tracer = OpikTracer()
    return _global_tracer


def set_global_tracer(tracer: OpikTracer) -> None:
    """Override the global tracer (for testing)."""
    global _global_tracer
    _global_tracer = tracer


# ── PII Redaction ──────────────────────────────────────────────────────────────

# Patterns for PII redaction in trace data
_PII_PATTERNS = [
    # SSN: XXX-XX-XXXX
    (r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED_SSN]"),
    # Email addresses
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[REDACTED_EMAIL]"),
    # Phone: XXX-XXX-XXXX
    (r"\b\d{3}-\d{3}-\d{4}\b", "[REDACTED_PHONE]"),
    # Credit card: XXXX-XXXX-XXXX-XXXX
    (r"\b\d{4}-\d{4}-\d{4}-\d{4}\b", "[REDACTED_CC]"),
]


def _redact_pii(text: str) -> str:
    """Redact PII from text before storing in traces."""
    if not text:
        return text
    import re

    result = text
    for pattern, replacement in _PII_PATTERNS:
        result = re.sub(pattern, replacement, result)
    return result


# ── Provenance Bridge ──────────────────────────────────────────────────────────


def generate_trace_id() -> str:
    """Generate a unique trace ID."""
    return f"trace_{uuid.uuid4().hex[:16]}"


def create_provenance_context(
    domain: str,
    action: str,
    document_path: str,
    trace_id: str,
    trace_url: str,
) -> str:
    """
    Create a context string for the Rust-side provenance receipt.

    This string is passed to ReceiptLog.emit_with_trace() as the `context`
    parameter, linking the Python trace to the Rust receipt.
    """
    return json.dumps(
        {
            "domain": domain,
            "action": action,
            "document": document_path,
            "trace_id": trace_id,
            "trace_url": trace_url,
        },
        ensure_ascii=False,
    )
