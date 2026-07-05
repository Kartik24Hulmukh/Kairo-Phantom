# PROVENANCE: original | Code domain descriptor for plugin registry
"""Code domain — real parse/compile/test verification via tree-sitter + py_compile + pytest.

Registers the ``code`` CLI subcommand with sub-actions:
  - verify: run parse + compile + test on a project directory
  - edit: apply a text replacement edit, then verify
  - parse: check tree-sitter parse validity of a single file
"""

from __future__ import annotations

import argparse
import os
import sys

from kairo.domains.registry import Domain, register


def _register_cli(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "code",
        help="Verify code parses, compiles, and passes tests (offline, tree-sitter + pytest)",
    )
    code_sub = parser.add_subparsers(dest="action", help="Code action")

    # code verify
    cv = code_sub.add_parser("verify", help="Run parse + compile + test on a project directory")
    cv.add_argument("project", help="Path to the project directory")
    cv.add_argument("--outdir", default="code_output", help="Output directory for artifacts")

    # code edit
    ce = code_sub.add_parser("edit", help="Apply a text replacement edit, then verify")
    ce.add_argument("project", help="Path to the project directory")
    ce.add_argument("file", help="Path to the file to edit (relative to project or absolute)")
    ce.add_argument("--old", required=True, help="Exact text to find (must be unique)")
    ce.add_argument("--new", required=True, help="Replacement text")
    ce.add_argument("--outdir", default="code_output", help="Output directory for artifacts")

    # code parse
    cp = code_sub.add_parser("parse", help="Check tree-sitter parse validity of a single file")
    cp.add_argument("file", help="Path to the .py file")
    cp.add_argument("--outdir", default="code_output", help="Output directory for artifacts")


def _run(args: argparse.Namespace) -> int:
    if not hasattr(args, "action") or args.action is None:
        print("ERROR: No code action specified. Use --help.", file=sys.stderr)
        return 1

    from pathlib import Path

    out_dir = Path(args.outdir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Get or create Ed25519 keypair
    from kairo.cli import _get_or_create_keypair

    key_dir = out_dir / ".keys"
    private_key, public_key, pub_pem = _get_or_create_keypair(key_dir)
    (out_dir / "public_key.pem").write_bytes(pub_pem)

    if args.action == "verify":
        from kairo.domains.code.engine import code_pipeline

        project_path = str(Path(args.project).resolve())
        if not os.path.exists(project_path):
            print(f"ERROR: Project directory not found: {project_path}", file=sys.stderr)
            return 1

        result = code_pipeline(
            project_dir=project_path,
            private_key=private_key,
            author="Kairo Code",
        )

        # Write audit + egress
        if result.audit_log_json:
            (out_dir / "audit_log.json").write_text(result.audit_log_json, encoding="utf-8")
        if result.egress_report_json:
            (out_dir / "zero_egress_report.json").write_text(
                result.egress_report_json, encoding="utf-8"
            )

        _print_result(result, out_dir)

        # Verify audit
        audit_ok, egress_ok = _verify_trust(result, public_key)

        print(f"  Audit log verified: {'✅' if audit_ok else '❌'}")
        print(f"  Zero-egress report verified: {'✅' if egress_ok else '❌'}")
        print("=" * 60)

        return 0 if (result.ok and audit_ok and egress_ok) else 1

    elif args.action == "edit":
        from kairo.domains.code.engine import apply_edit, code_pipeline

        project_path = str(Path(args.project).resolve())
        file_path = args.file
        if not os.path.isabs(file_path):
            file_path = str(Path(project_path) / file_path)

        if not os.path.exists(file_path):
            print(f"ERROR: File not found: {file_path}", file=sys.stderr)
            return 1

        try:
            apply_edit(file_path, args.old, args.new)
        except Exception as e:
            print(f"ERROR: Edit failed: {e}", file=sys.stderr)
            return 1

        result = code_pipeline(
            project_dir=project_path,
            private_key=private_key,
            author="Kairo Code",
        )

        if result.audit_log_json:
            (out_dir / "audit_log.json").write_text(result.audit_log_json, encoding="utf-8")
        if result.egress_report_json:
            (out_dir / "zero_egress_report.json").write_text(
                result.egress_report_json, encoding="utf-8"
            )

        _print_result(result, out_dir)

        audit_ok, egress_ok = _verify_trust(result, public_key)

        print(f"  Audit log verified: {'✅' if audit_ok else '❌'}")
        print(f"  Zero-egress report verified: {'✅' if egress_ok else '❌'}")
        print("=" * 60)

        return 0 if (result.ok and audit_ok and egress_ok) else 1

    elif args.action == "parse":
        from kairo.domains.code.oracles import parse_validity

        file_path = str(Path(args.file).resolve())
        if not os.path.exists(file_path):
            print(f"ERROR: File not found: {file_path}", file=sys.stderr)
            return 1

        try:
            passed = parse_validity(file_path)
            print()
            print("=" * 60)
            print("  KAIRO PHANTOM — CODE PARSE VALIDITY")
            print("=" * 60)
            print(f"  File: {Path(file_path).name}")
            print(f"  Parse valid: {'✅' if passed else '❌'}")
            print("=" * 60)
            return 0 if passed else 1
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

    return 1


def _print_result(result, out_dir):
    """Print the code pipeline result."""
    from pathlib import Path

    print()
    print("=" * 60)
    print("  KAIRO PHANTOM — CODE PIPELINE COMPLETE")
    print("=" * 60)
    print(f"  Output: {out_dir}")
    print(f"  Overall: {'✅ PASS' if result.ok else '❌ FAIL'}")
    print()

    if result.parse_results:
        print(f"  Parse results ({len(result.parse_results)} files):")
        for pr in result.parse_results:
            status = "✅" if not pr.has_errors else "❌"
            print(f"    {status} {Path(pr.file_path).name}: {pr.error_count} errors")

    if result.compile_results:
        print(f"  Compile results ({len(result.compile_results)} files):")
        for cr in result.compile_results:
            status = "✅" if cr.success else "❌"
            print(f"    {status} {Path(cr.file_path).name}")

    if result.test_result:
        tr = result.test_result
        print(f"  Test results: {tr.passed} passed, {tr.failed} failed, {tr.errors} errors")
        print(f"    Exit code: {tr.exit_code}")

    if result.error:
        print(f"  Error: {result.error}")
    print()


def _verify_trust(result, public_key):
    """Verify audit log and egress report."""
    audit_ok = True
    egress_ok = True

    if result.audit_log_json:
        from kairo.oracles.ed25519_audit_log import Ed25519AuditLog

        entries = Ed25519AuditLog.entries_from_json(result.audit_log_json)
        audit_ok = Ed25519AuditLog.verify_chain(entries, public_key)

    if result.egress_report_json:
        from kairo.oracles.zero_egress_report import (
            report_from_json,
            verify_zero_egress_report,
        )

        report = report_from_json(result.egress_report_json)
        egress_ok = verify_zero_egress_report(report, public_key)

    return audit_ok, egress_ok


DOMAIN = Domain(
    name="code",
    cli_name="code",
    status="Real",
    summary=(
        "compile_test_pass + parse_validity — tree-sitter parse (zero ERROR nodes) "
        "+ py_compile + pytest on self-contained Python project, kill-proven, "
        "honest-degradation. Python = Real; other languages = Experimental."
    ),
    register_cli=_register_cli,
    run=_run,
    requirements=[
        "tree-sitter>=0.25.0",
        "tree-sitter-python>=0.25.0",
    ],
)

register(DOMAIN)
