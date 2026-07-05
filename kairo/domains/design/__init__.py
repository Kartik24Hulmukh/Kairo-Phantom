# PROVENANCE: original | Design/media domain descriptor for plugin registry
"""Design/media domain — SVG canvas create/edit, verified by read-back.

Registers the ``design`` CLI subcommand with sub-actions:
  - create: create an SVG canvas from a spec JSON file
  - inspect: read back and display the structure of an SVG canvas
  - edit: apply edits to an existing SVG canvas
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from kairo.domains.registry import Domain, register


def _register_cli(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "design",
        help="Create/edit SVG canvas (shapes, text, layout) — offline, read-back verified",
    )
    design_sub = parser.add_subparsers(dest="action", help="Design action")

    # design create
    dc = design_sub.add_parser("create", help="Create an SVG canvas from a spec JSON file")
    dc.add_argument("spec", help="Path to the spec .json file")
    dc.add_argument("--out", default="canvas_output.svg", help="Output .svg path")
    dc.add_argument("--outdir", default="design_output", help="Output directory for artifacts")

    # design inspect
    di = design_sub.add_parser("inspect", help="Read back and display SVG canvas structure")
    di.add_argument("input", help="Path to the .svg file")
    di.add_argument("--outdir", default="design_output", help="Output directory for artifacts")

    # design edit
    de = design_sub.add_parser("edit", help="Apply edits to an existing SVG canvas")
    de.add_argument("input", help="Path to the existing .svg file")
    de.add_argument("edits", help="Path to the edits .json file")
    de.add_argument("--out", default="edited_canvas.svg", help="Output .svg path")
    de.add_argument("--outdir", default="design_output", help="Output directory for artifacts")


def _run(args: argparse.Namespace) -> int:
    if not hasattr(args, "action") or args.action is None:
        print("ERROR: No design action specified. Use --help.", file=sys.stderr)
        return 1

    out_dir = Path(args.outdir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Get or create Ed25519 keypair
    from kairo.cli import _get_or_create_keypair

    key_dir = out_dir / ".keys"
    private_key, public_key, pub_pem = _get_or_create_keypair(key_dir)
    (out_dir / "public_key.pem").write_bytes(pub_pem)

    if args.action == "create":
        from kairo.domains.design.engine import design_pipeline

        spec_path = str(Path(args.spec).resolve())
        if not os.path.exists(spec_path):
            print(f"ERROR: Spec file not found: {spec_path}", file=sys.stderr)
            return 1

        with open(spec_path, encoding="utf-8") as f:
            spec = json.load(f)

        output_svg = str(out_dir / Path(args.out).name)

        result = design_pipeline(
            spec=spec,
            output_path=output_svg,
            private_key=private_key,
            author="Kairo Design",
        )

        if not result.ok:
            print(f"ERROR: Design pipeline failed: {result.error}", file=sys.stderr)
            return 1

        # Write audit + egress
        if result.audit_log_json:
            (out_dir / "audit_log.json").write_text(result.audit_log_json, encoding="utf-8")
        if result.egress_report_json:
            (out_dir / "zero_egress_report.json").write_text(
                result.egress_report_json, encoding="utf-8"
            )

        print()
        print("=" * 60)
        print("  KAIRO PHANTOM — DESIGN PIPELINE COMPLETE")
        print("=" * 60)
        print(f"  Spec:     {Path(spec_path).name}")
        print(f"  Output:   {result.output_path}")
        print(f"  Elements: {result.canvas_info.element_count if result.canvas_info else 0}")
        print(f"  Canvas:   {result.canvas_info.width}x{result.canvas_info.height}" if result.canvas_info else "")
        print()

        if result.canvas_info:
            for i, elem in enumerate(result.canvas_info.elements):
                print(f"  Element {i}: type='{elem.element_type}' id='{elem.element_id}' z={elem.z_order}")
                for k, v in elem.attributes.items():
                    print(f"    {k}={v}")
                if elem.text_content:
                    print(f"    text='{elem.text_content}'")

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
        from kairo.domains.design.engine import read_canvas

        input_path = str(Path(args.input).resolve())
        if not os.path.exists(input_path):
            print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
            return 1

        try:
            canvas_info = read_canvas(input_path)
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

        print()
        print("=" * 60)
        print("  KAIRO PHANTOM — SVG CANVAS INSPECTION")
        print("=" * 60)
        print(f"  File:     {Path(input_path).name}")
        print(f"  Canvas:   {canvas_info.width}x{canvas_info.height}")
        print(f"  Elements: {canvas_info.element_count}")
        print()

        for i, elem in enumerate(canvas_info.elements):
            print(f"  Element {i}: type='{elem.element_type}' id='{elem.element_id}' z={elem.z_order}")
            for k, v in elem.attributes.items():
                print(f"    {k}={v}")
            if elem.text_content:
                print(f"    text='{elem.text_content}'")

        print("=" * 60)
        return 0

    elif args.action == "edit":
        from kairo.domains.design.engine import edit_canvas, save_canvas, read_canvas

        input_path = str(Path(args.input).resolve())
        edits_path = str(Path(args.edits).resolve())

        if not os.path.exists(input_path):
            print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
            return 1
        if not os.path.exists(edits_path):
            print(f"ERROR: Edits file not found: {edits_path}", file=sys.stderr)
            return 1

        with open(edits_path, encoding="utf-8") as f:
            edits = json.load(f)

        try:
            svg_content = edit_canvas(input_path, edits)
            output_svg = str(out_dir / Path(args.out).name)
            saved_path = save_canvas(svg_content, output_svg)
            canvas_info = read_canvas(saved_path)
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

        print()
        print("=" * 60)
        print("  KAIRO PHANTOM — SVG CANVAS EDITED")
        print("=" * 60)
        print(f"  Input:    {Path(input_path).name}")
        print(f"  Output:   {saved_path}")
        print(f"  Elements: {canvas_info.element_count}")
        print("=" * 60)
        return 0

    return 1


DOMAIN = Domain(
    name="design",
    cli_name="design",
    status="Real",
    summary=(
        "canvas_readback + structure_readback — SVG canvas create/edit "
        "(shapes, text, positions, z-order), read-back verified via re-parse, "
        "kill-proven, honest-degradation; live Figma/vision = Experimental"
    ),
    register_cli=_register_cli,
    run=_run,
    requirements=[
        "# pure-stdlib — uses xml.etree.ElementTree (no external dependencies required)",
    ],
)

register(DOMAIN)
