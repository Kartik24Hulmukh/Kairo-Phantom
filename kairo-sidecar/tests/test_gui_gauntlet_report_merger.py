"""Unit tests for gui_gauntlet_report_merger.py."""

import sys
import os
import json
import tempfile
import pytest

# Add the repositories/kairo-phantom directory to the path so we can import from scripts
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from scripts.gui_gauntlet_report_merger import merge_reports


@pytest.fixture
def cleanup_report():
    """Ensure gui_gauntlet_report.json is cleaned up after each test."""
    report_file = "gui_gauntlet_report.json"
    if os.path.exists(report_file):
        os.remove(report_file)
    yield
    if os.path.exists(report_file):
        os.remove(report_file)


def test_merge_reports_pass(cleanup_report):
    """Test merge_reports when gate threshold is met."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create nested dirs and results.json files
        dir1 = os.path.join(tmpdir, "word")
        dir2 = os.path.join(tmpdir, "excel")
        os.makedirs(dir1)
        os.makedirs(dir2)

        results_word = [
            {"id": "WORD_001", "app": "Word", "status": "PASSED", "elapsed": 100},
            {"id": "WORD_002", "app": "Word", "status": "PASSED", "elapsed": 120},
        ]
        results_excel = [
            {"id": "EXCEL_001", "app": "Excel", "status": "PASSED", "elapsed": 150},
            {
                "id": "EXCEL_002",
                "app": "Excel",
                "status": "ORACLE_FAILED",
                "elapsed": 180,
                "error": "Mismatch",
            },
            {"id": "EXCEL_003", "app": "Excel", "status": "PASSED", "elapsed": 110},
        ]

        with open(os.path.join(dir1, "results.json"), "w", encoding="utf-8") as f:
            json.dump(results_word, f)
        with open(os.path.join(dir2, "results.json"), "w", encoding="utf-8") as f:
            json.dump(results_excel, f)

        # 4 passed out of 5 total = 80.0% pass rate. Threshold is 80.0, so it should PASS.
        exit_code = merge_reports(tmpdir, gate_threshold=80.0)
        assert exit_code == 0

        # Check created file
        assert os.path.exists("gui_gauntlet_report.json")
        with open("gui_gauntlet_report.json", "r", encoding="utf-8") as f:
            report = json.load(f)

        assert report["total"] == 5
        assert report["passed"] == 4
        assert report["failed"] == 1
        assert report["pass_rate"] == 80.0
        assert len(report["results"]) == 5


def test_merge_reports_fail(cleanup_report):
    """Test merge_reports when gate threshold is not met."""
    with tempfile.TemporaryDirectory() as tmpdir:
        dir1 = os.path.join(tmpdir, "word")
        os.makedirs(dir1)

        results_word = [
            {"id": "WORD_001", "app": "Word", "status": "PASSED", "elapsed": 100},
            {
                "id": "WORD_002",
                "app": "Word",
                "status": "ORACLE_FAILED",
                "elapsed": 120,
                "error": "Fail",
            },
        ]

        with open(os.path.join(dir1, "results.json"), "w", encoding="utf-8") as f:
            json.dump(results_word, f)

        # 1 passed out of 2 total = 50.0% pass rate. Threshold is 80.0, so it should FAIL.
        exit_code = merge_reports(tmpdir, gate_threshold=80.0)
        assert exit_code == 1

        assert os.path.exists("gui_gauntlet_report.json")
        with open("gui_gauntlet_report.json", "r", encoding="utf-8") as f:
            report = json.load(f)

        assert report["total"] == 2
        assert report["passed"] == 1
        assert report["failed"] == 1
        assert report["pass_rate"] == 50.0


def test_merge_reports_no_files(cleanup_report):
    """Test merge_reports when no results.json files are found."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Empty directory
        exit_code = merge_reports(tmpdir, gate_threshold=80.0)
        assert exit_code == 1

        assert os.path.exists("gui_gauntlet_report.json")
        with open("gui_gauntlet_report.json", "r", encoding="utf-8") as f:
            report = json.load(f)

        assert report["total"] == 0
        assert report["passed"] == 0
        assert report["failed"] == 0
        assert report["pass_rate"] == 0.0
        assert len(report["results"]) == 0


def test_merge_reports_malformed_results(cleanup_report):
    """Test merge_reports when a results.json file is malformed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        dir1 = os.path.join(tmpdir, "word")
        os.makedirs(dir1)

        # Write invalid JSON content
        with open(os.path.join(dir1, "results.json"), "w", encoding="utf-8") as f:
            f.write("{invalid_json: true")

        exit_code = merge_reports(tmpdir, gate_threshold=80.0)
        assert exit_code == 1

        assert os.path.exists("gui_gauntlet_report.json")
        with open("gui_gauntlet_report.json", "r", encoding="utf-8") as f:
            report = json.load(f)

        assert report["total"] == 0
        assert "error" in report
