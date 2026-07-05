# PROVENANCE: original | PowerPoint domain descriptor for plugin registry
"""PowerPoint domain — real .pptx create/edit via python-pptx, verified by read-back.

Registers the ``pptx`` CLI subcommand with sub-actions:
  - create: create a .pptx from a spec JSON file, output deck + audit
  - inspect: read back and display the structure of a .pptx file
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from kairo.domains.registry import Domain, register


def _register_cli(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "pptx",
        help="Create/modify PowerPoint decks via python-pptx (offline, read-back verified)",
    )
    pptx_sub = parser.add_subparsers(dest="action", help="PowerPoint action")

    # pptx create
    pc = pptx_sub.add_parser("create", help="Create a .pptx from a spec JSON file")
    pc.add_argument("spec", help="Path to the spec .json file (slides + shapes)")
    pc.add_argument("--out", default="pptx_output.pptx", help="Output .pptx path")
    pc.add_argument("--outdir", default="pptx_output", help="Output directory for artifacts")

    # pptx inspect
    pi = pptx_sub.add_parser("inspect", help="Read back and display .pptx structure")
    pi.add_argument("input", help="Path to the .pptx file")
    pi.add_argument("--outdir", default="pptx_output", help="Output directory for artifacts")


def _run(args: argparse.Namespace) -> int:
    if not hasattr(args, "action") or args.action is None:
        print("ERROR: No pptx action specified. Use --help.", file=sys.stderr)
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
        from kairo.domains.powerpoint.engine import powerpoint_pipeline

        spec_path = str(Path(args.spec).resolve())
        if not os.path.exists(spec_path):
            print(f"ERROR: Spec file not found: {spec_path}", file=sys.stderr)
            return 1

        with open(spec_path, encoding="utf-8") as f:
            spec = json.load(f)

        output_pptx = str(out_dir / Path(args.out).name)

        result = powerpoint_pipeline(
            spec=spec,
            output_path=output_pptx,
            private_key=private_key,
            author="Kairo PowerPoint",
        )

        if not result.ok:
            print(f"ERROR: PowerPoint pipeline failed: {result.error}", file=sys.stderr)
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
        print("  KAIRO PHANTOM — POWERPOINT PIPELINE COMPLETE")
        print("=" * 60)
        print(f"  Spec:   {Path(spec_path).name}")
        print(f"  Output: {result.output_path}")
        print(f"  Slides: {result.deck_info.slide_count if result.deck_info else 0}")
        print()

        if result.deck_info:
            for slide in result.deck_info.slides:
                print(
                    f"  Slide {slide.slide_index}: layout='{slide.layout_name}', "
                    f"{len(slide.shapes)} shapes"
                )
                for shape in slide.shapes:
                    extra = ""
                    if shape.table_rows > 0:
                        extra = f" table={shape.table_rows}x{shape.table_cols}"
                    text_preview = (
                        shape.text[:50] + "..." if len(shape.text) > 50 else shape.text
                    )
                    print(
                        f"    {shape.name}: type={shape.shape_type}{extra} "
                        f"text='{text_preview}'"
                    )

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
        from kairo.domains.powerpoint.engine import read_deck

        input_path = str(Path(args.input).resolve())
        if not os.path.exists(input_path):
            print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
            return 1

        try:
            deck_info = read_deck(input_path)
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

        print()
        print("=" * 60)
        print("  KAIRO PHANTOM — POWERPOINT DECK INSPECTION")
        print("=" * 60)
        print(f"  File:   {Path(input_path).name}")
        print(f"  Slides: {deck_info.slide_count}")
        print()

        for slide in deck_info.slides:
            print(
                f"  Slide {slide.slide_index}: layout='{slide.layout_name}', "
                f"{len(slide.shapes)} shapes"
            )
            for shape in slide.shapes:
                extra = ""
                if shape.table_rows > 0:
                    extra = f" table={shape.table_rows}x{shape.table_cols}"
                text_preview = (
                    shape.text[:50] + "..." if len(shape.text) > 50 else shape.text
                )
                print(
                    f"    {shape.name}: type={shape.shape_type}{extra} "
                    f"text='{text_preview}'"
                )
        print("=" * 60)
        return 0

    return 1


DOMAIN = Domain(
    name="powerpoint",
    cli_name="pptx",
    status="Real",
    summary=(
        "slide_shape_readback + structure_readback — python-pptx real .pptx "
        "create/edit (slides, text, bullets, tables, images, shapes), "
        "read-back verified via reopen, kill-proven, honest-degradation"
    ),
    register_cli=_register_cli,
    run=_run,
    requirements=[
        "python-pptx>=1.0.0",
    ],
)

register(DOMAIN)
