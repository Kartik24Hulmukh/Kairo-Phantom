# PROVENANCE: original | Excel domain descriptor for plugin registry
"""Excel domain — wraps the existing cmd_excel handler.

This descriptor registers the ``excel`` CLI subcommand by delegating to
the existing ``kairo.cli.cmd_excel`` function.  No engine code is moved
or duplicated.
"""

from __future__ import annotations

import argparse

from kairo.domains.registry import Domain, register


def _register_cli(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "excel",
        help="Run the Excel pipeline: edit → recompute → verify",
    )
    parser.add_argument("input", help="Path to the input .xlsx file")
    parser.add_argument(
        "spec", help="Path to the spec .json file (edits + expected values)"
    )
    parser.add_argument(
        "--out",
        default="excel_output",
        help="Output directory for artifacts (default: excel_output)",
    )


def _run(args: argparse.Namespace) -> int:
    from kairo.cli import cmd_excel

    return cmd_excel(args)


DOMAIN = Domain(
    name="excel",
    cli_name="excel",
    status="Real",
    summary=(
        "xlsx_recompute + xlsx_structure_readback — LibreOffice headless recompute, "
        "values verified vs independent Python calc, kill-proven, honest-degradation"
    ),
    register_cli=_register_cli,
    run=_run,
    requirements=[
        "openpyxl>=3.1.0",
        "numpy>=1.24.0",
    ],
)

register(DOMAIN)
