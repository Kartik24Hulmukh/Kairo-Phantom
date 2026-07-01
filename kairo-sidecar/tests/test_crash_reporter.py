"""Tests for crash reporter module."""

import sys
import os
import json
from unittest.mock import patch
import pytest


@pytest.fixture(autouse=True)
def _clear_offline_env(monkeypatch):
    # These tests exercise the crash-WRITE path, disabled when KAIRO_OFFLINE=1.
    # CI sets that var globally, so clear it per-test. The offline-mode test
    # re-sets it inside its own scope.
    monkeypatch.delenv("KAIRO_OFFLINE", raising=False)


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import sidecar.crash_reporter as crash_module
from sidecar.crash_reporter import (
    install_crash_handler,
    _write_crash_report,
    write_manual_crash,
    _crash_handler,
)


def test_install_crash_handler():
    original = sys.excepthook
    sys.excepthook = lambda *a: None
    try:
        install_crash_handler()
        assert sys.excepthook is _crash_handler
    finally:
        sys.excepthook = original


def test_write_crash_report(tmp_path):
    with patch.object(crash_module, "CRASH_DIR", tmp_path):
        try:
            raise ValueError("test error")
        except ValueError:
            exc_type, exc_value, exc_tb = sys.exc_info()
            crash_file = _write_crash_report(exc_type, exc_value, exc_tb)
    assert crash_file.exists()
    data = json.loads(crash_file.read_text())
    assert data["exception"]["type"] == "ValueError"
    assert data["exception"]["message"] == "test error"
    assert "platform" in data
    assert data["version"] == "3.9.0"
    # Confirm no PII fields
    assert "user_text" not in data
    assert "document_content" not in data


def test_write_crash_report_traceback_is_list(tmp_path):
    with patch.object(crash_module, "CRASH_DIR", tmp_path):
        try:
            raise RuntimeError("traceback test")
        except RuntimeError:
            exc_type, exc_value, exc_tb = sys.exc_info()
            crash_file = _write_crash_report(exc_type, exc_value, exc_tb)
    data = json.loads(crash_file.read_text())
    assert isinstance(data["exception"]["traceback"], list)


def test_write_manual_crash(tmp_path):
    with patch.object(crash_module, "CRASH_DIR", tmp_path):
        crash_file = write_manual_crash("manual error", extra={"context": "test"})
    assert crash_file.exists()
    data = json.loads(crash_file.read_text())
    assert data["message"] == "manual error"
    assert data["type"] == "manual"
    assert data["extra"]["context"] == "test"


def test_crash_handler_writes_file(tmp_path, capsys):
    with patch.object(crash_module, "CRASH_DIR", tmp_path):
        try:
            raise KeyError("missing_key")
        except KeyError:
            exc_type, exc_value, exc_tb = sys.exc_info()
            with patch("sys.__excepthook__", lambda *a: None):
                _crash_handler(exc_type, exc_value, exc_tb)
    files = list(tmp_path.glob("crash_*.json"))
    assert len(files) == 1
    captured = capsys.readouterr()
    assert "Kairo Phantom" in captured.err
    assert "github.com" in captured.err


def test_scrub_pii_user_directory():
    raw_path_win = "Error in file C:\\Users\\john_doe\\app\\main.py at line 12"
    scrubbed_win = crash_module.scrub_pii(raw_path_win)
    assert scrubbed_win == "Error in file C:\\Users\\[USER]\\app\\main.py at line 12"

    raw_path_unix = "Error in file /Users/john_doe/app/main.py at line 12"
    scrubbed_unix = crash_module.scrub_pii(raw_path_unix)
    assert scrubbed_unix == "Error in file /Users/[USER]/app/main.py at line 12"

    raw_path_lower = "Error in /users/alice_smith/project"
    scrubbed_lower = crash_module.scrub_pii(raw_path_lower)
    assert scrubbed_lower == "Error in /users/[USER]/project"


def test_crash_reporter_offline_mode(tmp_path):
    with patch.object(crash_module, "CRASH_DIR", tmp_path):
        with patch.dict(os.environ, {"KAIRO_OFFLINE": "1"}):
            try:
                raise ValueError("offline error")
            except ValueError:
                exc_type, exc_value, exc_tb = sys.exc_info()
                crash_file = _write_crash_report(exc_type, exc_value, exc_tb)
            assert crash_file is None

            manual_file = write_manual_crash("manual offline error")
            assert manual_file is None

            files = list(tmp_path.glob("crash_*.json"))
            assert len(files) == 0


def test_crash_reporter_source_map_hashes():
    try:
        raise ValueError("test source map")
    except ValueError:
        exc_type, exc_value, exc_tb = sys.exc_info()
        frames = crash_module._build_source_map(exc_tb)

    assert len(frames) > 0
    test_frame = frames[-1]
    assert test_frame["file"].endswith("test_crash_reporter.py")
    assert test_frame["file_hash"] is not None
    assert len(test_frame["file_hash"]) == 16
    assert len(test_frame["context"]) > 0
