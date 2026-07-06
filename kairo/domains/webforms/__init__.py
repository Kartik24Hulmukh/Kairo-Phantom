# PROVENANCE: original | Web-forms/apps domain descriptor for plugin registry
"""Web-forms/apps domain — local HTML form fill, verified by DOM read-back.

Registers the ``webforms`` CLI subcommand with sub-actions:
  - fill:   fill a local HTML form from a spec JSON file
  - inspect: read back and display the structure of an HTML form
  - verify: fill + verify a form (read-back + required-field check)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from kairo.domains.registry import Domain, register


def _register_cli(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "webforms",
        help="Fill/verify web forms (local HTML) — offline, DOM read-back verified",
    )
    wf_sub = parser.add_subparsers(dest="action", help="Web-forms action")

    # webforms fill
    wf_fill = wf_sub.add_parser("fill", help="Fill a local HTML form from a spec JSON file")
    wf_fill.add_argument("html", help="Path to the source .html file")
    wf_fill.add_argument("spec", help="Path to the fill spec .json file")
    wf_fill.add_argument("--form-id", default="", help="Form ID to target (if multiple forms)")
    wf_fill.add_argument("--out", default="filled_form.html", help="Output .html path")
    wf_fill.add_argument("--outdir", default="webforms_output", help="Output directory for artifacts")

    # webforms inspect
    wf_inspect = wf_sub.add_parser("inspect", help="Read back and display HTML form structure")
    wf_inspect.add_argument("input", help="Path to the .html file")
    wf_inspect.add_argument("--form-id", default="", help="Form ID to target")
    wf_inspect.add_argument("--outdir", default="webforms_output", help="Output directory for artifacts")

    # webforms verify
    wf_verify = wf_sub.add_parser("verify", help="Fill + verify a form (read-back + required check)")
    wf_verify.add_argument("html", help="Path to the source .html file")
    wf_verify.add_argument("spec", help="Path to the fill spec .json file")
    wf_verify.add_argument("--form-id", default="", help="Form ID to target")
    wf_verify.add_argument("--outdir", default="webforms_output", help="Output directory for artifacts")


def _run(args: argparse.Namespace) -> int:
    if not hasattr(args, "action") or args.action is None:
        print("ERROR: No webforms action specified. Use --help.", file=sys.stderr)
        return 1

    out_dir = Path(args.outdir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Get or create Ed25519 keypair
    from kairo.cli import _get_or_create_keypair

    key_dir = out_dir / ".keys"
    private_key, public_key, pub_pem = _get_or_create_keypair(key_dir)
    (out_dir / "public_key.pem").write_bytes(pub_pem)

    from kairo.domains.webforms.engine import (
        WebFormsError,
        read_form,
        webforms_pipeline,
    )

    if args.action == "inspect":
        html_path = args.input
        form_id = args.form_id
        try:
            info = read_form(html_path, form_id)
        except WebFormsError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

        print()
        print("=" * 60)
        print("  KAIRO PHANTOM — WEB FORM INSPECT")
        print("=" * 60)
        print(f"  File:       {Path(html_path).name}")
        print(f"  Form ID:    {info.form_id or '(none)'}")
        print(f"  Action:     {info.form_action or '(none)'}")
        print(f"  Method:     {info.form_method}")
        print(f"  Fields:     {info.field_count}")
        print(f"  Required:   {info.required_field_count}")
        print("-" * 60)
        for i, field in enumerate(info.fields):
            req_tag = " [required]" if field.required else ""
            val_display = field.current_value[:40] if field.current_value else "(empty)"
            print(f"  [{i}] {field.tag}/{field.field_type} "
                  f"id='{field.element_id}' name='{field.name}'{req_tag}")
            print(f"       selector: {field.selector}")
            print(f"       value:    {val_display}")
            if field.options:
                print(f"       options:  {field.options}")
        print("=" * 60)
        return 0

    elif args.action == "fill":
        html_path = args.html
        spec_path = args.spec
        form_id = args.form_id
        out_path = str(out_dir / args.out)

        try:
            with open(spec_path, encoding="utf-8") as f:
                fill_spec = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"ERROR: Cannot load spec: {e}", file=sys.stderr)
            return 1

        result = webforms_pipeline(
            html_path=html_path,
            fill_spec=fill_spec,
            form_id=form_id,
            output_path=out_path,
            private_key=private_key,
        )

        if not result.ok:
            print(f"ERROR: {result.error}", file=sys.stderr)
            return 1

        print()
        print("=" * 60)
        print("  KAIRO PHANTOM — WEB FORM FILLED")
        print("=" * 60)
        print(f"  Source:       {Path(html_path).name}")
        print(f"  Output:       {result.output_path}")
        print(f"  Fields filled: {result.fields_filled}/{result.fields_total}")
        print(f"  Verified:     {result.verified}")
        print(f"  Submit blocked: {result.submit_blocked}")
        if result.required_blank:
            print(f"  Required blank: {result.required_blank}")
        print(f"  Audit log:    {len(result.audit_log_json)} bytes")
        print(f"  Egress report: {len(result.egress_report_json)} bytes")
        print("=" * 60)
        return 0

    elif args.action == "verify":
        html_path = args.html
        spec_path = args.spec
        form_id = args.form_id

        try:
            with open(spec_path, encoding="utf-8") as f:
                fill_spec = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"ERROR: Cannot load spec: {e}", file=sys.stderr)
            return 1

        result = webforms_pipeline(
            html_path=html_path,
            fill_spec=fill_spec,
            form_id=form_id,
            output_path=str(out_dir / "verified_form.html"),
            private_key=private_key,
        )

        if not result.ok:
            print(f"ERROR: {result.error}", file=sys.stderr)
            return 1

        from kairo.domains.webforms.oracles import form_fill_readback, uistate_readback

        # Build expected values from fill spec
        expected_values: dict[str, Any] = {}
        for key, spec in fill_spec.items():
            ftype = spec.get("type", "text")
            value = spec.get("value", "")
            if ftype in ("checkbox", "radio"):
                expected_values[key] = bool(value)
            else:
                expected_values[key] = str(value)

        try:
            readback_ok = form_fill_readback(
                html_path, fill_spec, expected_values, form_id
            )
        except (AssertionError, WebFormsError) as e:
            readback_ok = False
            print(f"  form_fill_readback: FAIL — {e}")

        try:
            if result.form_info:
                uistate_ok = uistate_readback(
                    html_path,
                    expected_field_count=result.form_info.field_count,
                    form_id=form_id,
                    fill_spec=fill_spec,
                )
            else:
                uistate_ok = False
        except (AssertionError, WebFormsError) as e:
            uistate_ok = False
            print(f"  uistate_readback: FAIL — {e}")

        print()
        print("=" * 60)
        print("  KAIRO PHANTOM — WEB FORM VERIFIED")
        print("=" * 60)
        print(f"  Source:          {Path(html_path).name}")
        print(f"  Fields filled:   {result.fields_filled}/{result.fields_total}")
        print(f"  form_fill_readback: {'PASS' if readback_ok else 'FAIL'}")
        print(f"  uistate_readback:   {'PASS' if uistate_ok else 'FAIL'}")
        print(f"  CUA verified:    {result.verified}")
        print(f"  Submit blocked:  {result.submit_blocked}")
        if result.required_blank:
            print(f"  Required blank:  {result.required_blank}")
        print(f"  Audit log:       {len(result.audit_log_json)} bytes")
        print(f"  Egress report:   {len(result.egress_report_json)} bytes")
        print("=" * 60)
        return 0 if (readback_ok and uistate_ok and result.verified) else 1

    return 1


DOMAIN = Domain(
    name="webforms",
    cli_name="webforms",
    status="Real",
    summary=(
        "form_fill_readback + uistate_readback — local HTML form fill "
        "(text, email, password, select, checkbox, radio, textarea), "
        "read-back verified via DOM re-parse, kill-proven, honest-degradation; "
        "live browser/page-agent = Experimental"
    ),
    register_cli=_register_cli,
    run=_run,
    requirements=[
        "beautifulsoup4>=4.12",
        "lxml>=5.1",
    ],
)

register(DOMAIN)
