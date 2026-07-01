"""Tests for the integrated CI scan gates (vulnerabilities and secrets)."""

import os
import sys

# Add sidecar/repository root to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sidecar.secret_gate import run_gate
from scripts.verify_production_gate import check_vulnerabilities


def test_ci_scan_gates_with_clean_workspace(tmp_path):
    (tmp_path / "Cargo.toml").write_text('[dependencies]\nrand = "0.8.5"\n')
    (tmp_path / "requirements.txt").write_text("fastapi==0.100.0\n")
    (tmp_path / "main.py").write_text("print('Hello World')\n")

    assert run_gate(str(tmp_path)) is True
    assert check_vulnerabilities(str(tmp_path)) is True


def test_ci_scan_gates_fails_on_secret(tmp_path):
    (tmp_path / "Cargo.toml").write_text('[dependencies]\nrand = "0.8.5"\n')
    (tmp_path / "requirements.txt").write_text("fastapi==0.100.0\n")
    (tmp_path / "main.py").write_text("OPENAI_KEY = 'sk-proj-abcdefghijklmnopqrstuvwxyz123456'\n")

    assert run_gate(str(tmp_path)) is False


def test_ci_scan_gates_fails_on_database_url_secret(tmp_path):
    (tmp_path / "Cargo.toml").write_text('[dependencies]\nrand = "0.8.5"\n')
    (tmp_path / "requirements.txt").write_text("fastapi==0.100.0\n")
    (tmp_path / "main.py").write_text(
        "db = 'postgres://admin:secretpassword123@localhost:5432/mydb'\n"
    )

    assert run_gate(str(tmp_path)) is False


def test_ci_scan_gates_fails_on_planted_vulnerability_cargo(tmp_path):
    (tmp_path / "requirements.txt").write_text("fastapi==0.100.0\n")
    (tmp_path / "Cargo.toml").write_text('[dependencies]\nvulnerable-rust-pkg = "1.0.0"\n')

    assert check_vulnerabilities(str(tmp_path)) is False


def test_ci_scan_gates_fails_on_planted_cve_comment_requirements(tmp_path):
    (tmp_path / "Cargo.toml").write_text('[dependencies]\nrand = "0.8.5"\n')
    (tmp_path / "requirements.txt").write_text("urllib3==1.26.4 # CVE-2021-33503\n")

    assert check_vulnerabilities(str(tmp_path)) is False
