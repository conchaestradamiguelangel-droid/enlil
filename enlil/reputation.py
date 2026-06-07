import json
import sqlite3
import os
import time
from .gods.base import GodProfile

DEFAULT_DB = os.environ.get("ENLIL_DB", "enlil.db")


class ReputationStore:
    """Persiste y actualiza la reputación de cada dios por dominio."""

    def __init__(self, db_path: str = DEFAULT_DB, connection: sqlite3.Connection | None = None):
        self._conn = connection if connection is not None else sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS reputation (
                god_name TEXT NOT NULL,
                domain TEXT NOT NULL,
                score REAL NOT NULL DEFAULT 0.5,
                evaluations INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (god_name, domain)
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS reputation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                god_name TEXT NOT NULL,
                domain TEXT NOT NULL,
                score REAL NOT NULL,
                timestamp REAL NOT NULL
            )
        """)
        self._conn.commit()

    def load_into(self, pantheon: dict[str, GodProfile]):
        rows = self._conn.execute("SELECT god_name, domain, score FROM reputation").fetchall()
        for god_name, domain, score in rows:
            if god_name in pantheon:
                pantheon[god_name].reputation[domain] = score

    def record_feedback(
        self,
        decree_gods: list[str],
        decree_domains: list[str],
        useful: bool,
        pantheon: dict[str, GodProfile],
    ):
        """
        Tras un decreto, el usuario indica si fue útil.
        Actualiza reputación de todos los dioses convocados en los dominios del decreto.
        """
        for god_name in decree_gods:
            if god_name not in pantheon:
                continue
            god = pantheon[god_name]
            for domain in decree_domains:
                current = god.get_reputation(domain)
                god.update_reputation(domain, useful)
                new_score = god.get_reputation(domain)
                self._upsert(god_name, domain, new_score)

    def _upsert(self, god_name: str, domain: str, score: float):
        self._conn.execute("""
            INSERT INTO reputation (god_name, domain, score, evaluations)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(god_name, domain) DO UPDATE SET
                score = excluded.score,
                evaluations = evaluations + 1
        """, (god_name, domain, score))
        self._conn.execute(
            "INSERT INTO reputation_history (god_name, domain, score, timestamp) VALUES (?, ?, ?, ?)",
            (god_name, domain, score, time.time())
        )
        self._conn.commit()

    def history(self, limit: int = 100) -> list[dict]:
        """Historial de cambios de reputación, más recientes primero."""
        rows = self._conn.execute(
            """SELECT god_name, domain, score, timestamp
               FROM reputation_history
               ORDER BY timestamp DESC LIMIT ?""",
            (limit,)
        ).fetchall()
        return [{"god_name": g, "domain": d, "score": round(s, 4), "timestamp": t}
                for g, d, s, t in rows]

    def snapshot(self) -> dict[str, dict[str, float]]:
        rows = self._conn.execute("SELECT god_name, domain, score, evaluations FROM reputation").fetchall()
        result: dict[str, dict] = {}
        for god_name, domain, score, evals in rows:
            result.setdefault(god_name, {})[domain] = {"score": round(score, 4), "evaluations": evals}
        return result
