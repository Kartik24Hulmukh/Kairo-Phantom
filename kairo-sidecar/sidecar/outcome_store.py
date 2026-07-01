"""
outcome_store.py — DuckDB-backed episode store for Kairo Phantom gauntlet.

Stores every episode (state, intent, action, outcome, accepted?) and full
LoopResult audit trails.  Public API is backward-compatible with the old
SQLite version so all callers work without change.

Schema
------
  episodes     — one row per gym_env step (backward-compat with SQLite version)
  loop_results — one row per TestFixLoop.run_loop() call (with audit trail JSON)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

import duckdb

log = logging.getLogger("kairo.outcome_store")


# ── default DB location ───────────────────────────────────────────────────────


def _default_db_path() -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    target_dir = os.path.join(base_dir, "target")
    os.makedirs(target_dir, exist_ok=True)
    return os.path.join(target_dir, "gauntlet_outcomes.duckdb")


class OutcomeStore:
    """
    DuckDB-backed outcome store.

    Public API (backward-compatible with the old SQLite version):
        log_episode(...)              -> int  (episode id or -1)
        get_episodes(scenario_id)     -> List[dict]
        get_all_episodes()            -> List[dict]

    New methods (Item 37):
        log_loop_result(loop_result)  -> None
        get_loop_audit(scenario_id)   -> List[dict]
        get_all_loop_results()        -> List[dict]
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or _default_db_path()
        self._initialize_db()

    # ── internal helpers ──────────────────────────────────────────────────────

    def _con(self) -> duckdb.DuckDBPyConnection:
        """Open a new connection — cheap in DuckDB."""
        return duckdb.connect(self.db_path)

    def _initialize_db(self) -> None:
        """Create sequences and tables if they don't exist."""
        try:
            con = self._con()
            # Sequences for auto-increment IDs
            con.execute("CREATE SEQUENCE IF NOT EXISTS episodes_id_seq START 1")
            con.execute("CREATE SEQUENCE IF NOT EXISTS loop_results_id_seq START 1")

            con.execute("""
                CREATE TABLE IF NOT EXISTS episodes (
                    id           BIGINT DEFAULT nextval('episodes_id_seq'),
                    scenario_id  TEXT   NOT NULL,
                    state        TEXT,
                    intent       TEXT,
                    action       TEXT,
                    outcome      TEXT,
                    accepted     BOOLEAN,
                    ts           TIMESTAMP DEFAULT current_timestamp
                )
            """)

            con.execute("""
                CREATE TABLE IF NOT EXISTS loop_results (
                    id              BIGINT DEFAULT nextval('loop_results_id_seq'),
                    scenario_id     TEXT   NOT NULL,
                    terminal_state  TEXT   NOT NULL,
                    reward          DOUBLE NOT NULL,
                    attempts_used   INTEGER NOT NULL,
                    elapsed_s       DOUBLE NOT NULL,
                    failure_reason  TEXT,
                    ticket_path     TEXT,
                    audit_trail     TEXT,
                    ts              TIMESTAMP DEFAULT current_timestamp
                )
            """)
            con.close()
        except Exception as exc:
            log.error(f"[OutcomeStore] Failed to initialise DuckDB: {exc}")

    # ── backward-compatible API ───────────────────────────────────────────────

    def log_episode(
        self,
        scenario_id: str,
        state: Dict[str, Any],
        intent: str,
        action: str,
        outcome: str,
        accepted: bool,
    ) -> int:
        """Insert one gauntlet-env step.  Returns the new episode id or -1 on error."""
        try:
            state_json = json.dumps(state)
            con = self._con()
            con.execute(
                """
                INSERT INTO episodes (scenario_id, state, intent, action, outcome, accepted)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [scenario_id, state_json, intent, action, outcome, accepted],
            )
            # currval returns the last value emitted by nextval in this connection
            row = con.execute("SELECT currval('episodes_id_seq')").fetchone()
            con.close()
            return int(row[0]) if row else -1
        except Exception as exc:
            log.error(f"[OutcomeStore] log_episode failed: {exc}")
            return -1

    def get_episodes(self, scenario_id: str) -> List[Dict[str, Any]]:
        """Return all episodes for a given scenario, newest first."""
        try:
            con = self._con()
            rows = con.execute(
                "SELECT id, scenario_id, state, intent, action, outcome, accepted, ts "
                "FROM episodes WHERE scenario_id = ? ORDER BY ts DESC",
                [scenario_id],
            ).fetchall()
            con.close()
            return [self._row_to_episode(r) for r in rows]
        except Exception as exc:
            log.error(f"[OutcomeStore] get_episodes failed: {exc}")
            return []

    def get_all_episodes(self) -> List[Dict[str, Any]]:
        """Return every episode across all scenarios, newest first."""
        try:
            con = self._con()
            rows = con.execute(
                "SELECT id, scenario_id, state, intent, action, outcome, accepted, ts "
                "FROM episodes ORDER BY ts DESC"
            ).fetchall()
            con.close()
            return [self._row_to_episode(r) for r in rows]
        except Exception as exc:
            log.error(f"[OutcomeStore] get_all_episodes failed: {exc}")
            return []

    # ── new Item-37 API ───────────────────────────────────────────────────────

    def log_loop_result(self, loop_result: Any) -> None:
        """
        Persist a complete LoopResult (from TestFixLoop.run_loop) to DuckDB.
        The audit_trail list is JSON-serialised so it survives round-trips.
        """
        import dataclasses as _dc

        try:
            audit_json = json.dumps(
                [_dc.asdict(a) for a in loop_result.audit_trail] if loop_result.audit_trail else []
            )
            con = self._con()
            con.execute(
                """
                INSERT INTO loop_results
                    (scenario_id, terminal_state, reward, attempts_used,
                     elapsed_s, failure_reason, ticket_path, audit_trail)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    loop_result.scenario_id,
                    loop_result.terminal_state,
                    float(loop_result.reward),
                    int(loop_result.attempts_used),
                    float(loop_result.elapsed_s),
                    loop_result.failure_reason,
                    loop_result.ticket_path,
                    audit_json,
                ],
            )
            con.close()
            log.info(
                f"[OutcomeStore] Logged LoopResult: "
                f"scenario={loop_result.scenario_id} "
                f"state={loop_result.terminal_state} "
                f"reward={loop_result.reward:+.1f}"
            )
        except Exception as exc:
            log.error(f"[OutcomeStore] log_loop_result failed: {exc}")

    def get_loop_audit(self, scenario_id: str) -> List[Dict[str, Any]]:
        """
        Return the per-attempt audit trail for a scenario.
        Each dict has: scenario_id, terminal_state, reward, attempts_used,
        elapsed_s, failure_reason, ticket_path, ts, attempts (list of dicts).
        """
        try:
            con = self._con()
            rows = con.execute(
                """
                SELECT scenario_id, terminal_state, reward, attempts_used,
                       elapsed_s, failure_reason, ticket_path, audit_trail, ts
                FROM   loop_results
                WHERE  scenario_id = ?
                ORDER  BY ts DESC
                """,
                [scenario_id],
            ).fetchall()
            con.close()
            cols = [
                "scenario_id",
                "terminal_state",
                "reward",
                "attempts_used",
                "elapsed_s",
                "failure_reason",
                "ticket_path",
                "audit_trail",
                "ts",
            ]
            results = []
            for row in rows:
                d = dict(zip(cols, row))
                d["attempts"] = json.loads(d.pop("audit_trail") or "[]")
                results.append(d)
            return results
        except Exception as exc:
            log.error(f"[OutcomeStore] get_loop_audit failed: {exc}")
            return []

    def get_all_loop_results(self) -> List[Dict[str, Any]]:
        """Return every LoopResult row summary (without audit trail), newest first."""
        try:
            con = self._con()
            rows = con.execute(
                """
                SELECT scenario_id, terminal_state, reward,
                       attempts_used, elapsed_s, failure_reason, ts
                FROM   loop_results
                ORDER  BY ts DESC
                """
            ).fetchall()
            con.close()
            cols = [
                "scenario_id",
                "terminal_state",
                "reward",
                "attempts_used",
                "elapsed_s",
                "failure_reason",
                "ts",
            ]
            return [dict(zip(cols, r)) for r in rows]
        except Exception as exc:
            log.error(f"[OutcomeStore] get_all_loop_results failed: {exc}")
            return []

    # ── internal utils ────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_episode(row: tuple) -> Dict[str, Any]:
        """Convert a fetched row tuple to an episode dict."""
        eid, scenario_id, state_json, intent, action, outcome, accepted, ts = row
        state = {}
        if state_json:
            try:
                state = json.loads(state_json)
            except Exception:
                pass
        return {
            "id": eid,
            "scenario_id": scenario_id,
            "state": state,
            "intent": intent,
            "action": action,
            "outcome": outcome,
            "accepted": bool(accepted),
            "timestamp": str(ts),
        }
