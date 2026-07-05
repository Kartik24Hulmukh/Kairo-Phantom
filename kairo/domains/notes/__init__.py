# PROVENANCE: original | Research/notes domain descriptor for plugin registry
"""Research/notes domain — real markdown vault with [[wikilinks]] + backlinks.

Registers the ``notes`` CLI subcommand with sub-actions:
  - verify: parse vault, check backlink integrity, output graph + audit
  - graph: display the vault document graph (notes + links)
  - create: create a new note in the vault
  - rename: rename a note and update all referencing wikilinks
"""

from __future__ import annotations

import argparse
import os
import sys

from kairo.domains.registry import Domain, register


def _register_cli(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "notes",
        help="Manage markdown vault: [[wikilinks]], backlinks, graph integrity (offline)",
    )
    notes_sub = parser.add_subparsers(dest="action", help="Notes action")

    # notes verify
    nv = notes_sub.add_parser("verify", help="Check backlink integrity of a vault")
    nv.add_argument("vault", help="Path to the vault directory")
    nv.add_argument("--outdir", default="notes_output", help="Output directory for artifacts")

    # notes graph
    ng = notes_sub.add_parser("graph", help="Display the vault document graph")
    ng.add_argument("vault", help="Path to the vault directory")
    ng.add_argument("--outdir", default="notes_output", help="Output directory for artifacts")

    # notes create
    nc = notes_sub.add_parser("create", help="Create a new note in the vault")
    nc.add_argument("vault", help="Path to the vault directory")
    nc.add_argument("name", help="Note name (without .md)")
    nc.add_argument("--content", default="", help="Note content (markdown)")
    nc.add_argument("--outdir", default="notes_output", help="Output directory for artifacts")

    # notes rename
    nr = notes_sub.add_parser("rename", help="Rename a note and update all wikilinks")
    nr.add_argument("vault", help="Path to the vault directory")
    nr.add_argument("old_name", help="Current note name (without .md)")
    nr.add_argument("new_name", help="New note name (without .md)")
    nr.add_argument("--outdir", default="notes_output", help="Output directory for artifacts")


def _run(args: argparse.Namespace) -> int:
    if not hasattr(args, "action") or args.action is None:
        print("ERROR: No notes action specified. Use --help.", file=sys.stderr)
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
        from kairo.domains.notes.engine import notes_pipeline

        vault_path = str(Path(args.vault).resolve())
        if not os.path.exists(vault_path):
            print(f"ERROR: Vault not found: {vault_path}", file=sys.stderr)
            return 1

        result = notes_pipeline(
            vault_path=vault_path,
            private_key=private_key,
            author="Kairo Notes",
        )

        # Write audit + egress
        if result.audit_log_json:
            (out_dir / "audit_log.json").write_text(result.audit_log_json, encoding="utf-8")
        if result.egress_report_json:
            (out_dir / "zero_egress_report.json").write_text(
                result.egress_report_json, encoding="utf-8"
            )

        _print_graph(result, out_dir)

        # Verify audit
        audit_ok, egress_ok = _verify_trust(result, public_key)

        print(f"  Audit log verified: {'✅' if audit_ok else '❌'}")
        print(f"  Zero-egress report verified: {'✅' if egress_ok else '❌'}")
        print("=" * 60)

        return 0 if (result.ok and audit_ok and egress_ok) else 1

    elif args.action == "graph":
        from kairo.domains.notes.engine import parse_vault

        vault_path = str(Path(args.vault).resolve())
        try:
            graph = parse_vault(vault_path)
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

        print()
        print("=" * 60)
        print("  KAIRO PHANTOM — VAULT DOCUMENT GRAPH")
        print("=" * 60)
        print(f"  Vault: {Path(vault_path).name}")
        print(f"  Notes: {graph.note_count}")
        print(f"  Edges: {graph.edge_count}")
        print()

        for name in sorted(graph.notes.keys()):
            note = graph.notes[name]
            print(f"  📄 {name}")
            if note.forward_links:
                print(f"     → links to: {note.forward_links}")
            if note.backlinks:
                print(f"     ← backlinks from: {note.backlinks}")

        dangling = graph.get_dangling_links()
        if dangling:
            print(f"\n  ⚠️  Dangling links: {len(dangling)}")
            for s, t in dangling:
                print(f"     {s} → {t} (missing)")

        print("=" * 60)
        return 0 if not dangling else 1

    elif args.action == "create":
        from kairo.domains.notes.engine import create_note, notes_pipeline

        vault_path = str(Path(args.vault).resolve())
        try:
            create_note(vault_path, args.name, args.content)
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

        result = notes_pipeline(
            vault_path=vault_path,
            private_key=private_key,
            author="Kairo Notes",
        )

        if result.audit_log_json:
            (out_dir / "audit_log.json").write_text(result.audit_log_json, encoding="utf-8")
        if result.egress_report_json:
            (out_dir / "zero_egress_report.json").write_text(
                result.egress_report_json, encoding="utf-8"
            )

        _print_graph(result, out_dir)
        audit_ok, egress_ok = _verify_trust(result, public_key)
        print(f"  Audit log verified: {'✅' if audit_ok else '❌'}")
        print(f"  Zero-egress report verified: {'✅' if egress_ok else '❌'}")
        print("=" * 60)
        return 0 if (result.ok and audit_ok and egress_ok) else 1

    elif args.action == "rename":
        from kairo.domains.notes.engine import notes_pipeline, rename_note

        vault_path = str(Path(args.vault).resolve())
        try:
            rename_note(vault_path, args.old_name, args.new_name)
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

        result = notes_pipeline(
            vault_path=vault_path,
            private_key=private_key,
            author="Kairo Notes",
        )

        if result.audit_log_json:
            (out_dir / "audit_log.json").write_text(result.audit_log_json, encoding="utf-8")
        if result.egress_report_json:
            (out_dir / "zero_egress_report.json").write_text(
                result.egress_report_json, encoding="utf-8"
            )

        _print_graph(result, out_dir)
        audit_ok, egress_ok = _verify_trust(result, public_key)
        print(f"  Audit log verified: {'✅' if audit_ok else '❌'}")
        print(f"  Zero-egress report verified: {'✅' if egress_ok else '❌'}")
        print("=" * 60)
        return 0 if (result.ok and audit_ok and egress_ok) else 1

    return 1


def _print_graph(result, out_dir):
    """Print the notes pipeline result."""
    print()
    print("=" * 60)
    print("  KAIRO PHANTOM — NOTES PIPELINE COMPLETE")
    print("=" * 60)
    print(f"  Output: {out_dir}")
    print(f"  Overall: {'✅ PASS' if result.ok else '❌ FAIL'}")
    print()

    if result.vault_graph:
        graph = result.vault_graph
        print(f"  Notes: {graph.note_count}")
        print(f"  Edges: {graph.edge_count}")

        dangling = graph.get_dangling_links()
        if dangling:
            print(f"  ⚠️  Dangling links: {len(dangling)}")
            for s, t in dangling[:5]:
                print(f"    {s} → {t} (missing)")
        else:
            print("  ✅ No dangling links — backlink integrity OK")

        print()
        print("  Notes:")
        for name in sorted(graph.notes.keys()):
            note = graph.notes[name]
            links_str = ", ".join(note.forward_links) if note.forward_links else "(none)"
            back_str = ", ".join(note.backlinks) if note.backlinks else "(none)"
            print(f"    📄 {name}: → [{links_str}] ← [{back_str}]")

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
    name="notes",
    cli_name="notes",
    status="Real",
    summary=(
        "backlink_integrity + graph_readback — pure-Python markdown vault "
        "with [[wikilinks]], bidirectional backlinks, document graph, "
        "create/edit/rename with link rewriting, kill-proven, honest-degradation"
    ),
    register_cli=_register_cli,
    run=_run,
    requirements=[],
)

register(DOMAIN)
