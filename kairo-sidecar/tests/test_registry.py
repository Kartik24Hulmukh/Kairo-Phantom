# PROVENANCE: original | registry backward-compat + discovery tests
"""Tests for the domain plugin registry — backward compat + discovery.

Asserts the 4 backward-compat imports still work and that the registry
discovers the 3 existing domains with correct status.
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


class TestBackwardCompatImports:
    """The 4 backward-compat imports that must never break."""

    def test_cli_main_import(self):
        from kairo.cli import main

        assert callable(main)

    def test_pdf_engine_import(self):
        from kairo.pdf.engine import classify_pdf

        assert callable(classify_pdf)

    def test_excel_engine_import(self):
        from kairo.excel.engine import excel_pipeline

        assert callable(excel_pipeline)

    def test_legal_redline_pipeline_import(self):
        from kairo.oracles.legal_redline_pipeline import redline_contract

        assert callable(redline_contract)


class TestRegistryDiscovery:
    """Registry discovers the 3 existing domains."""

    def test_discovers_three_domains(self):
        from kairo.domains.registry import discover

        domains = discover()
        names = {d.name for d in domains}
        assert "legal_redline" in names
        assert "excel" in names
        assert "pdf" in names

    def test_all_domains_real(self):
        from kairo.domains.registry import discover

        domains = discover()
        for d in domains:
            assert d.status == "Real", f"{d.name} status should be Real, got {d.status}"

    def test_cli_names_match_commands(self):
        from kairo.domains.registry import discover

        domains = discover()
        cli_names = {d.cli_name for d in domains}
        assert "redline" in cli_names
        assert "excel" in cli_names
        assert "pdf" in cli_names

    def test_domains_have_requirements(self):
        from kairo.domains.registry import discover

        domains = discover()
        for d in domains:
            assert len(d.requirements) > 0, f"{d.name} should have requirements"


class TestCLIHelpListsCommands:
    """CLI --help lists all expected commands."""

    def test_help_lists_commands(self):
        from kairo.cli import main

        import io
        import contextlib

        buf = io.StringIO()
        with pytest.raises(SystemExit):
            with contextlib.redirect_stdout(buf):
                main(["--help"])
        output = buf.getvalue()
        assert "redline" in output
        assert "verify" in output
        assert "excel" in output
        assert "pdf" in output
