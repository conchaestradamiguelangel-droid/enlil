import sqlite3
import json
import os
from .decree import Decree, GodVoice
from ..quantum import sign_decree, verify_decree

DEFAULT_DB = os.environ.get("ENLIL_DB", "enlil.db")


class DecreeStore:
    def __init__(self, db_path: str = DEFAULT_DB, connection: sqlite3.Connection | None = None):
        if connection is not None:
            self._connection = connection
        else:
            self._connection = sqlite3.connect(db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS decrees (
                id TEXT PRIMARY KEY,
                timestamp REAL NOT NULL,
                query TEXT NOT NULL,
                domains TEXT NOT NULL,
                gods_convened TEXT NOT NULL,
                voices TEXT NOT NULL,
                synthesis TEXT NOT NULL,
                total_tokens INTEGER NOT NULL,
                budget_tier TEXT NOT NULL,
                parent_decree_id TEXT,
                has_dissent INTEGER NOT NULL DEFAULT 0,
                pq_signature TEXT,
                vertical TEXT NOT NULL DEFAULT 'general',
                predicted_scores TEXT NOT NULL DEFAULT '{}'
            )"""
        )
        for col, sql in [
            ("client_id",       "ALTER TABLE decrees ADD COLUMN client_id TEXT NOT NULL DEFAULT 'default'"),
            ("pq_signature", "ALTER TABLE decrees ADD COLUMN pq_signature TEXT"),
            ("vertical",     "ALTER TABLE decrees ADD COLUMN vertical TEXT NOT NULL DEFAULT 'general'"),
            ("predicted_scores", "ALTER TABLE decrees ADD COLUMN predicted_scores TEXT NOT NULL DEFAULT '{}'"),
        ]:
            if not self._column_exists(col):
                self._connection.execute(sql)
        self._connection.commit()

    def _column_exists(self, column: str) -> bool:
        cols = [r[1] for r in self._connection.execute("PRAGMA table_info(decrees)").fetchall()]
        return column in cols

    def save(self, decree: Decree, client_id: str = "default"):
        voices_data = [
            {"god_name": v.god_name, "model": v.model, "content": v.content,
             "tokens_used": v.tokens_used, "latency_ms": v.latency_ms, "dissent": v.dissent}
            for v in decree.voices
        ]
        pq_sig = sign_decree(decree.id, decree.query, decree.synthesis, decree.timestamp)
        decree.pq_signature = pq_sig or None
        self._connection.execute(
            "INSERT INTO decrees VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (decree.id, decree.timestamp, decree.query,
             json.dumps(decree.domains), json.dumps(decree.gods_convened),
             json.dumps(voices_data), decree.synthesis, decree.total_tokens,
             decree.budget_tier, decree.parent_decree_id,
             1 if decree.has_dissent() else 0, decree.pq_signature,
             getattr(decree, "vertical", "general"),
             json.dumps(getattr(decree, "predicted_scores", {})),
             client_id),
        )
        self._connection.commit()

    def get(self, decree_id: str) -> Decree | None:
        row = self._connection.execute(
            "SELECT * FROM decrees WHERE id = ?", (decree_id,)
        ).fetchone()
        return self._row_to_decree(row) if row else None

    def recent(self, limit: int = 20, client_id=None) -> list[Decree]:
        if client_id:
            rows = self._connection.execute(
                "SELECT * FROM decrees WHERE client_id = ? ORDER BY timestamp DESC LIMIT ?",
                (client_id, limit)
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT * FROM decrees ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_decree(r) for r in rows]
    def count(self) -> int:
        row = self._connection.execute("SELECT COUNT(*) FROM decrees").fetchone()
        return row[0] if row else 0

    def _row_to_decree(self, row) -> Decree:
        r = dict(row)
        voices_raw = json.loads(r["voices"])
        voices = [
            GodVoice(god_name=v["god_name"], model=v["model"], content=v["content"],
                     tokens_used=v["tokens_used"], latency_ms=v["latency_ms"],
                     dissent=v.get("dissent"))
            for v in voices_raw
        ]
        obj = Decree(
            id=r["id"], timestamp=r["timestamp"], query=r["query"],
            domains=json.loads(r["domains"]), gods_convened=json.loads(r["gods_convened"]),
            voices=voices, synthesis=r["synthesis"], total_tokens=r["total_tokens"],
            budget_tier=r["budget_tier"], parent_decree_id=r["parent_decree_id"],
            pq_signature=r.get("pq_signature"),
        )
        obj.vertical = r.get("vertical", "general")
        obj.predicted_scores = json.loads(r.get("predicted_scores", "{}") or "{}")
        return obj

    def verify(self, decree_id: str) -> dict:
        decree = self.get(decree_id)
        if not decree:
            return {"valid": False, "reason": "decreto no encontrado"}
        if not decree.pq_signature:
            return {"valid": False, "reason": "decreto sin firma PQ (anterior a S7)"}
        valid = verify_decree(decree.id, decree.query, decree.synthesis, decree.timestamp, decree.pq_signature)
        return {
            "valid": valid,
            "decree_id": decree_id,
            "algorithm": "ML-DSA-87",
            "reason": "firma valida" if valid else "firma invalida o decreto manipulado",
        }
