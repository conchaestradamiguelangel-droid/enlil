"""
ENLIL — Migración de api_keys a almacenamiento por hash (Fase 2 P0, 2026-08-29)
==================================================================================
Reconstruye la tabla `api_keys` completa dentro de una única transacción:
  key TEXT PRIMARY KEY, client_id, label, created_at, expires_at, active
->
  key_id TEXT PRIMARY KEY, key_hash TEXT NOT NULL UNIQUE, key_prefix,
  client_id, label, created_at, expires_at, active

No usa ALTER TABLE ... DROP COLUMN sobre la tabla original a propósito
(key es su PK viva) — crea api_keys_new, verifica exhaustivamente que
coincide con el original salvo el propio secreto, y solo entonces
sustituye la tabla vieja. Cualquier discrepancia aborta con ROLLBACK
antes de tocar la tabla original.

Uso:
    python3 migrate_api_keys_hash.py <ruta_a_la_db>

Nunca imprime ninguna clave completa ni su hash. Piensa en ejecutarse
SIEMPRE primero contra una COPIA de la base real, nunca contra la base
en producción directamente sin un backup y una ventana de mantenimiento
(ver el procedimiento de despliegue en el informe de la sesión).
"""
import sqlite3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from enlil.auth import hash_api_key, key_prefix as compute_key_prefix, generate_key_id


class MigrationAborted(Exception):
    """Se lanza ante cualquier discrepancia — el caller debe hacer rollback."""


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    return column in cols


def migrate_api_keys(db_path: str) -> dict:
    """
    Ejecuta la migración completa. Devuelve un resumen SIN secretos.
    Lanza MigrationAborted (y hace rollback) ante cualquier discrepancia.
    """
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row

    try:
        if _column_exists(conn, "api_keys", "key_hash"):
            raise MigrationAborted(
                "api_keys ya tiene key_hash -- parece ya migrada. Abortando sin tocar nada."
            )
        if not _column_exists(conn, "api_keys", "key"):
            raise MigrationAborted(
                "api_keys no tiene columna 'key' -- esquema inesperado. Abortando."
            )

        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("BEGIN IMMEDIATE")

        old_rows = conn.execute(
            "SELECT key, client_id, label, created_at, expires_at, active FROM api_keys"
        ).fetchall()
        n_old = len(old_rows)

        conn.execute("""
            CREATE TABLE api_keys_new (
                key_id      TEXT PRIMARY KEY,
                key_hash    TEXT NOT NULL UNIQUE,
                key_prefix  TEXT NOT NULL,
                client_id   TEXT NOT NULL,
                label       TEXT DEFAULT '',
                created_at  REAL NOT NULL,
                expires_at  REAL,
                active      INTEGER DEFAULT 1,
                FOREIGN KEY (client_id) REFERENCES clients(id)
            )
        """)

        used_key_ids = set()
        for row in old_rows:
            raw_key = row["key"]
            kid = generate_key_id()
            while kid in used_key_ids:          # colisión, improbable con 8 bytes -- por si acaso
                kid = generate_key_id()
            used_key_ids.add(kid)

            conn.execute(
                "INSERT INTO api_keys_new (key_id,key_hash,key_prefix,client_id,label,created_at,expires_at,active) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    kid,
                    hash_api_key(raw_key),
                    compute_key_prefix(raw_key),
                    row["client_id"], row["label"], row["created_at"],
                    row["expires_at"], row["active"],
                ),
            )

        # ── Verificaciones, todas dentro de la misma transacción ──────────
        n_new = conn.execute("SELECT COUNT(*) FROM api_keys_new").fetchone()[0]
        if n_new != n_old:
            raise MigrationAborted(f"conteo no coincide: {n_old} originales vs {n_new} nuevas")

        n_distinct_hash = conn.execute("SELECT COUNT(DISTINCT key_hash) FROM api_keys_new").fetchone()[0]
        if n_distinct_hash != n_old:
            raise MigrationAborted(f"key_hash no son todos únicos: {n_distinct_hash}/{n_old}")

        n_distinct_id = conn.execute("SELECT COUNT(DISTINCT key_id) FROM api_keys_new").fetchone()[0]
        if n_distinct_id != n_old:
            raise MigrationAborted(f"key_id no son todos únicos: {n_distinct_id}/{n_old}")

        # Comparación fila a fila de todo excepto el secreto (por orden
        # estable de created_at, ya que las dos tablas no comparten PK).
        old_sorted = sorted(old_rows, key=lambda r: (r["created_at"], r["client_id"]))
        new_sorted = conn.execute(
            "SELECT client_id, label, created_at, expires_at, active FROM api_keys_new "
            "ORDER BY created_at, client_id"
        ).fetchall()
        for o, n in zip(old_sorted, new_sorted):
            if (o["client_id"], o["label"], o["created_at"], o["expires_at"], o["active"]) != \
               (n["client_id"], n["label"], n["created_at"], n["expires_at"], n["active"]):
                raise MigrationAborted("una fila no conserva propietario/label/fecha/estado exactos")

        conn.execute("DROP TABLE api_keys")
        conn.execute("ALTER TABLE api_keys_new RENAME TO api_keys")
        conn.execute("CREATE INDEX idx_keys_client ON api_keys(client_id)")

        # Comprobación acotada a la tabla que tocamos -- PRAGMA
        # foreign_key_check() sin argumento revisa TODA la base y
        # abortaría por problemas preexistentes ajenos a esta migración
        # (ej. filas huérfanas históricas en usage_log/rate_buckets que
        # nada tienen que ver con api_keys). Solo nos interesa si nuestra
        # propia tabla nueva introduce una violación.
        fk_problems = conn.execute("PRAGMA foreign_key_check(api_keys)").fetchall()
        if fk_problems:
            raise MigrationAborted(f"foreign_key_check(api_keys) encontró {len(fk_problems)} problema(s)")

        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise MigrationAborted(f"integrity_check devolvió: {integrity}")

        conn.commit()

        return {
            "status": "OK",
            "filas_migradas": n_new,
            "activas": sum(1 for r in old_rows if r["active"] == 1),
            "revocadas": sum(1 for r in old_rows if r["active"] == 0),
            "key_hash_unicos": n_distinct_hash,
            "key_id_unicos": n_distinct_id,
            "foreign_key_check": "ok",
            "integrity_check": integrity,
        }

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python3 migrate_api_keys_hash.py <ruta_a_la_db>")
        sys.exit(1)
    result = migrate_api_keys(sys.argv[1])
    print(result)
