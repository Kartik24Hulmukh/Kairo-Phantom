"""
Opt-in anonymous telemetry for Kairo Phantom.
Collects ONLY: operation counts, latency percentiles, error counts.
NEVER collects: document content, user text, filenames, or any PII.
Opt-in: disabled by default.

Observability design (Item 56):
- OpenTelemetry-compatible span structure written to local JSONL (zero network).
- Air-gap mode (KAIRO_OFFLINE=1 or telemetry_enabled=False) suppresses ALL writes.
- Spans include trace_id, span_id, parent_span_id for distributed trace correlation.
"""

import json
import time
import uuid
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional
from collections import defaultdict
import os
from sidecar.crash_reporter import scrub_pii


class ScrubbedLogger:
    def __init__(self, logger):
        self._logger = logger

    def debug(self, msg, *args, **kwargs):
        self._logger.debug(scrub_pii(msg), *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        self._logger.info(scrub_pii(msg), *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self._logger.warning(scrub_pii(msg), *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self._logger.error(scrub_pii(msg), *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        self._logger.critical(scrub_pii(msg), *args, **kwargs)


log = ScrubbedLogger(logging.getLogger("kairo.telemetry"))

TELEMETRY_FILE = Path.home() / ".kairo-phantom" / "telemetry.jsonl"
SPANS_FILE = Path.home() / ".kairo-phantom" / "spans.jsonl"
CONFIG_FILE = Path.home() / ".kairo-phantom" / "config.json"
METRICS_PROM_FILE = Path.home() / ".kairo-phantom" / "metrics.prom"
LOGS_JSONL_FILE = Path.home() / ".kairo-phantom" / "logs.jsonl"


def _is_air_gapped() -> bool:
    """Return True if offline mode is active — suppresses all telemetry writes."""
    return os.environ.get("KAIRO_OFFLINE") == "1"


def is_opted_in() -> bool:
    """Check if user has opted into telemetry. Default: False."""
    if _is_air_gapped():
        return False
    try:
        config = json.loads(CONFIG_FILE.read_text())
        return config.get("telemetry_enabled", False)
    except Exception:
        return False


def _update_prometheus_metrics() -> None:
    """Read all entries from telemetry.jsonl and generate metrics.prom in Prometheus exposition format."""
    if not TELEMETRY_FILE.exists():
        return

    counts = defaultdict(lambda: {"true": 0, "false": 0})
    latencies = defaultdict(list)
    try:
        for line in TELEMETRY_FILE.read_text().splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            dom = entry["domain"]
            succ = str(entry.get("success", True)).lower()
            counts[dom][succ] += 1
            latencies[dom].append(entry["latency_ms"])
    except Exception as e:
        log.debug(f"[Telemetry] Failed to parse telemetry.jsonl for prom metrics: {e}")
        return

    lines = []
    lines.append("# HELP kairo_operations_total Total number of operations recorded")
    lines.append("# TYPE kairo_operations_total counter")
    for dom, sub_counts in counts.items():
        for succ, val in sub_counts.items():
            lines.append(f'kairo_operations_total{{domain="{dom}",success="{succ}"}} {val}')

    lines.append("# HELP kairo_operation_latency_ms Latency of operations in milliseconds")
    lines.append("# TYPE kairo_operation_latency_ms gauge")
    for dom, lats in latencies.items():
        if lats:
            avg_lat = round(sum(lats) / len(lats), 2)
            lines.append(f'kairo_operation_latency_ms{{domain="{dom}"}} {avg_lat}')

    try:
        METRICS_PROM_FILE.parent.mkdir(parents=True, exist_ok=True)
        METRICS_PROM_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception as e:
        log.debug(f"[Telemetry] Metrics prom write failed: {e}")


def record_operation(domain: str, latency_ms: float, success: bool = True) -> None:
    """
    Record an anonymized operation metric.
    Only fires if user has opted in.
    NON-BLOCKING: writes to local JSONL file only (no network).
    """
    if not is_opted_in():
        return
    domain = scrub_pii(domain)
    entry = {
        "ts": int(time.time()),
        "domain": domain,
        "latency_ms": round(latency_ms, 1),
        "success": success,
    }
    try:
        TELEMETRY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TELEMETRY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        _update_prometheus_metrics()
    except Exception as e:
        log.debug(f"[Telemetry] Write failed: {e}")


def record_span(
    name: str,
    duration_ms: float,
    status: str = "OK",
    trace_id: Optional[str] = None,
    parent_span_id: Optional[str] = None,
    attributes: Optional[Dict] = None,
) -> str:
    """
    Record an OpenTelemetry-compatible span.
    Returns the span_id for use as parent_span_id by child spans.
    Zero outbound network calls — written to local spans.jsonl only.
    """
    span_id = uuid.uuid4().hex[:16]
    if trace_id is None:
        trace_id = uuid.uuid4().hex

    name = scrub_pii(name)
    status = scrub_pii(status)
    scrubbed_attributes = {}
    if attributes:
        for k, v in attributes.items():
            k_scrubbed = scrub_pii(str(k))
            if isinstance(v, str):
                v_scrubbed = scrub_pii(v)
            elif isinstance(v, dict):
                v_scrubbed = {
                    scrub_pii(str(dk)): (scrub_pii(dv) if isinstance(dv, str) else dv)
                    for dk, dv in v.items()
                }
            elif isinstance(v, list):
                v_scrubbed = [scrub_pii(item) if isinstance(item, str) else item for item in v]
            else:
                v_scrubbed = v
            scrubbed_attributes[k_scrubbed] = v_scrubbed

    span = {
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "name": name,
        "start_time_ms": int(time.time() * 1000) - int(duration_ms),
        "end_time_ms": int(time.time() * 1000),
        "duration_ms": round(duration_ms, 2),
        "status": status,
        "attributes": scrubbed_attributes,
    }

    if not is_opted_in():
        return span_id  # Still return a valid span_id for chaining even when off

    try:
        SPANS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SPANS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(span) + "\n")

        otel_span = {
            "traceId": span["trace_id"],
            "spanId": span["span_id"],
            "parentSpanId": span["parent_span_id"],
            "name": span["name"],
            "kind": "SPAN_KIND_INTERNAL",
            "startTimeUnixNano": str(int(span["start_time_ms"] * 1000000)),
            "endTimeUnixNano": str(int(span["end_time_ms"] * 1000000)),
            "attributes": span["attributes"],
            "status": {
                "code": "STATUS_CODE_OK" if span["status"] == "OK" else "STATUS_CODE_ERROR",
                "message": span["status"],
            },
        }
        LOGS_JSONL_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOGS_JSONL_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(otel_span) + "\n")
    except Exception as e:
        log.debug(f"[Telemetry] Span write failed: {e}")

    return span_id


@contextmanager
def traced_operation(
    name: str,
    domain: str = "",
    trace_id: Optional[str] = None,
    parent_span_id: Optional[str] = None,
):
    """
    Context manager that records both a legacy operation metric and an OTel span.

    Usage:
        with traced_operation("docx_edit", domain="word") as span_ctx:
            # do work
            span_ctx["ok"] = True
    """
    span_ctx: Dict = {"ok": True, "span_id": None}
    start = time.monotonic()
    try:
        yield span_ctx
    except Exception:
        span_ctx["ok"] = False
        raise
    finally:
        duration_ms = (time.monotonic() - start) * 1000
        status = "OK" if span_ctx.get("ok", True) else "ERROR"
        span_id = record_span(
            name=name,
            duration_ms=duration_ms,
            status=status,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            attributes={"domain": domain} if domain else {},
        )
        span_ctx["span_id"] = span_id
        if domain:
            record_operation(domain, duration_ms, success=span_ctx.get("ok", True))


def get_summary() -> Dict:
    """Read telemetry file and return summary statistics."""
    if not TELEMETRY_FILE.exists():
        return {"operations": 0, "domains": {}, "avg_latency_ms": 0}
    domain_counts: Dict[str, int] = defaultdict(int)
    latencies: List[float] = []
    try:
        for line in TELEMETRY_FILE.read_text().splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            domain_counts[entry["domain"]] += 1
            latencies.append(entry["latency_ms"])
    except Exception:
        pass
    return {
        "operations": sum(domain_counts.values()),
        "domains": dict(domain_counts),
        "avg_latency_ms": round(sum(latencies) / max(len(latencies), 1), 1),
    }


def get_spans(limit: int = 100) -> List[Dict]:
    """Read the most recent N spans from spans.jsonl for local inspection."""
    if not SPANS_FILE.exists():
        return []
    spans = []
    try:
        for line in SPANS_FILE.read_text().splitlines():
            if line.strip():
                spans.append(json.loads(line))
    except Exception:
        pass
    return spans[-limit:]
