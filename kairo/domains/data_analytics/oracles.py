# PROVENANCE: original | clean-room data/analytics oracles per VERIFICATION_ORACLES.md
"""Data/analytics domain oracles — deterministic, kill-proven verification.

Implements two practitioner-grade oracles:

  1. ``query_result_oracle`` — runs SQL via DuckDB and compares the result
     to an INDEPENDENT pandas/numpy computation of the same logic.  The
     expected values must come from a separate code path (pandas), never
     from the SQL engine itself.

  2. ``schema_readback_oracle`` — verifies that a loaded table's columns,
     types, and row count match the expected schema.

Both oracles are KILL-PROVEN: perturbing the expected result (dropping a
row, wrong aggregate, wrong column) causes a hard failure.

HONEST DEGRADATION:
  If DuckDB is not installed, the oracles raise ``QueryEngineUnavailableError``
  — they never present unverified results as correct.

All operations are fully offline.  No network calls.  No LLM.  No cloud.

Dependencies (all permissive — MIT/BSD):
  - duckdb (MIT) — SQL query engine
  - pandas (BSD-3) — independent verification + file I/O
  - numpy (BSD-3) — numeric computation
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from kairo.domains.data_analytics.engine import execute_query


# ---------------------------------------------------------------------------
# Oracle 1: query_result_oracle
# ---------------------------------------------------------------------------


def query_result_oracle(
    conn: Any,
    sql: str,
    expected_rows: list[list[Any]],
    expected_columns: list[str],
    tolerance: float = 1e-6,
) -> bool:
    """Oracle: run SQL via DuckDB → assert result equals independent expected values.

    The expected_rows must come from an INDEPENDENT computation (pandas/numpy),
    not from the SQL engine itself.

    KILL-PROOF: perturbing expected_rows (wrong value, dropped row, wrong
    column list) causes an AssertionError.

    Args:
        conn: DuckDB connection.
        sql: SQL query to execute.
        expected_rows: Expected result rows from independent calc.
        expected_columns: Expected column names.
        tolerance: Float comparison tolerance.

    Returns:
        True if the query result matches the expected values.

    Raises:
        AssertionError: If results don't match (kill-proof).
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


# ---------------------------------------------------------------------------
# Oracle 2: schema_readback_oracle
# ---------------------------------------------------------------------------


def schema_readback_oracle(
    conn: Any,
    table_name: str,
    expected_columns: list[tuple[str, str]],
    expected_row_count: int,
) -> bool:
    """Oracle: verify table schema (columns/types/row-count) after load.

    KILL-PROOF: dropping a column, changing a type, or wrong row count
    causes an AssertionError.

    Args:
        conn: DuckDB connection.
        table_name: Name of the loaded table.
        expected_columns: List of (column_name, type) tuples.
        expected_row_count: Expected number of rows.

    Returns:
        True if schema matches.

    Raises:
        AssertionError: If schema doesn't match (kill-proof).
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
        raise ValueError(f"Unsupported file type: {ext}")

    return int(len(df[df[filter_col] == filter_value]))
