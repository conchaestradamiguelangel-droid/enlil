import logging
import sqlite3
import os
from .decrees.decree import Decree

DEFAULT_DB = os.environ.get("ENLIL_DB", "enlil.db")


logger = logging.getLogger("enlil.memory")

class MemoryStore:
    """
    Memoria de decretos pasados para enriquecer consultas futuras.
    Fase 1: SQLite FTS5 (búsqueda full-text eficiente, sin dependencias externas).
    Fase 2: Qdrant cuando haya volumen suficiente para embeddings.
    """

    def __init__(self, db_path: str = DEFAULT_DB, connection: sqlite3.Connection | None = None):
        self._conn = connection if connection is not None else sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS memory_entries (
                decree_id TEXT PRIMARY KEY,
                timestamp REAL NOT NULL,
                query TEXT NOT NULL,
                synthesis TEXT NOT NULL,
                domains TEXT NOT NULL,
                gods TEXT NOT NULL
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
            USING fts5(decree_id UNINDEXED, query, synthesis, domains, content=memory_entries, content_rowid=rowid);

            CREATE TRIGGER IF NOT EXISTS memory_ai AFTER INSERT ON memory_entries BEGIN
                INSERT INTO memory_fts(rowid, decree_id, query, synthesis, domains)
                VALUES (new.rowid, new.decree_id, new.query, new.synthesis, new.domains);
            END;
        """)
        self._conn.commit()

    def store(self, decree: Decree):
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO memory_entries VALUES (?,?,?,?,?,?)",
                (
                    decree.id,
                    decree.timestamp,
                    decree.query,
                    decree.synthesis,
                    " ".join(decree.domains),
                    " ".join(decree.gods_convened),
                ),
            )
            self._conn.commit()
        except Exception as e:
            logger.debug("MemoryStore.store failed: %s", e)

    def search(self, query: str, limit: int = 3) -> str:
        """Búsqueda FTS5 en decretos anteriores."""
        try:
            rows = self._conn.execute(
                """
                SELECT m.query, m.synthesis
                FROM memory_fts f
                JOIN memory_entries m ON f.decree_id = m.decree_id
                WHERE memory_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (self._sanitize(query), limit),
            ).fetchall()

            if not rows:
                return ""

            parts = []
            for q, s in rows:
                parts.append(f"- Consulta: {q[:100]}\n  Síntesis: {s[:200]}")
            return "\n".join(parts)

        except Exception:
            return ""

    def _sanitize(self, query: str) -> str:
        words = [w for w in re.split(r'\W+', query) if len(w) >= 2 and w.isalpha()]
        if not words:
            return '""'
        return " OR ".join(f'"{w}"' for w in words[:5])
    def prune(self, max_entries: int = 500):
        """Elimina decretos mas antiguos si supera max_entries."""
        count = self._conn.execute("SELECT COUNT(*) FROM memory_entries").fetchone()[0]
        if count <= max_entries:
            return
        excess = count - max_entries
        self._conn.execute(
            "DELETE FROM memory_entries WHERE decree_id IN "
            "(SELECT decree_id FROM memory_entries ORDER BY timestamp ASC LIMIT ?)",
            (excess,),
        )
        self._conn.execute("INSERT INTO memory_fts(memory_fts) VALUES('rebuild')")
        self._conn.commit()
