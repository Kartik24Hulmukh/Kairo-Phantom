# PROVENANCE: original | PDF domain descriptor for plugin registry
"""PDF domain — wraps the existing cmd_pdf handler.

This descriptor registers the ``pdf`` CLI subcommand (with its
extract/redact/fill/sign/verify sub-actions) by delegating to the
existing ``kairo.cli.cmd_pdf`` function.  No engine code is moved
or duplicated.
"""

from __future__ import annotations

import argparse
import sys

from kairo.domains.registry import Domain, register


def _register_cli(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "pdf",
        help="Run the PDF pipeline: extract/redact/fill/sign/verify",
    )
    pdf_subparsers = parser.add_subparsers(dest="action", help="PDF action")

    # pdf extract
    pdf_extract = pdf_subparsers.add_parser(
        "extract", help="Extract text + coordinates"
    )
    pdf_extract.add_argument("input", help="Path to the input .pdf file")
    pdf_extract.add_argument(
        "--out", default="pdf_output", help="Output directory (default: pdf_output)"
    )

    # pdf redact
    pdf_redact = pdf_subparsers.add_parser(
        "redact", help="True redaction of target text"
    )
    pdf_redact.add_argument("input", help="Path to the input .pdf file")
    pdf_redact.add_argument(
        "spec", help="Path to the spec .json file (target_text)"
    )
    pdf_redact.add_argument(
        "--out", default="pdf_output", help="Output directory (default: pdf_output)"
    )

    # pdf fill
    pdf_fill = pdf_subparsers.add_parser("fill", help="Fill AcroForm fields")
    pdf_fill.add_argument("input", help="Path to the input .pdf file")
    pdf_fill.add_argument(
        "spec", help="Path to the spec .json file (field values)"
    )
    pdf_fill.add_argument(
        "--out", default="pdf_output", help="Output directory (default: pdf_output)"
    )

    # pdf sign
    pdf_sign = pdf_subparsers.add_parser(
        "sign", help="Apply PAdES digital signature"
    )
    pdf_sign.add_argument("input", help="Path to the input .pdf file")
    pdf_sign.add_argument(
        "--out", default="pdf_output", help="Output directory (default: pdf_output)"
    )

    # pdf verify
    pdf_verify = pdf_subparsers.add_parser(
        "verify", help="Verify digital signatures"
    )
    pdf_verify.add_argument("input", help="Path to the signed .pdf file")
    pdf_verify.add_argument(
        "--out", default="pdf_output", help="Output directory (default: pdf_output)"
    )


def _run(args: argparse.Namespace) -> int:
    if not hasattr(args, "action") or args.action is None:
        print(
            "ERROR: No PDF action specified. Use --help to see available actions.",
            file=sys.stderr,
        )
        return 1
    from kairo.cli import cmd_pdf

    return cmd_pdf(args)


DOMAIN = Domain(
    name="pdf",
    cli_name="pdf",
    status="Real",
    summary=(
        "pdf_text_roundtrip + pdf_render_diff + pdf_form_readback + "
        "pdf_signature_verify — pdfplumber coords, pikepdf true redaction "
        "(bytes removed), AcroForm fill+readback, pyHanko PAdES sign+verify, "
        "kill-proven, honest-degradation. OCR sub-capability: Experimental."
    ),
    register_cli=_register_cli,
    run=_run,
    requirements=[
        "pdfplumber>=0.11.0",
        "pypdfium2>=4.0.0",
        "pikepdf>=9.0.0",
        "pypdf>=4.0.0",
        "pyhanko>=0.20.0",
        "reportlab>=4.0.0",
    ],
)

register(DOMAIN)
