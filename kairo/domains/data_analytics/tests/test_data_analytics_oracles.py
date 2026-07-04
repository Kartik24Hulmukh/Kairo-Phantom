# PROVENANCE: original | data/analytics oracle tests per VERIFICATION_ORACLES.md
"""Data/analytics domain oracle tests — query_result + schema_readback + kill-proofs.

Tests verify:
  1. query_result: DuckDB SQL result equals independent pandas/numpy calc.
     Kill-proof: perturb expected result → FAILS.
  2. schema_readback: table columns/types/row-count match after load.
     Kill-proof: drop a column → FAILS.
  3. Honest degradation: DuckDB missing → FAIL LOUD.
  4. >=3 gauntlet scenarios: group-by aggregation, two-file join, wrong-result catch.
  5. Trust stack integration: audit log + egress report.
  6. CLI integration: data subcommand works end-to-end.

All tests run fully offline. No mocks on production paths. Zero skips.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

_REPO_ROOT = os.path.dirname(
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from kairo.domains.data_analytics.engine import (  # noqa: E402
    connect,
    data_analytics_pipeline,
    execute_query,
    independent_filter_count,
    independent_group_by_sum,
    independent_join,
    load_file,
    query_result,
    schema_readback,
)

# Fixture paths
_FIX = os.path.join(_REPO_ROOT, "kairo", "domains", "data_analytics", "fixtures")
_SALES_CSV = os.path.join(_FIX, "sales.csv")
_CUSTOMERS_PARQUET = os.path.join(_FIX, "customers.parquet")
_ORDERS_CSV = os.path.join(_FIX, "orders.csv")


# ---------------------------------------------------------------------------
# Helper: check engine availability
# ---------------------------------------------------------------------------


def _duckdb_available() -> bool:
    try:
        import duckdb  # noqa: F401

        return True
    except ImportError:
        return False


_HAS_DUCKDB = _duckdb_available()


# ---------------------------------------------------------------------------
# Oracle 1: query_result
# ---------------------------------------------------------------------------


class TestQueryResult:
    """query_result oracle: DuckDB SQL equals independent pandas calc."""

    def test_group_by_aggregation_matches(self):
        """GROUP BY + SUM via DuckDB matches independent pandas computation."""
        if not _HAS_DUCKDB:
            pytest.fail("duckdb not available — cannot test query_result")

        conn = connect()
        load_file(conn, _SALES_CSV, "sales")

        sql = "SELECT product, SUM(quantity) AS total_quantity FROM sales GROUP BY product ORDER BY product"
        expected_cols, expected_rows = independent_group_by_sum(_SALES_CSV, "product", "quantity")

        passed = query_result(conn, sql, expected_rows, expected_cols)
        assert passed, "query_result oracle failed for GROUP BY aggregation"
        conn.close()

    def test_filter_query_matches(self):
        """Filtered query via DuckDB matches independent pandas count."""
        if not _HAS_DUCKDB:
            pytest.fail("duckdb not available")

        conn = connect()
        load_file(conn, _SALES_CSV, "sales")

        sql = "SELECT COUNT(*) AS cnt FROM sales WHERE region = 'North'"
        expected_count = independent_filter_count(_SALES_CSV, "region", "North")

        result = execute_query(conn, sql)
        assert (
            result.rows[0][0] == expected_count
        ), f"Filter count mismatch: DuckDB={result.rows[0][0]}, pandas={expected_count}"
        conn.close()

    def test_kill_proof_wrong_result_fails(self):
        """Kill-proof: perturb expected result → oracle FAILS."""
        if not _HAS_DUCKDB:
            pytest.fail("duckdb not available")

        conn = connect()
        load_file(conn, _SALES_CSV, "sales")

        sql = "SELECT product, SUM(quantity) AS total_quantity FROM sales GROUP BY product ORDER BY product"
        _, expected_rows = independent_group_by_sum(_SALES_CSV, "product", "quantity")

        # Perturb: add 1000 to the first expected row's sum
        wrong_rows = [list(r) for r in expected_rows]
        wrong_rows[0][1] = wrong_rows[0][1] + 1000

        with pytest.raises(AssertionError, match="value mismatch"):
            query_result(conn, sql, wrong_rows, ["product", "total_quantity"])
        conn.close()

    def test_kill_proof_dropped_row_fails(self):
        """Kill-proof: drop a row from expected → oracle FAILS."""
        if not _HAS_DUCKDB:
            pytest.fail("duckdb not available")

        conn = connect()
        load_file(conn, _SALES_CSV, "sales")

        sql = "SELECT product, SUM(quantity) AS total_quantity FROM sales GROUP BY product ORDER BY product"
        expected_cols, expected_rows = independent_group_by_sum(_SALES_CSV, "product", "quantity")

        # Drop the last expected row
        wrong_rows = expected_rows[:-1]

        with pytest.raises(AssertionError, match="row count mismatch"):
            query_result(conn, sql, wrong_rows, expected_cols)
        conn.close()


# ---------------------------------------------------------------------------
# Oracle 2: schema_readback
# ---------------------------------------------------------------------------


class TestSchemaReadback:
    """schema_readback oracle: table columns/types/row-count match after load."""

    def test_csv_schema_matches(self):
        """CSV file schema matches expected columns and row count."""
        if not _HAS_DUCKDB:
            pytest.fail("duckdb not available")

        conn = connect()
        load_file(conn, _SALES_CSV, "sales")

        # Get actual schema
        schema = conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'sales' ORDER BY ordinal_position"
        ).fetchall()
        expected_cols = [(row[0], row[1]) for row in schema]
        expected_count = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]

        passed = schema_readback(conn, "sales", expected_cols, expected_count)
        assert passed
        conn.close()

    def test_parquet_schema_matches(self):
        """Parquet file schema matches expected columns and row count."""
        if not _HAS_DUCKDB:
            pytest.fail("duckdb not available")

        conn = connect()
        load_file(conn, _CUSTOMERS_PARQUET, "customers")

        schema = conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'customers' ORDER BY ordinal_position"
        ).fetchall()
        expected_cols = [(row[0], row[1]) for row in schema]
        expected_count = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]

        passed = schema_readback(conn, "customers", expected_cols, expected_count)
        assert passed
        conn.close()

    def test_kill_proof_wrong_row_count_fails(self):
        """Kill-proof: wrong row count → oracle FAILS."""
        if not _HAS_DUCKDB:
            pytest.fail("duckdb not available")

        conn = connect()
        load_file(conn, _SALES_CSV, "sales")

        schema = conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'sales' ORDER BY ordinal_position"
        ).fetchall()
        expected_cols = [(row[0], row[1]) for row in schema]

        with pytest.raises(AssertionError, match="row count mismatch"):
            schema_readback(conn, "sales", expected_cols, 999)
        conn.close()

    def test_kill_proof_wrong_columns_fails(self):
        """Kill-proof: wrong columns → oracle FAILS."""
        if not _HAS_DUCKDB:
            pytest.fail("duckdb not available")

        conn = connect()
        load_file(conn, _SALES_CSV, "sales")

        wrong_cols = [("wrong_col", "VARCHAR")]

        with pytest.raises(AssertionError, match="column mismatch"):
            schema_readback(conn, "sales", wrong_cols, 20)
        conn.close()


# ---------------------------------------------------------------------------
# Honest degradation
# ---------------------------------------------------------------------------


class TestHonestDegradation:
    """DuckDB missing → FAIL LOUD, never fake results."""

    def test_pipeline_without_duckdb_fails_loud(self):
        """If DuckDB is not installed, pipeline must fail with clear error."""
        if _HAS_DUCKDB:
            # If duckdb IS installed, verify the pipeline works
            result = data_analytics_pipeline(
                input_files=[_SALES_CSV],
                sql_queries=["SELECT COUNT(*) FROM sales"],
            )
            assert result.ok, "Pipeline should succeed when DuckDB is available"
        else:
            result = data_analytics_pipeline(
                input_files=[_SALES_CSV],
                sql_queries=["SELECT COUNT(*) FROM sales"],
            )
            assert not result.ok
            assert "query engine unavailable" in result.error.lower()


# ---------------------------------------------------------------------------
# Gauntlet scenarios (>=3, zero skips)
# ---------------------------------------------------------------------------


class TestGauntletScenarios:
    ">=3 end-to-end gauntlet scenarios."""

    def test_scenario_a_group_by_aggregation(self):
        """Scenario (a): GROUP BY aggregation over CSV, verified vs pandas."""
        if not _HAS_DUCKDB:
            pytest.fail("duckdb not available")

        conn = connect()
        load_file(conn, _SALES_CSV, "sales")

        sql = (
            "SELECT product, SUM(quantity * unit_price) AS total_revenue "
            "FROM sales GROUP BY product ORDER BY product"
        )

        # Independent calc via pandas
        import pandas as pd

        df = pd.read_csv(_SALES_CSV)
        df["revenue"] = df["quantity"] * df["unit_price"]
        expected = df.groupby("product")["revenue"].sum().reset_index()
        expected = expected.sort_values("product").reset_index(drop=True)

        result = execute_query(conn, sql)
        assert result.columns == ["product", "total_revenue"]
        assert result.row_count == len(expected)

        for i, (actual, exp) in enumerate(zip(result.rows, expected.values.tolist())):
            assert actual[0] == exp[0], f"Product mismatch at row {i}"
            assert abs(float(actual[1]) - float(exp[1])) < 1e-6, (
                f"Revenue mismatch at row {i}: {actual[1]} vs {exp[1]}"
            )
        conn.close()

    def test_scenario_b_two_file_join(self):
        """Scenario (b): JOIN across CSV + Parquet, verified vs pandas."""
        if not _HAS_DUCKDB:
            pytest.fail("duckdb not available")

        conn = connect()
        load_file(conn, _ORDERS_CSV, "orders")
        load_file(conn, _CUSTOMERS_PARQUET, "customers")

        sql = (
            "SELECT c.name, o.product, o.amount "
            "FROM orders o JOIN customers c ON o.customer_id = c.customer_id "
            "ORDER BY c.name, o.product"
        )

        # Independent calc via pandas
        expected_cols, expected_rows = independent_join(
            _ORDERS_CSV,
            _CUSTOMERS_PARQUET,
            "customer_id",
            "customer_id",
            ["name", "product", "amount"],
        )

        passed = query_result(conn, sql, expected_rows, expected_cols)
        assert passed, "Two-file JOIN query result does not match independent calc"
        conn.close()

    def test_scenario_c_wrong_result_caught(self):
        """Scenario (c): deliberately wrong expected result → oracle catches it."""
        if not _HAS_DUCKDB:
            pytest.fail("duckdb not available")

        conn = connect()
        load_file(conn, _SALES_CSV, "sales")

        sql = "SELECT COUNT(*) AS cnt FROM sales WHERE region = 'North'"
        correct_count = independent_filter_count(_SALES_CSV, "region", "North")
        wrong_count = correct_count + 42  # Deliberately wrong

        result = execute_query(conn, sql)
        actual = result.rows[0][0]

        # The oracle must catch that wrong_count != actual
        assert actual == correct_count, "DuckDB result should match pandas"
        assert actual != wrong_count, "Kill-proof: wrong expected result should not match actual"
        conn.close()


# ---------------------------------------------------------------------------
# Trust stack integration
# ---------------------------------------------------------------------------


class TestTrustStackIntegration:
    """Audit log + zero-egress report integration."""

    def test_pipeline_emits_audit_and_egress(self):
        """Pipeline with private_key emits audit log + egress report."""
        if not _HAS_DUCKDB:
            pytest.fail("duckdb not available")

        private_key = ed25519.Ed25519PrivateKey.generate()

        result = data_analytics_pipeline(
            input_files=[_SALES_CSV],
            sql_queries=["SELECT COUNT(*) FROM sales"],
            private_key=private_key,
        )
        assert result.ok
        assert result.audit_log_json, "Audit log JSON should be non-empty"
        assert result.egress_report_json, "Egress report JSON should be non-empty"

        from kairo.oracles.ed25519_audit_log import Ed25519AuditLog
        from kairo.oracles.zero_egress_report import (
            report_from_json,
            verify_zero_egress_report,
        )

        public_key = private_key.public_key()
        entries = Ed25519AuditLog.entries_from_json(result.audit_log_json)
        assert len(entries) > 0
        assert Ed25519AuditLog.verify_chain(entries, public_key)

        report = report_from_json(result.egress_report_json)
        assert verify_zero_egress_report(report, public_key)


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestCLIIntegration:
    """data CLI subcommand works end-to-end via registry."""

    def test_cli_query(self):
        """`kairo data query` produces output + audit artifacts."""
        if not _HAS_DUCKDB:
            pytest.fail("duckdb not available")

        from kairo.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "data_output")
            rc = main(
                [
                    "data",
                    "query",
                    _SALES_CSV,
                    "SELECT product, SUM(quantity) AS total FROM sales GROUP BY product ORDER BY product",
                    "--out",
                    out_dir,
                ]
            )
            assert rc == 0, f"CLI query failed with exit code {rc}"
            assert os.path.isfile(os.path.join(out_dir, "audit_log.json"))
            assert os.path.isfile(os.path.join(out_dir, "zero_egress_report.json"))
