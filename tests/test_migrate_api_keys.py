"""
ENLIL — Fase 2 P0: migración transaccional de api_keys (2026-08-29)
======================================================================
Pruebas deterministas sobre datos sintéticos (nunca reales) que
demuestran que scripts/migrate_api_keys_hash.py:
  - migra correctamente un esquema viejo válido;
  - es idempotente (abortar limpio si ya está migrado);
  - hace ROLLBACK completo ante cualquier discrepancia forzada, sin
    dejar la tabla a medias.

El ensayo real contra una copia de la base de producción (13 filas
reales) se documenta aparte en el informe de la sesión -- no forma
parte de esta suite automática porque depende de un fichero externo
que no existe en un checkout limpio del repositorio.
"""
import os
import sqlite3
import sys
import tempfile
import time
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch

import migrate_api_keys_hash as migration
from enlil.auth import hash_api_key


def _make_old_schema_db(rows):
    """
    Crea un fichero SQLite temporal con el ESQUEMA VIEJO de api_keys
    (key en claro como PK) + la tabla clients mínima necesaria para la
    FK, poblado con `rows` = [(key, client_id, label, active), ...].
    Los client_id se crean también en `clients` para que
    foreign_key_check tenga algo válido que comprobar.
    """
    path = os.path.join(tempfile.gettempdir(), f"enlil_migrate_test_{uuid.uuid4().hex}.db")
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE clients (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
            plan TEXT DEFAULT 'standard', monthly_token_budget INTEGER DEFAULT 500000,
            max_requests_per_hour INTEGER DEFAULT 30, max_total_requests INTEGER,
            monthly_decrees_limit INTEGER, active INTEGER DEFAULT 1,
            created_at REAL NOT NULL, notes TEXT DEFAULT ''
        );
        CREATE TABLE api_keys (
            key TEXT PRIMARY KEY, client_id TEXT NOT NULL, label TEXT DEFAULT '',
            created_at REAL NOT NULL, expires_at REAL, active INTEGER DEFAULT 1,
            FOREIGN KEY (client_id) REFERENCES clients(id)
        );
    """)
    seen_clients = set()
    now = time.time()
    for key, client_id, label, active in rows:
        if client_id not in seen_clients:
            conn.execute(
                "INSERT INTO clients (id,name,email,created_at) VALUES (?,?,?,?)",
                (client_id, f"Cliente {client_id}", f"{client_id}@test.invalid", now),
            )
            seen_clients.add(client_id)
        conn.execute(
            "INSERT INTO api_keys (key,client_id,label,created_at,active) VALUES (?,?,?,?,?)",
            (key, client_id, label, now, active),
        )
    conn.commit()
    conn.close()
    return path


def _cleanup(path):
    try:
        os.remove(path)
        for ext in ("-wal", "-shm"):
            if os.path.exists(path + ext):
                os.remove(path + ext)
    except OSError:
        pass


SYNTHETIC_ROWS = [
    ("enlil_sinteticaA1111111111111111111111111", "cliA", "primary", 1),
    ("enlil_sinteticaB2222222222222222222222222", "cliB", "primary", 1),
    ("enlil_sinteticaC3333333333333333333333333", "cliC", "primary", 0),  # revocada
]


class TestMigracionExitosa:
    def setup_method(self):
        self.db_path = _make_old_schema_db(SYNTHETIC_ROWS)

    def teardown_method(self):
        _cleanup(self.db_path)

    def test_migra_todas_las_filas(self):
        result = migration.migrate_api_keys(self.db_path)
        assert result["status"] == "OK"
        assert result["filas_migradas"] == 3
        assert result["activas"] == 2
        assert result["revocadas"] == 1
        assert result["foreign_key_check"] == "ok"
        assert result["integrity_check"] == "ok"

    def test_esquema_final_sin_columna_key(self):
        migration.migrate_api_keys(self.db_path)
        conn = sqlite3.connect(self.db_path)
        cols = [c[1] for c in conn.execute("PRAGMA table_info(api_keys)").fetchall()]
        conn.close()
        assert "key" not in cols
        assert set(cols) == {"key_id", "key_hash", "key_prefix", "client_id", "label", "created_at", "expires_at", "active"}

    def test_hashes_y_key_ids_unicos_y_correctos(self):
        migration.migrate_api_keys(self.db_path)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT key_id, key_hash, key_prefix, client_id, active FROM api_keys").fetchall()
        conn.close()
        assert len({r["key_id"] for r in rows}) == 3
        assert len({r["key_hash"] for r in rows}) == 3
        expected_hashes = {hash_api_key(k) for k, _, _, _ in SYNTHETIC_ROWS}
        assert {r["key_hash"] for r in rows} == expected_hashes

    def test_activas_autentican_revocada_no(self):
        migration.migrate_api_keys(self.db_path)
        conn = sqlite3.connect(self.db_path)
        for raw_key, client_id, label, active in SYNTHETIC_ROWS:
            row = conn.execute(
                "SELECT active FROM api_keys WHERE key_hash=?", (hash_api_key(raw_key),)
            ).fetchone()
            assert row is not None, f"clave de {client_id} no encontrada tras migrar"
            assert row[0] == active, f"estado active no coincide para {client_id}"
        conn.close()

    def test_idempotente_aborta_si_ya_migrada(self):
        migration.migrate_api_keys(self.db_path)
        with pytest.raises(migration.MigrationAborted):
            migration.migrate_api_keys(self.db_path)


class TestRollbackAnteFalloSimulado:
    def setup_method(self):
        self.db_path = _make_old_schema_db(SYNTHETIC_ROWS)

    def teardown_method(self):
        _cleanup(self.db_path)

    def test_rollback_si_hash_forzado_a_colisionar(self):
        """
        Fuerza a que TODAS las filas produzcan el mismo key_hash (como si
        el algoritmo de hash estuviera roto) para comprobar que la tabla
        original queda intacta. La propia restricción UNIQUE del esquema
        (no solo la verificación en Python de después) ya rechaza el
        INSERT duplicado con sqlite3.IntegrityError -- una segunda capa
        de seguridad más fuerte que mi propio guard, que ni siquiera
        llega a ejecutarse en este caso.
        """
        with patch.object(migration, "hash_api_key", return_value="hash-siempre-igual"):
            with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed"):
                migration.migrate_api_keys(self.db_path)

        # La tabla original NO debe haberse tocado -- sigue con el
        # esquema viejo y las 3 filas originales intactas.
        conn = sqlite3.connect(self.db_path)
        cols = [c[1] for c in conn.execute("PRAGMA table_info(api_keys)").fetchall()]
        assert "key" in cols and "key_hash" not in cols
        n = conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
        assert n == 3
        # No debe quedar ninguna tabla intermedia huérfana
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        assert "api_keys_new" not in tables
        conn.close()

    def test_rollback_si_client_id_huerfano(self):
        """
        Inserta una fila de api_keys que apunta a un client_id
        inexistente en clients -- viola la FK a propósito. Con
        PRAGMA foreign_keys=ON (que el script activa explícitamente),
        SQLite rechaza el INSERT en el momento mismo de la copia, antes
        de que mi propio PRAGMA foreign_key_check posterior llegue a
        ejecutarse -- otra capa de seguridad más fuerte que mi guard.
        """
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO api_keys (key,client_id,label,created_at,active) VALUES (?,?,?,?,1)",
            ("enlil_sinteticaD4444444444444444444444444", "cliente-inexistente", "primary", time.time()),
        )
        conn.commit()
        conn.close()

        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
            migration.migrate_api_keys(self.db_path)

        conn = sqlite3.connect(self.db_path)
        cols = [c[1] for c in conn.execute("PRAGMA table_info(api_keys)").fetchall()]
        assert "key" in cols  # esquema viejo intacto, rollback aplicado
        n = conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
        assert n == 4  # las 3 originales + la fila rota que insertamos, sin migrar
        conn.close()
