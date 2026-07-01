"""Tests for opt-in telemetry module."""

import sys
import os
import json
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import sidecar.telemetry as telemetry_module
from sidecar.telemetry import is_opted_in, record_operation, get_summary


def _write_config(tmp_path: Path, enabled: bool):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"telemetry_enabled": enabled}))
    return config_file


def test_is_opted_in_false_by_default(tmp_path):
    with patch.object(telemetry_module, "CONFIG_FILE", tmp_path / "config.json"):
        assert is_opted_in() is False


def test_is_opted_in_true(tmp_path):
    _write_config(tmp_path, True)
    with patch.object(telemetry_module, "CONFIG_FILE", tmp_path / "config.json"):
        assert is_opted_in() is True


def test_record_operation_no_op_when_not_opted_in(tmp_path):
    tel_file = tmp_path / "telemetry.jsonl"
    with (
        patch.object(telemetry_module, "CONFIG_FILE", tmp_path / "no_config.json"),
        patch.object(telemetry_module, "TELEMETRY_FILE", tel_file),
    ):
        record_operation("word", 123.4)
    assert not tel_file.exists()


def test_record_operation_writes_when_opted_in(tmp_path):
    _write_config(tmp_path, True)
    tel_file = tmp_path / "telemetry.jsonl"
    with (
        patch.object(telemetry_module, "CONFIG_FILE", tmp_path / "config.json"),
        patch.object(telemetry_module, "TELEMETRY_FILE", tel_file),
    ):
        record_operation("word", 123.4, success=True)
        record_operation("excel", 456.7, success=False)
    assert tel_file.exists()
    lines = tel_file.read_text().splitlines()
    assert len(lines) == 2
    e1 = json.loads(lines[0])
    assert e1["domain"] == "word"
    assert e1["latency_ms"] == 123.4
    assert e1["success"] is True
    e2 = json.loads(lines[1])
    assert e2["domain"] == "excel"
    assert e2["success"] is False


def test_get_summary_empty(tmp_path):
    tel_file = tmp_path / "telemetry.jsonl"
    with patch.object(telemetry_module, "TELEMETRY_FILE", tel_file):
        summary = get_summary()
    assert summary["operations"] == 0
    assert summary["domains"] == {}
    assert summary["avg_latency_ms"] == 0


def test_get_summary_with_data(tmp_path):
    _write_config(tmp_path, True)
    tel_file = tmp_path / "telemetry.jsonl"
    with (
        patch.object(telemetry_module, "CONFIG_FILE", tmp_path / "config.json"),
        patch.object(telemetry_module, "TELEMETRY_FILE", tel_file),
    ):
        record_operation("word", 100.0)
        record_operation("word", 200.0)
        record_operation("excel", 300.0)
        summary = get_summary()
    assert summary["operations"] == 3
    assert summary["domains"]["word"] == 2
    assert summary["domains"]["excel"] == 1
    assert summary["avg_latency_ms"] == 200.0


def test_record_span_writes_when_opted_in(tmp_path):
    _write_config(tmp_path, True)
    spans_file = tmp_path / "spans.jsonl"
    with (
        patch.object(telemetry_module, "CONFIG_FILE", tmp_path / "config.json"),
        patch.object(telemetry_module, "SPANS_FILE", spans_file),
    ):
        span_id = telemetry_module.record_span("test_span", 50.0, attributes={"key": "val"})
    assert spans_file.exists()
    span = json.loads(spans_file.read_text().strip())
    assert span["name"] == "test_span"
    assert span["duration_ms"] == 50.0
    assert span["span_id"] == span_id
    assert span["attributes"]["key"] == "val"


def test_traced_operation_success(tmp_path):
    _write_config(tmp_path, True)
    tel_file = tmp_path / "telemetry.jsonl"
    spans_file = tmp_path / "spans.jsonl"
    with (
        patch.object(telemetry_module, "CONFIG_FILE", tmp_path / "config.json"),
        patch.object(telemetry_module, "TELEMETRY_FILE", tel_file),
        patch.object(telemetry_module, "SPANS_FILE", spans_file),
    ):
        with telemetry_module.traced_operation("op_name", domain="word") as ctx:
            ctx["ok"] = True

    assert tel_file.exists()
    assert spans_file.exists()
    span = json.loads(spans_file.read_text().strip())
    assert span["name"] == "op_name"
    assert span["status"] == "OK"
    assert span["attributes"]["domain"] == "word"


def test_air_gap_mode_suppresses_writes(tmp_path):
    _write_config(tmp_path, True)
    tel_file = tmp_path / "telemetry.jsonl"
    spans_file = tmp_path / "spans.jsonl"
    prom_file = tmp_path / "metrics.prom"
    logs_file = tmp_path / "logs.jsonl"

    with (
        patch.dict(os.environ, {"KAIRO_OFFLINE": "1"}),
        patch.object(telemetry_module, "CONFIG_FILE", tmp_path / "config.json"),
        patch.object(telemetry_module, "TELEMETRY_FILE", tel_file),
        patch.object(telemetry_module, "SPANS_FILE", spans_file),
        patch.object(telemetry_module, "METRICS_PROM_FILE", prom_file),
        patch.object(telemetry_module, "LOGS_JSONL_FILE", logs_file),
    ):
        telemetry_module.record_operation("word", 100.0)
        telemetry_module.record_span("span_name", 10.0)

    assert not tel_file.exists()
    assert not spans_file.exists()
    assert not prom_file.exists()
    assert not logs_file.exists()


def test_telemetry_scrub_pii(tmp_path):
    _write_config(tmp_path, True)
    tel_file = tmp_path / "telemetry.jsonl"
    spans_file = tmp_path / "spans.jsonl"
    prom_file = tmp_path / "metrics.prom"
    logs_file = tmp_path / "logs.jsonl"

    with (
        patch.object(telemetry_module, "CONFIG_FILE", tmp_path / "config.json"),
        patch.object(telemetry_module, "TELEMETRY_FILE", tel_file),
        patch.object(telemetry_module, "SPANS_FILE", spans_file),
        patch.object(telemetry_module, "METRICS_PROM_FILE", prom_file),
        patch.object(telemetry_module, "LOGS_JSONL_FILE", logs_file),
    ):
        telemetry_module.record_operation("word_C:\\Users\\john_doe\\doc.docx", 123.4)

        telemetry_module.record_span(
            name="process_user_john@example.com",
            duration_ms=50.0,
            attributes={
                "phone": "Call 123-456-7890",
                "ssn": "SSN: 123-45-6789",
                "list_attr": ["user@example.com", "clean_text"],
                "dict_attr": {"nested_email": "nested@example.com"},
            },
        )

    assert tel_file.exists()
    assert spans_file.exists()
    assert prom_file.exists()
    assert logs_file.exists()

    tel_data = json.loads(tel_file.read_text().strip())
    assert "john_doe" not in tel_data["domain"]
    assert "[USER]" in tel_data["domain"]

    span_data = json.loads(spans_file.read_text().strip())
    assert "john@example.com" not in span_data["name"]
    assert "[EMAIL]" in span_data["name"]
    assert span_data["attributes"]["phone"] == "Call [PHONE]"
    assert span_data["attributes"]["ssn"] == "SSN: [SSN]"
    assert span_data["attributes"]["list_attr"] == ["[EMAIL]", "clean_text"]
    assert span_data["attributes"]["dict_attr"] == {"nested_email": "[EMAIL]"}


def test_telemetry_standard_formats(tmp_path):
    _write_config(tmp_path, True)
    tel_file = tmp_path / "telemetry.jsonl"
    spans_file = tmp_path / "spans.jsonl"
    prom_file = tmp_path / "metrics.prom"
    logs_file = tmp_path / "logs.jsonl"

    with (
        patch.object(telemetry_module, "CONFIG_FILE", tmp_path / "config.json"),
        patch.object(telemetry_module, "TELEMETRY_FILE", tel_file),
        patch.object(telemetry_module, "SPANS_FILE", spans_file),
        patch.object(telemetry_module, "METRICS_PROM_FILE", prom_file),
        patch.object(telemetry_module, "LOGS_JSONL_FILE", logs_file),
    ):
        telemetry_module.record_operation("word", 100.0, success=True)
        telemetry_module.record_operation("word", 200.0, success=True)
        telemetry_module.record_operation("excel", 150.0, success=False)

        telemetry_module.record_span("span_1", 30.0, status="OK")
        telemetry_module.record_span("span_2", 40.0, status="ERROR")

    assert prom_file.exists()
    prom_content = prom_file.read_text()
    assert "# HELP kairo_operations_total" in prom_content
    assert "# TYPE kairo_operations_total counter" in prom_content
    assert 'kairo_operations_total{domain="word",success="true"} 2' in prom_content
    assert 'kairo_operations_total{domain="excel",success="false"} 1' in prom_content
    assert "# HELP kairo_operation_latency_ms" in prom_content
    assert "# TYPE kairo_operation_latency_ms gauge" in prom_content
    assert 'kairo_operation_latency_ms{domain="word"} 150.0' in prom_content
    assert 'kairo_operation_latency_ms{domain="excel"} 150.0' in prom_content

    assert logs_file.exists()
    logs_lines = logs_file.read_text().splitlines()
    assert len(logs_lines) == 2
    otel_span_1 = json.loads(logs_lines[0])
    otel_span_2 = json.loads(logs_lines[1])

    assert otel_span_1["name"] == "span_1"
    assert otel_span_1["kind"] == "SPAN_KIND_INTERNAL"
    assert "startTimeUnixNano" in otel_span_1
    assert "endTimeUnixNano" in otel_span_1
    assert otel_span_1["status"] == {"code": "STATUS_CODE_OK", "message": "OK"}

    assert otel_span_2["name"] == "span_2"
    assert otel_span_2["status"] == {"code": "STATUS_CODE_ERROR", "message": "ERROR"}


import pytest


@pytest.fixture(autouse=True)
def _clear_offline_env(monkeypatch):
    # CI sets KAIRO_OFFLINE=1 globally, suppressing telemetry/updater writes & network.
    # These tests exercise the opted-in / online paths, so clear it per-test.
    # Tests that need offline behavior set KAIRO_OFFLINE themselves via patch.dict.
    monkeypatch.delenv("KAIRO_OFFLINE", raising=False)
