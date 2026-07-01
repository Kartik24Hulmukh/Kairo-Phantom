"""
scenario_store.py — DuckDB-backed scenario registry and results store for Phase 5.

Schema:
  scenarios  (id TEXT PK, prompt TEXT, fixture TEXT, oracle TEXT,
              category TEXT, fix_budget INT)
  results    (run_id TEXT, scenario_id TEXT, worker_id TEXT,
              sandbox_path TEXT, oracle_verdict TEXT, elapsed_s REAL,
              ts TIMESTAMP DEFAULT current_timestamp)
"""

from __future__ import annotations

import os
import uuid
import datetime
from typing import Any, Dict, List, Optional

import duckdb


_DEFAULT_DB = os.path.join(os.path.dirname(__file__), "..", "kairo_scenarios.duckdb")


def _connect(db_path: str = _DEFAULT_DB) -> duckdb.DuckDBPyConnection:
    """Open (or create) the DuckDB database and ensure tables exist."""
    con = duckdb.connect(db_path)
    con.execute("""
        CREATE TABLE IF NOT EXISTS scenarios (
            id          TEXT PRIMARY KEY,
            prompt      TEXT,
            fixture     TEXT,
            oracle      TEXT,
            category    TEXT,
            fix_budget  INTEGER
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS results (
            run_id          TEXT,
            scenario_id     TEXT,
            worker_id       TEXT,
            sandbox_path    TEXT,
            oracle_verdict  TEXT,
            elapsed_s       DOUBLE,
            ts              TIMESTAMP
        )
    """)
    return con


def upsert_scenario(
    scenario: Dict[str, Any],
    db_path: str = _DEFAULT_DB,
) -> None:
    """Insert or replace a scenario row (upsert by id)."""
    sid = scenario.get("id", str(uuid.uuid4()))
    con = _connect(db_path)
    try:
        # DuckDB doesn't support INSERT OR REPLACE; use DELETE + INSERT.
        con.execute("DELETE FROM scenarios WHERE id = ?", [sid])
        con.execute(
            """
            INSERT INTO scenarios
                (id, prompt, fixture, oracle, category, fix_budget)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            [
                sid,
                scenario.get("prompt", ""),
                scenario.get("fixture", ""),
                scenario.get("oracle", ""),
                scenario.get("category", ""),
                int(scenario.get("fix_budget", 3)),
            ],
        )
    finally:
        con.close()


def record_result(
    run_id: str,
    scenario_id: str,
    worker_id: str,
    sandbox_path: str,
    oracle_verdict: str,
    elapsed_s: float,
    db_path: str = _DEFAULT_DB,
) -> None:
    """Append one result row."""
    con = _connect(db_path)
    try:
        con.execute(
            """
            INSERT INTO results
                (run_id, scenario_id, worker_id, sandbox_path, oracle_verdict, elapsed_s, ts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            [
                run_id,
                scenario_id,
                worker_id,
                sandbox_path,
                oracle_verdict,
                float(elapsed_s),
                datetime.datetime.utcnow(),
            ],
        )
    finally:
        con.close()


def query_results(run_id: Optional[str] = None, db_path: str = _DEFAULT_DB) -> List[Dict[str, Any]]:
    """Return result rows, optionally filtered by run_id."""
    con = _connect(db_path)
    try:
        if run_id:
            rows = con.execute(
                """
                SELECT r.run_id, r.scenario_id, s.category, r.worker_id,
                       r.sandbox_path, r.oracle_verdict, r.elapsed_s, r.ts
                FROM   results r
                LEFT JOIN scenarios s ON s.id = r.scenario_id
                WHERE  r.run_id = ?
                ORDER  BY r.ts
            """,
                [run_id],
            ).fetchall()
        else:
            rows = con.execute("""
                SELECT r.run_id, r.scenario_id, s.category, r.worker_id,
                       r.sandbox_path, r.oracle_verdict, r.elapsed_s, r.ts
                FROM   results r
                LEFT JOIN scenarios s ON s.id = r.scenario_id
                ORDER  BY r.ts
            """).fetchall()
        columns = [
            "run_id",
            "scenario_id",
            "category",
            "worker_id",
            "sandbox_path",
            "oracle_verdict",
            "elapsed_s",
            "ts",
        ]
        return [dict(zip(columns, row)) for row in rows]
    finally:
        con.close()


def seed_scenarios(scenarios: List[Dict[str, Any]], db_path: str = _DEFAULT_DB) -> None:
    """Bulk-upsert a list of scenario dicts."""
    for s in scenarios:
        upsert_scenario(s, db_path)


def load_scenarios(db_path: str = _DEFAULT_DB) -> List[Dict[str, Any]]:
    """Load all scenarios from the DB as dicts."""
    con = _connect(db_path)
    try:
        rows = con.execute(
            "SELECT id, prompt, fixture, oracle, category, fix_budget FROM scenarios"
        ).fetchall()
        columns = ["id", "prompt", "fixture", "oracle", "category", "fix_budget"]
        return [dict(zip(columns, row)) for row in rows]
    finally:
        con.close()
