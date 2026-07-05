# PROVENANCE: original | data/analytics domain descriptor for plugin registry
"""Data/analytics domain — SQL queries over local data files via DuckDB.

Registers the ``data`` CLI subcommand with sub-actions:
  - query: run a SQL query over a loaded file, output results + audit
  - schema: show table schema after loading a file
"""

from __future__ import annotations

import argparse
import os
import sys

from kairo.domains.registry import Domain, register


def _register_cli(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "data",
        help="Query and analyze local data files (CSV/Parquet/xlsx) via DuckDB",
    )
    data_sub = parser.add_subparsers(dest="action", help="Data action")

    # data query
    dq = data_sub.add_parser("query", help="Run a SQL query over a data file")
    dq.add_argument("input", help="Path to the data file (.csv, .parquet, .xlsx)")
    dq.add_argument("sql", help="SQL query to execute")
    dq.add_argument("--out", default="data_output", help="Output directory (default: data_output)")

    # data schema
    ds = data_sub.add_parser("schema", help="Show table schema after loading a file")
    ds.add_argument("input", help="Path to the data file")
    ds.add_argument("--out", default="data_output", help="Output directory (default: data_output)")


def _run(args: argparse.Namespace) -> int:
    if not hasattr(args, "action") or args.action is None:
        print("ERROR: No data action specified. Use --help.", file=sys.stderr)
        return 1

    from pathlib import Path

    input_path = str(Path(args.input).resolve())
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not os.path.exists(input_path):
        print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
        return 1

    # Get or create Ed25519 keypair
    from kairo.cli import _get_or_create_keypair

    key_dir = out_dir / ".keys"
    private_key, public_key, pub_pem = _get_or_create_keypair(key_dir)
    (out_dir / "public_key.pem").write_bytes(pub_pem)

    if args.action == "query":
        from kairo.domains.data_analytics.engine import data_analytics_pipeline

        result = data_analytics_pipeline(
            input_files=[input_path],
            sql_queries=[args.sql],
            private_key=private_key,
            author="Kairo Data",
        )

        if not result.ok:
            print(f"ERROR: Data pipeline failed: {result.error}", file=sys.stderr)
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
        print("  KAIRO PHANTOM — DATA/ANALYTICS PIPELINE COMPLETE")
        print("=" * 60)
        print(f"  Input:  {Path(input_path).name}")
        print(f"  Query:  {args.sql}")
        print(f"  Output: {out_dir}")
        print()

        for i, qr in enumerate(result.query_results):
            print(f"  Query {i}: {qr.row_count} rows, {len(qr.columns)} columns")
            if qr.columns:
                print(f"    Columns: {qr.columns}")
                for row in qr.rows[:10]:
                    print(f"    {row}")
                if qr.row_count > 10:
                    print(f"    ... ({qr.row_count - 10} more rows)")

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

    elif args.action == "schema":
        from kairo.domains.data_analytics.engine import connect, load_file

        try:
            conn = connect()
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

        try:
            si = load_file(conn, input_path, "data")
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

        print()
        print("=" * 60)
        print("  KAIRO PHANTOM — DATA SCHEMA")
        print("=" * 60)
        print(f"  File:  {Path(input_path).name}")
        print(f"  Table: {si.table_name}")
        print(f"  Rows:  {si.row_count}")
        print()
        print("  Columns:")
        for col_name, col_type in si.columns:
            print(f"    {col_name}: {col_type}")
        print("=" * 60)
        conn.close()
        return 0

    return 1


DOMAIN = Domain(
    name="data_analytics",
    cli_name="data",
    status="Real",
    summary=(
        "query_result + schema_readback — DuckDB SQL over local CSV/Parquet/xlsx, "
        "results verified vs independent pandas/numpy calc, kill-proven, "
        "honest-degradation"
    ),
    register_cli=_register_cli,
    run=_run,
    requirements=[
        "duckdb>=1.0.0",
        "pandas>=2.0.0",
        "numpy>=1.24.0",
        "pyarrow>=15.0.0",
    ],
)

register(DOMAIN)
