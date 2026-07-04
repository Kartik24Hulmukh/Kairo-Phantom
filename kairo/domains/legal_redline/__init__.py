# PROVENANCE: original | legal-redline domain descriptor for plugin registry
"""Legal-redline domain — wraps the existing cmd_redline handler.

This descriptor registers the ``redline`` CLI subcommand by delegating to
the existing ``kairo.cli.cmd_redline`` function.  No engine code is moved
or duplicated.
"""

from __future__ import annotations

import argparse

from kairo.domains.registry import Domain, register


def _register_cli(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "redline",
        help="Run the real redline pipeline on a contract",
    )
    parser.add_argument("contract", help="Path to the contract .docx file")
    parser.add_argument(
        "playbook", help="Path to the redline playbook .json file"
    )
    parser.add_argument(
        "--sealed",
        action="store_true",
        help="Run in sealed mode with live air-gap egress capture",
    )
    parser.add_argument(
        "--out",
        default="redline_output",
        help="Output directory for artifacts (default: redline_output)",
    )


def _run(args: argparse.Namespace) -> int:
    from kairo.cli import cmd_redline

    return cmd_redline(args)


DOMAIN = Domain(
    name="legal_redline",
    cli_name="redline",
    status="Real",
    summary=(
        "docx_tracked_changes_readback + clause_coverage + no_hallucinated_citation "
        "+ injection_block + airgap_egress + audit_log_integrity"
    ),
    register_cli=_register_cli,
    run=_run,
    requirements=[
        "python-docx>=1.1.0",
        "cryptography>=42.0.0",
    ],
)

register(DOMAIN)
