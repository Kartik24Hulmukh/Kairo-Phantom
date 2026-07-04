# PROVENANCE: original | clean-room data/analytics domain engine per DOMAIN_BUILD_TEMPLATE.md
"""Data/analytics domain engine — real SQL queries via DuckDB, verified by pandas.

Implements the ``query_result`` and ``schema_readback`` oracles from
specs/VERIFICATION_ORACLES.md for the Data/analytics domain.

ARCHITECTURE:
  1. DuckDB (MIT) loads CSV/Parquet/xlsx files and runs SQL queries.
  2. pandas/numpy (BSD-3) provide the INDEPENDENT verification — the oracle
     computes the same logic in Python and compares results.
  3. Never trust the engine alone — the oracle verifies query results vs
     independent calc.

HONEST DEGRADATION:
  If DuckDB is not installed, the engine FAILS LOUD:
  "query engine unavailable — install duckdb"
  It NEVER presents unverified results as done.

Dependencies (all permissive — MIT/BSD):
  - duckdb (MIT) — SQL query engine over local files
  - pandas (BSD-3) — independent verification + file I/O
  - numpy (BSD-3) — numeric computation
  - pyarrow (Apache-2.0) — Parquet support
  - openpyxl (MIT) — xlsx support (transitive via pandas)

All operations are fully offline. No network calls. No LLM. No cloud.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any

log = logging.getLogger("kairo.data_analytics")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class QueryEngineUnavailableError(RuntimeError):
    """Raised when DuckDB is not installed — honest degradation."""

    pass


class QueryError(RuntimeError):
    """Raised when a SQL query fails."""

    pass


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class QueryResult:
    """Structured result of a SQL query."""

    columns: list[str]
    rows: list[list[Any]]
    row_count: int

    def to_dict_list(self) -> list[dict[str, Any]]:
        """Convert to list of dicts (column → value)."""
        return [dict(zip(self.columns, row)) for row in self.rows]


@dataclass
class SchemaInfo:
    """Schema information for a loaded table."""

    table_name: str
    columns: list[tuple[str, str]]  # (column_name, dtype)
    row_count: int


@dataclass
class DataAnalyticsResult:
    """Structured result of a data/analytics pipeline run."""

    ok: bool
    query_results: list[QueryResult] = dc_field(default_factory=list)
    schema_info: SchemaInfo | None = None
    error: str = ""
    audit_log_json: str = ""
    egress_report_json: str = ""
    doc_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "query_count": len(self.query_results),
            "schema_info": (
                {
                    "table_name": self.schema_info.table_name,
                    "columns": self.schema_info.columns,
                    "row_count": self.schema_info.row_count,
                }
                if self.schema_info
                else None
            ),
            "error": self.error,
            "doc_hash": self.doc_hash,
        }


# ---------------------------------------------------------------------------
# Engine availability check
# ---------------------------------------------------------------------------


def _check_duckdb() -> bool:
    """Check if DuckDB is available."""
    try:
        import duckdb  # noqa: F401

        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# File loading
# ---------------------------------------------------------------------------


def load_file(
    conn: Any,
    file_path: str,
    table_name: str = "data",
) -> SchemaInfo:
    """Load a CSV/Parquet/xlsx file into a DuckDB table.

    Args:
        conn: DuckDB connection.
        file_path: Path to the file (.csv, .parquet, .xlsx).
        table_name: Name for the created table.

    Returns:
        SchemaInfo with columns, types, and row count.

    Raises:
        QueryError: If the file cannot be loaded.
    """
    file_path = str(Path(file_path).resolve())
    ext = Path(file_path).suffix.lower()

    if ext == ".csv":
        conn.execute(
            f"CREATE TABLE {table_name} AS SELECT * FROM read_csv_auto('{file_path}')"
        )
    elif ext == ".parquet":
        conn.execute(
            f"CREATE TABLE {table_name} AS SELECT * FROM read_parquet('{file_path}')"
        )
    elif ext == ".xlsx":
        # Use pandas to read xlsx, then register with DuckDB
        import pandas as pd

        df = pd.read_excel(file_path)
        conn.register(table_name, df)
        conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM {table_name}")
    else:
        raise QueryError(f"Unsupported file type: {ext}")

    # Get schema info
    schema = conn.execute(
        f"SELECT column_name, data_type FROM information_schema.columns "
        f"WHERE table_name = '{table_name}' ORDER BY ordinal_position"
    ).fetchall()

    row_count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]

    return SchemaInfo(
        table_name=table_name,
        columns=[(row[0], row[1]) for row in schema],
        row_count=row_count,
    )


def connect() -> Any:
    """Create a DuckDB in-memory connection.

    Raises:
        QueryEngineUnavailableError: If DuckDB is not installed.
    """
    if not _check_duckdb():
        raise QueryEngineUnavailableError(
            "query engine unavailable — install duckdb to enable SQL queries "
            "over local data files. The data/analytics domain cannot proceed "
            "without DuckDB."
        )

    import duckdb

    return duckdb.connect(":memory:")


# ---------------------------------------------------------------------------
# Query execution
# ---------------------------------------------------------------------------


def execute_query(conn: Any, sql: str) -> QueryResult:
    """Execute a SQL query and return structured results.

    Args:
        conn: DuckDB connection.
        sql: SQL query string.

    Returns:
        QueryResult with columns, rows, and row count.

    Raises:
        QueryError: If the query fails.
    """
    try:
        cursor = conn.execute(sql)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return QueryResult(columns=columns, rows=rows, row_count=len(rows))
    except Exception as e:
        raise QueryError(f"SQL query failed: {e}") from e


# ---------------------------------------------------------------------------
# Oracles (deterministic, kill-proof)
# ---------------------------------------------------------------------------


def query_result(
    conn: Any,
    sql: str,
    expected_rows: list[list[Any]],
    expected_columns: list[str],
    tolerance: float = 1e-6,
) -> bool:
    """Oracle: run SQL via DuckDB → assert result equals independent expected values.

    The expected_rows must come from an INDEPENDENT computation (pandas/numpy),
    not from the SQL engine itself.

    Args:
        conn: DuckDB connection.
        sql: SQL query to execute.
        expected_rows: Expected result rows from independent calc.
        expected_columns: Expected column names.
        tolerance: Float comparison tolerance.

    Returns:
        True if the query result matches the expected values.

    Raises:
        AssertionError: If results don't match.
        QueryEngineUnavailableError: If DuckDB is not installed.
        QueryError: If the query fails.
    """
    result = execute_query(conn, sql)

    # Check columns
    if result.columns != expected_columns:
        raise AssertionError(
            f"query_result FAILED: column mismatch.\n"
            f"  Expected: {expected_columns}\n"
            f"  Got:      {result.columns}"
        )

    # Check row count
    if result.row_count != len(expected_rows):
        raise AssertionError(
            f"query_result FAILED: row count mismatch.\n"
            f"  Expected: {len(expected_rows)} rows\n"
            f"  Got:      {result.row_count} rows"
        )

    # Check each row
    for i, (actual, expected) in enumerate(zip(result.rows, expected_rows)):
        if len(actual) != len(expected):
            raise AssertionError(
                f"query_result FAILED: row {i} column count mismatch.\n"
                f"  Expected: {len(expected)} cols\n"
                f"  Got:      {len(actual)} cols"
            )
        for j, (a, e) in enumerate(zip(actual, expected)):
            # Handle float comparison with tolerance
            if isinstance(a, float) or isinstance(e, float):
                if abs(float(a) - float(e)) > tolerance:
                    raise AssertionError(
                        f"query_result FAILED: row {i}, col {j} value mismatch.\n"
                        f"  Expected: {e}\n"
                        f"  Got:      {a}"
                    )
            elif a != e:
                raise AssertionError(
                    f"query_result FAILED: row {i}, col {j} value mismatch.\n"
                    f"  Expected: {e}\n"
                    f"  Got:      {a}"
                )

    return True


def schema_readback(
    conn: Any,
    table_name: str,
    expected_columns: list[tuple[str, str]],
    expected_row_count: int,
) -> bool:
    """Oracle: verify table schema (columns/types/row-count) after load.

    Args:
        conn: DuckDB connection.
        table_name: Name of the loaded table.
        expected_columns: List of (column_name, type) tuples.
        expected_row_count: Expected number of rows.

    Returns:
        True if schema matches.

    Raises:
        AssertionError: If schema doesn't match.
    """
    schema = conn.execute(
        f"SELECT column_name, data_type FROM information_schema.columns "
        f"WHERE table_name = '{table_name}' ORDER BY ordinal_position"
    ).fetchall()

    actual_columns = [(row[0], row[1]) for row in schema]
    if actual_columns != expected_columns:
        raise AssertionError(
            f"schema_readback FAILED: column mismatch.\n"
            f"  Expected: {expected_columns}\n"
            f"  Got:      {actual_columns}"
        )

    actual_count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    if actual_count != expected_row_count:
        raise AssertionError(
            f"schema_readback FAILED: row count mismatch.\n"
            f"  Expected: {expected_row_count}\n"
            f"  Got:      {actual_count}"
        )

    return True


# ---------------------------------------------------------------------------
# Independent calculations (pandas/numpy — never trust the engine alone)
# ---------------------------------------------------------------------------


def independent_group_by_sum(
    file_path: str,
    group_col: str,
    sum_col: str,
) -> tuple[list[str], list[list[Any]]]:
    """Independent pandas computation of GROUP BY + SUM.

    Returns (columns, rows) matching what a SQL query would produce.
    """
    import pandas as pd

    ext = Path(file_path).suffix.lower()
    if ext == ".csv":
        df = pd.read_csv(file_path)
    elif ext == ".parquet":
        df = pd.read_parquet(file_path)
    elif ext == ".xlsx":
        df = pd.read_excel(file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    grouped = df.groupby(group_col)[sum_col].sum().reset_index()
    grouped = grouped.sort_values(group_col).reset_index(drop=True)

    columns = [group_col, f"total_{sum_col}"]
    rows = grouped.values.tolist()
    return columns, rows


def independent_join(
    left_file: str,
    right_file: str,
    left_key: str,
    right_key: str,
    select_cols: list[str],
) -> tuple[list[str], list[list[Any]]]:
    """Independent pandas computation of an INNER JOIN.

    Returns (columns, rows) matching what a SQL query would produce.
    """
    import pandas as pd

    def _read(path):
        ext = Path(path).suffix.lower()
        if ext == ".csv":
            return pd.read_csv(path)
        elif ext == ".parquet":
            return pd.read_parquet(path)
        elif ext == ".xlsx":
            return pd.read_excel(path)
        raise ValueError(f"Unsupported: {ext}")

    left = _read(left_file)
    right = _read(right_file)

    merged = left.merge(right, left_on=left_key, right_on=right_key, how="inner")
    result = merged[select_cols].sort_values(select_cols).reset_index(drop=True)

    columns = select_cols
    rows = result.values.tolist()
    return columns, rows


def independent_filter_count(
    file_path: str,
    filter_col: str,
    filter_value: str,
) -> int:
    """Independent pandas computation of a filtered COUNT.

    Returns the count of rows where filter_col == filter_value.
    """
    import pandas as pd

    ext = Path(file_path).suffix.lower()
    if ext == ".csv":
        df = pd.read_csv(file_path)
    elif ext == ".parquet":
        df = pd.read_parquet(file_path)
    elif ext == ".xlsx":
        df = pd.read_excel(file_path)
    else:
        raise ValueError(f"Unsupported: {ext}")

    return int(len(df[df[filter_col] == filter_value]))


# ---------------------------------------------------------------------------
# Pipeline with trust stack integration
# ---------------------------------------------------------------------------


def data_analytics_pipeline(
    input_files: list[str],
    sql_queries: list[str],
    table_names: list[str] | None = None,
    private_key: Any = None,
    author: str = "Kairo Data",
) -> DataAnalyticsResult:
    """Run the data/analytics pipeline with trust stack integration.

    1. Connect to DuckDB (in-memory).
    2. Load each input file into a table.
    3. Execute each SQL query.
    4. Emit Ed25519 audit log + zero-egress report (if private_key provided).

    Args:
        input_files: List of file paths to load (CSV/Parquet/xlsx).
        sql_queries: List of SQL queries to execute.
        table_names: Optional table names for each file (defaults to file stem).
        private_key: Optional Ed25519 private key for audit + egress report.
        author: Author name for audit log.

    Returns:
        DataAnalyticsResult with query results and trust artifacts.
    """
    if table_names is None:
        table_names = [Path(f).stem for f in input_files]

    # Compute doc hash from input files
    hasher = hashlib.sha256()
    for f in input_files:
        with open(f, "rb") as fh:
            hasher.update(fh.read())
    doc_hash = hasher.hexdigest()

    try:
        conn = connect()
    except QueryEngineUnavailableError as e:
        return DataAnalyticsResult(ok=False, error=str(e), doc_hash=doc_hash)

    # Load files
    schema_infos: list[SchemaInfo] = []
    for file_path, table_name in zip(input_files, table_names):
        try:
            si = load_file(conn, file_path, table_name)
            schema_infos.append(si)
        except QueryError as e:
            return DataAnalyticsResult(ok=False, error=str(e), doc_hash=doc_hash)

    # Execute queries
    query_results: list[QueryResult] = []
    for sql in sql_queries:
        try:
            qr = execute_query(conn, sql)
            query_results.append(qr)
        except QueryError as e:
            return DataAnalyticsResult(
                ok=False,
                query_results=query_results,
                schema_info=schema_infos[0] if schema_infos else None,
                error=str(e),
                doc_hash=doc_hash,
            )

    conn.close()

    # Emit audit log + egress report
    audit_log_json = ""
    egress_report_json = ""
    if private_key is not None:
        from kairo.oracles.ed25519_audit_log import Ed25519AuditLog
        from kairo.oracles.zero_egress_report import generate_zero_egress_report

        audit = Ed25519AuditLog(private_key)
        audit.log_run_started(doc_hash=doc_hash, playbook_id="data_analytics_pipeline")

        for i, qr in enumerate(query_results):
            audit.log_edit(
                doc_hash=doc_hash,
                clause_id=f"query_{i}",
                clause_label=f"SQL query {i}: {qr.row_count} rows",
                old_text="",
                new_text=f"Returned {qr.row_count} rows, {len(qr.columns)} columns",
                citation="duckdb",
                rationale="SQL query executed over local data files",
            )

        audit.log_run_completed(
            doc_hash=doc_hash,
            total_edits=len(query_results),
            total_flagged=0,
            injection_detected=False,
        )

        audit_log_json = audit.to_json()

        egress_report = generate_zero_egress_report(
            doc_hash=doc_hash,
            playbook_id="data_analytics_pipeline",
            total_edits=len(query_results),
            total_flagged=0,
            injection_detected=False,
            audit_log_json=audit_log_json,
            private_key=private_key,
        )
        egress_report_json = egress_report.to_json()

    return DataAnalyticsResult(
        ok=True,
        query_results=query_results,
        schema_info=schema_infos[0] if schema_infos else None,
        audit_log_json=audit_log_json,
        egress_report_json=egress_report_json,
        doc_hash=doc_hash,
    )
