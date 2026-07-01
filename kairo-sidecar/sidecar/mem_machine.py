import os
import sqlite3
import logging
import time
from typing import Optional, List, Dict, Any
from sidecar.observability.opik_tracer import track

log = logging.getLogger("kairo-sidecar.mem_machine")

# Default DB path — can be overridden via KAIRO_DB_PATH env var or config
DEFAULT_DB_PATH = os.path.join(os.path.expanduser("~"), ".kairo", "memmachine.db")

DDL = """
CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'local',
    domain TEXT NOT NULL,
    task_type TEXT NOT NULL,
    user_prompt TEXT NOT NULL,
    output_preview TEXT,
    confidence REAL DEFAULT 1.0,
    style_notes TEXT,
    created_at REAL NOT NULL,
    style_vector TEXT
);
CREATE TABLE IF NOT EXISTS audit_chain (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_type TEXT NOT NULL,
    epsilon REAL NOT NULL,
    delta REAL NOT NULL,
    chain_hash TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_domain_user ON interactions(user_id, domain);
CREATE INDEX IF NOT EXISTS idx_created_at ON interactions(created_at);
"""


class MemMachineClient:
    """
    Local SQLite-backed memory for Kairo domain interactions.
    Records user interactions and recalls style preferences for each domain.
    Sub-300ms recall via indexed SQLite queries.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = (
            db_path
            or os.environ.get("KAIRO_DB_PATH")
            or self._load_db_path_from_config()
            or DEFAULT_DB_PATH
        )
        self._ensure_db()

    def _load_db_path_from_config(self) -> Optional[str]:
        """Try to load db_path from config/kairo.toml."""
        try:
            # Look for kairo.toml in standard locations
            candidates = [
                os.path.join(os.path.dirname(__file__), "..", "..", "config", "kairo.toml"),
                os.path.join(os.path.expanduser("~"), ".kairo", "kairo.toml"),
            ]
            for candidate in candidates:
                candidate = os.path.normpath(candidate)
                if os.path.exists(candidate):
                    with open(candidate, "r", encoding="utf-8") as f:
                        content = f.read()
                    # Simple TOML key extraction (no toml library dependency)
                    import re

                    m = re.search(r'db_path\s*=\s*["\']([^"\']+)["\']', content)
                    if m:
                        return m.group(1)
        except Exception as e:
            log.debug(f"MemMachineClient: could not load config: {e}")
        return None

    def _ensure_db(self):
        """Create DB and tables if they don't exist."""
        conn = None
        try:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            conn = sqlite3.connect(self.db_path, timeout=10, check_same_thread=False)
            # WAL mode: allows concurrent readers + one writer without locking errors
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")  # Safe + faster with WAL
            conn.executescript(DDL)

            # Migration check: if style_vector column does not exist, add it
            try:
                conn.execute("ALTER TABLE interactions ADD COLUMN style_vector TEXT")
                conn.commit()
            except Exception:
                pass

            conn.commit()
            log.debug(f"MemMachineClient: DB ready at {self.db_path} (WAL mode)")
        except Exception as e:
            log.error(f"MemMachineClient: DB initialization failed: {e}")
        finally:
            if conn is not None:
                conn.close()

    def _connect(self) -> sqlite3.Connection:
        # check_same_thread=False: sidecar uses threads; SQLite is safe if we use
        # per-call connections (open → query → close) rather than shared connections.
        conn = sqlite3.connect(self.db_path, timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # Ensure WAL is active on every new connection (in case of DB recreation)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def recall_contextualized(self, query_text: str, domain: str = "", limit: int = 5) -> str:
        """
        Semantic recall using model2vec embeddings.

        Finds interactions with semantically similar user_prompt/style_notes,
        not just keyword matches. Uses cosine similarity over model2vec embeddings.

        Falls back to keyword-based query() if model2vec is not available.
        """
        try:
            import numpy as np
            from sidecar.embeddings import embed_text, embed_texts
        except ImportError:
            return self.query(domain=domain, limit=limit)

        # Encode the query using the existing embeddings module
        query_emb = np.array(embed_text(query_text))

        # Get all interactions from the database
        conn = self._connect()
        rows = conn.execute(
            "SELECT domain, task_type, user_prompt, style_notes FROM interactions ORDER BY created_at DESC LIMIT 1000"
        ).fetchall()
        conn.close()

        if not rows:
            return ""

        # Encode all stored prompts using the existing embeddings module
        texts = [f"{r['user_prompt']} {r['style_notes']}" for r in rows]
        stored_embs = np.array(embed_texts(texts))

        # Compute cosine similarity
        query_norm = query_emb / (np.linalg.norm(query_emb) + 1e-8)
        stored_norms = stored_embs / (np.linalg.norm(stored_embs, axis=1, keepdims=True) + 1e-8)
        similarities = stored_norms @ query_norm

        # Filter by domain if specified
        if domain:
            domain_mask = np.array([1 if r["domain"] == domain else 0 for r in rows])
            similarities = similarities * domain_mask

        # Get top-k results
        top_indices = np.argsort(similarities)[::-1][:limit]

        # Build context string from top results
        context_parts = []
        for idx in top_indices:
            if similarities[idx] > 0.1:  # Minimum similarity threshold
                row = rows[idx]
                context_parts.append(row["style_notes"])

        return " ".join(context_parts) if context_parts else ""

    @track("memory", "query")
    def query(
        self,
        user_id: str = "local",
        domain: str = "",
        task_type: str = "",
        limit: int = 5,
    ) -> str:
        """
        Retrieve recent style context for user+domain as a formatted string.
        Returns empty string if no history.
        """
        conn = None
        try:
            conn = self._connect()
            # Get the most recent interactions for this user+domain
            rows = conn.execute(
                """
                SELECT task_type, user_prompt, style_notes, output_preview, confidence
                FROM interactions
                WHERE user_id=? AND domain=?
                ORDER BY created_at DESC LIMIT ?
                """,
                (user_id, domain, limit),
            ).fetchall()

            if not rows:
                return ""

            lines = [f"[MemMachine — {domain} style history for {user_id}]"]
            for row in rows:
                if row["style_notes"]:
                    lines.append(f"• {row['task_type']}: {row['style_notes']}")
                elif row["output_preview"]:
                    lines.append(f"• {row['task_type']}: {row['output_preview'][:150]}")
            return "\n".join(lines)
        except Exception as e:
            log.warning(f"MemMachineClient.query failed: {e}")
            return ""
        finally:
            if conn is not None:
                conn.close()

    def record_interaction(
        self,
        domain: str,
        task_type: str,
        user_prompt: str,
        output_preview: str = "",
        confidence: float = 1.0,
        user_id: str = "local",
        style_notes: str = "",
        style_vector: Optional[List[float]] = None,
    ) -> bool:
        """Record an interaction to the SQLite DB."""
        conn = None
        try:
            import json

            vector_json = json.dumps(style_vector) if style_vector else None
            conn = self._connect()
            conn.execute(
                """
                INSERT INTO interactions
                (user_id, domain, task_type, user_prompt, output_preview, confidence, style_notes, created_at, style_vector)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    domain,
                    task_type,
                    user_prompt[:500],
                    output_preview[:500],
                    confidence,
                    style_notes[:500],
                    time.time(),
                    vector_json,
                ),
            )
            conn.commit()
            log.debug(f"MemMachineClient: recorded {domain}/{task_type} interaction")
            return True
        except Exception as e:
            log.error(f"MemMachineClient.record_interaction failed: {e}")
            return False
        finally:
            if conn is not None:
                conn.close()

    def get_style_centroid(
        self, user_id: str = "local", domain: str = "", limit: int = 10
    ) -> Optional[List[float]]:
        """Compute style centroid as element-wise mean of recent style vectors."""
        conn = None
        try:
            import json

            conn = self._connect()
            rows = conn.execute(
                """
                SELECT style_vector FROM interactions
                WHERE user_id=? AND domain=? AND style_vector IS NOT NULL AND style_vector != ''
                ORDER BY created_at DESC LIMIT ?
                """,
                (user_id, domain, limit),
            ).fetchall()

            if not rows:
                return None

            vectors = []
            for r in rows:
                try:
                    v = json.loads(r["style_vector"])
                    if isinstance(v, list) and v:
                        vectors.append(v)
                except Exception:
                    continue

            if not vectors:
                return None

            dim = len(vectors[0])
            centroid = [0.0] * dim
            for v in vectors:
                for idx in range(min(dim, len(v))):
                    centroid[idx] += v[idx]
            for idx in range(dim):
                centroid[idx] /= len(vectors)

            return centroid
        except Exception as e:
            log.warning(f"MemMachineClient.get_style_centroid failed: {e}")
            return None
        finally:
            if conn is not None:
                conn.close()

    def get_style_profile(self, user_id: str = "local", domain: str = "") -> Dict[str, Any]:
        """Get aggregated style profile for user+domain."""
        conn = None
        try:
            conn = self._connect()
            rows = conn.execute(
                """
                SELECT task_type, COUNT(*) as count, AVG(confidence) as avg_conf
                FROM interactions
                WHERE user_id=? AND domain=?
                GROUP BY task_type
                ORDER BY count DESC
                """,
                (user_id, domain),
            ).fetchall()
            return {
                "user_id": user_id,
                "domain": domain,
                "task_frequencies": [
                    {
                        "task_type": r["task_type"],
                        "count": r["count"],
                        "avg_confidence": r["avg_conf"],
                    }
                    for r in rows
                ],
            }
        except Exception as e:
            log.warning(f"MemMachineClient.get_style_profile failed: {e}")
            return {"user_id": user_id, "domain": domain, "task_frequencies": []}
        finally:
            if conn is not None:
                conn.close()

    def clear_domain_history(self, domain: str, user_id: str = "local") -> int:
        """Clear all interactions for a domain. Returns number of rows deleted."""
        conn = None
        try:
            conn = self._connect()
            cursor = conn.execute(
                "DELETE FROM interactions WHERE user_id=? AND domain=?", (user_id, domain)
            )
            deleted = cursor.rowcount
            conn.commit()
            return deleted
        except Exception as e:
            log.error(f"MemMachineClient.clear_domain_history failed: {e}")
            return 0
        finally:
            if conn is not None:
                conn.close()


class MemorySeeder:
    """
    High-level adapter for seeding MemMachine after successful domain operations.
    Wraps MemMachineClient and provides a structured seed_operation() interface.
    """

    def __init__(self, db_path: Optional[str] = None):
        self._client = MemMachineClient(db_path=db_path)

    def seed_operation(
        self,
        domain: str,
        operation: Dict[str, Any],
        result: Dict[str, Any],
        user_correction: Optional[str] = None,
        user_id: str = "local",
        style_vector: Optional[List[float]] = None,
    ) -> bool:
        """
        Seed a completed operation into MemMachine for future style recall.

        Parameters
        ----------
        domain       : Domain string (e.g. "word", "excel").
        operation    : Dict with keys: op (str), user_prompt (str).
        result       : Dict with key: summary (str).
        user_correction : Optional user-provided correction string (for style learning).
        user_id      : MemMachine user key.
        style_vector : Optional style vector.
        """
        op_type = operation.get("op", "insert")
        user_prompt = operation.get("user_prompt", "")
        result_summary = result.get("summary", "")
        style_notes = user_correction or ""

        return self._client.record_interaction(
            domain=domain,
            task_type=op_type,
            user_prompt=user_prompt,
            output_preview=result_summary,
            confidence=1.0,
            user_id=user_id,
            style_notes=style_notes,
            style_vector=style_vector,
        )


class MemSyncManager:
    """
    Exposes MemSyncManager in sidecar wrapping MemMachineClient's record_interaction and query.
    Used for federated DP sync and interaction recall.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.client = MemMachineClient(db_path=db_path)

    def record_interaction(
        self,
        domain: str,
        task_type: str,
        user_prompt: str,
        output_preview: str = "",
        confidence: float = 1.0,
        user_id: str = "local",
        style_notes: str = "",
        style_vector: Optional[List[float]] = None,
    ) -> bool:
        return self.client.record_interaction(
            domain=domain,
            task_type=task_type,
            user_prompt=user_prompt,
            output_preview=output_preview,
            confidence=confidence,
            user_id=user_id,
            style_notes=style_notes,
            style_vector=style_vector,
        )

    def query(
        self,
        user_id: str = "local",
        domain: str = "",
        task_type: str = "",
        limit: int = 5,
    ) -> str:
        return self.client.query(
            user_id=user_id,
            domain=domain,
            task_type=task_type,
            limit=limit,
        )
