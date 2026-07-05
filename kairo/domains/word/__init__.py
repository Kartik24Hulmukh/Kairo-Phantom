# PROVENANCE: original | Word/docs domain descriptor for plugin registry
"""Word/docs domain — real .docx create/edit via python-docx, verified by read-back.

Registers the ``word`` CLI subcommand with sub-actions:
  - create: create a .docx from a spec JSON file, output doc + audit
  - inspect: read back and display the structure of a .docx file
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from kairo.domains.registry import Domain, register


def _register_cli(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "word",
        help="Create/edit Word documents via python-docx (offline, read-back verified)",
    )
    word_sub = parser.add_subparsers(dest="action", help="Word action")

    # word create
    wc = word_sub.add_parser("create", help="Create a .docx from a spec JSON file")
    wc.add_argument("spec", help="Path to the spec .json file (content blocks)")
    wc.add_argument("--out", default="word_output.docx", help="Output .docx path")
    wc.add_argument("--outdir", default="word_output", help="Output directory for artifacts")

    # word inspect
    wi = word_sub.add_parser("inspect", help="Read back and display .docx structure")
    wi.add_argument("input", help="Path to the .docx file")
    wi.add_argument("--outdir", default="word_output", help="Output directory for artifacts")


def _run(args: argparse.Namespace) -> int:
    if not hasattr(args, "action") or args.action is None:
        print("ERROR: No word action specified. Use --help.", file=sys.stderr)
        return 1

    from pathlib import Path

    out_dir = Path(args.outdir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Get or create Ed25519 keypair
    from kairo.cli import _get_or_create_keypair

    key_dir = out_dir / ".keys"
    private_key, public_key, pub_pem = _get_or_create_keypair(key_dir)
    (out_dir / "public_key.pem").write_bytes(pub_pem)

    if args.action == "create":
        from kairo.domains.word.engine import word_pipeline

        spec_path = str(Path(args.spec).resolve())
        if not os.path.exists(spec_path):
            print(f"ERROR: Spec file not found: {spec_path}", file=sys.stderr)
            return 1

        with open(spec_path, encoding="utf-8") as f:
            spec = json.load(f)

        output_docx = str(out_dir / Path(args.out).name)

        result = word_pipeline(
            spec=spec,
            output_path=output_docx,
            private_key=private_key,
            author="Kairo Word",
        )

        if not result.ok:
            print(f"ERROR: Word pipeline failed: {result.error}", file=sys.stderr)
            return 1

        # Write audit + egress
        if result.audit_log_json:
            (out_dir / "audit_log.json").write_text(result.audit_log_json, encoding="utf-8")
        if result.egress_report_json:
            (out_dir / "zero_egress_report.json").write_text(
                result.egress_report_json, encoding="utf-8"
            )

        # Print results
        print()
        print("=" * 60)
        print("  KAIRO PHANTOM — WORD PIPELINE COMPLETE")
        print("=" * 60)
        print(f"  Spec:       {Path(spec_path).name}")
        print(f"  Output:     {result.output_path}")
        print(f"  Paragraphs: {result.doc_info.paragraph_count if result.doc_info else 0}")
        print(f"  Tables:     {result.doc_info.table_count if result.doc_info else 0}")
        print()

        if result.doc_info:
            for i, para in enumerate(result.doc_info.paragraphs):
                style_info = f"style='{para.style}'"
                if para.heading_level > 0:
                    style_info += f" heading={para.heading_level}"
                if para.list_type:
                    style_info += f" list={para.list_type}"
                text_preview = para.text[:60] + "..." if len(para.text) > 60 else para.text
                print(f"  Para {i}: {style_info} text='{text_preview}'")
                for j, run in enumerate(para.runs):
                    fmt = []
                    if run.bold:
                        fmt.append("bold")
                    if run.italic:
                        fmt.append("italic")
                    fmt_str = f" [{', '.join(fmt)}]" if fmt else ""
                    run_preview = run.text[:40] + "..." if len(run.text) > 40 else run.text
                    print(f"    Run {j}: '{run_preview}'{fmt_str}")

            for i, table in enumerate(result.doc_info.tables):
                print(f"  Table {i}: {table.rows}x{table.cols}")
                for r_idx, row in enumerate(table.cells):
                    row_preview = [c[:20] for c in row]
                    print(f"    Row {r_idx}: {row_preview}")

        # Verify audit
        audit_ok = True
        if result.audit_log_json:
            from kairo.oracles.ed25519_audit_log import Ed25519AuditLog

            entries = Ed25519AuditLog.entries_from_json(result.audit_log_json)
            audit_ok = Ed25519AuditLog.verify_chain(entries, public_key)

        egress_ok = True
        if result.egress_report_json:
            from kairo.oracles.zero_egress_report import (
                report_from_json,
                verify_zero_egress_report,
            )

            report = report_from_json(result.egress_report_json)
            egress_ok = verify_zero_egress_report(report, public_key)

        print()
        print(f"  Audit log verified: {'✅' if audit_ok else '❌'}")
        print(f"  Zero-egress report verified: {'✅' if egress_ok else '❌'}")
        print("=" * 60)

        return 0 if (audit_ok and egress_ok and result.ok) else 1

    elif args.action == "inspect":
        from kairo.domains.word.engine import read_document

        input_path = str(Path(args.input).resolve())
        if not os.path.exists(input_path):
            print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
            return 1

        try:
            doc_info = read_document(input_path)
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

        print()
        print("=" * 60)
        print("  KAIRO PHANTOM — WORD DOCUMENT INSPECTION")
        print("=" * 60)
        print(f"  File:       {Path(input_path).name}")
        print(f"  Paragraphs: {doc_info.paragraph_count}")
        print(f"  Tables:     {doc_info.table_count}")
        print()

        for i, para in enumerate(doc_info.paragraphs):
            style_info = f"style='{para.style}'"
            if para.heading_level > 0:
                style_info += f" heading={para.heading_level}"
            if para.list_type:
                style_info += f" list={para.list_type}"
            text_preview = para.text[:60] + "..." if len(para.text) > 60 else para.text
            print(f"  Para {i}: {style_info} text='{text_preview}'")

        for i, table in enumerate(doc_info.tables):
            print(f"  Table {i}: {table.rows}x{table.cols}")
            for r_idx, row in enumerate(table.cells):
                row_preview = [c[:20] for c in row]
                print(f"    Row {r_idx}: {row_preview}")

        print("=" * 60)
        return 0

    return 1


DOMAIN = Domain(
    name="word",
    cli_name="word",
    status="Real",
    summary=(
        "docx_readback + structure_readback — python-docx real .docx "
        "create/edit (headings, styled paragraphs, numbered/bulleted lists, "
        "tables, bold/italic runs), read-back verified via reopen, "
        "kill-proven, honest-degradation"
    ),
    register_cli=_register_cli,
    run=_run,
    requirements=[
        "python-docx>=1.1.0",
    ],
)

register(DOMAIN)
