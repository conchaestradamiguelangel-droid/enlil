"""ENLIL — Persistencia de jobs de análisis en SQLite."""
from __future__ import annotations

import json
import sqlite3
import threading
import time


class JobStore:
    """Almacén persistente de jobs. Sobrevive reinicios del servicio."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        with self._lock, self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id      TEXT PRIMARY KEY,
                    status      TEXT NOT NULL DEFAULT 'running',
                    progress    INTEGER DEFAULT 0,
                    total       INTEGER DEFAULT 0,
                    completed   TEXT DEFAULT '[]',
                    result      TEXT,
                    error       TEXT,
                    created_at  REAL,
                    updated_at  REAL
                )
            """)
            # Jobs 'running' al iniciar = interrumpidos por reinicio
            conn.execute(
                "UPDATE jobs SET status='interrupted', "
                "error='Interrumpido por reinicio del servicio' "
                "WHERE status='running'"
            )
            conn.commit()

    def create(self, job_id: str, total: int) -> dict:
        now = time.time()
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO jobs (job_id, status, progress, total, completed, created_at, updated_at) "
                "VALUES (?, 'running', 0, ?, '[]', ?, ?)",
                (job_id, total, now, now),
            )
            conn.commit()
        return self.get(job_id)

    def get(self, job_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        if not row:
            return None
        return {
            "job_id":    row["job_id"],
            "status":    row["status"],
            "progress":  row["progress"],
            "total":     row["total"],
            "completed": json.loads(row["completed"] or "[]"),
            "result":    json.loads(row["result"]) if row["result"] else None,
            "error":     row["error"],
        }

    def add_completed(self, job_id: str, doc: dict):
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT progress, completed FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if row:
                completed = json.loads(row["completed"] or "[]")
                completed.append(doc)
                conn.execute(
                    "UPDATE jobs SET progress = ?, completed = ?, updated_at = ? WHERE job_id = ?",
                    (row["progress"] + 1, json.dumps(completed), time.time(), job_id),
                )
                conn.commit()

    def finish(self, job_id: str, result: dict):
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT total FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            total = row["total"] if row else 0
            conn.execute(
                "UPDATE jobs SET status = 'done', progress = ?, result = ?, updated_at = ? WHERE job_id = ?",
                (total, json.dumps(result), time.time(), job_id),
            )
            conn.commit()

    def fail(self, job_id: str, error: str):
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE jobs SET status = 'error', error = ?, updated_at = ? WHERE job_id = ?",
                (error, time.time(), job_id),
            )
            conn.commit()

    def list_recent(self, limit: int = 20) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT job_id, status, progress, total, created_at, updated_at "
                "FROM jobs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "job_id":     r["job_id"],
                "status":     r["status"],
                "progress":   r["progress"],
                "total":      r["total"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]

    def __contains__(self, job_id: str) -> bool:
        return self.get(job_id) is not None
