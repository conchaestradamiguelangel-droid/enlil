"""TEST 01B — migración de esquema, backfill V1, postcondición de firma
(ENLIL_TEST01B_AUDITORIA_DISENO_V3/V4/V6.md §10). Incluye ensayo obligatorio
contra una COPIA real de la base de producción -- nunca contra el fichero
vivo."""
import os
import shutil
import sqlite3
import pytest

from enlil.decrees.store import DecreeStore, SchemaMismatchError, _EXPECTED_SCHEMA
from enlil.decrees.decree import Decree, GodVoice
from enlil.quantum import verify_decree

REAL_DB_COPY = os.path.join(os.path.dirname(__file__), "..", "data", "enlil_migration_test.db")


def _fresh_copy(tmp_path, name="mig.db"):
    dst = str(tmp_path / name)
    shutil.copy(REAL_DB_COPY, dst)
    return dst


# ── 1. Migración sobre copia del esquema actual real ────────────────────

@pytest.mark.skipif(not os.path.exists(REAL_DB_COPY), reason="copia de producción no disponible en este entorno")
class TestMigracionSobreCopiaReal:
    def test_migracion_anade_columnas_definitivas(self, tmp_path):
        db_path = _fresh_copy(tmp_path)
        store = DecreeStore(db_path=db_path)
        cols = {r[1] for r in store._connection.execute("PRAGMA table_info(decrees)").fetchall()}
        for expected_col in _EXPECTED_SCHEMA:
            assert expected_col in cols, f"falta columna {expected_col}"

    def test_backfill_v1_solo_para_decretos_firmados(self, tmp_path):
        db_path = _fresh_copy(tmp_path)
        conn_before = sqlite3.connect(db_path)
        signed_before = conn_before.execute(
            "SELECT COUNT(*) FROM decrees WHERE pq_signature IS NOT NULL"
        ).fetchone()[0]
        unsigned_before = conn_before.execute(
            "SELECT COUNT(*) FROM decrees WHERE pq_signature IS NULL"
        ).fetchone()[0]
        conn_before.close()
        assert signed_before > 0, "la copia de producción debería tener decretos firmados"

        store = DecreeStore(db_path=db_path)
        signed_v1 = store._connection.execute(
            "SELECT COUNT(*) FROM decrees WHERE pq_signature IS NOT NULL AND signature_payload_version = 1"
        ).fetchone()[0]
        unsigned_no_version = store._connection.execute(
            "SELECT COUNT(*) FROM decrees WHERE pq_signature IS NULL AND signature_payload_version IS NULL"
        ).fetchone()[0]
        assert signed_v1 == signed_before, "todos los decretos firmados deben recibir version=1"
        assert unsigned_no_version == unsigned_before, "los no firmados NO reciben version=1 falsamente"

    def test_firma_v1_real_historica_sigue_verificando(self, tmp_path):
        """El test más importante: ninguna firma ya emitida se invalida."""
        db_path = _fresh_copy(tmp_path)
        store = DecreeStore(db_path=db_path)
        rows = store._connection.execute(
            "SELECT id, query, synthesis, timestamp, pq_signature, signature_payload_version "
            "FROM decrees WHERE pq_signature IS NOT NULL ORDER BY timestamp DESC LIMIT 20"
        ).fetchall()
        assert len(rows) > 0
        for row in rows:
            assert row["signature_payload_version"] == 1
            valid = verify_decree(
                row["id"], row["query"], row["synthesis"], row["timestamp"], row["pq_signature"],
                payload_version=1,
            )
            assert valid is True, f"firma histórica {row['id']} dejó de verificar tras la migración"

    def test_postcondicion_pasa_tras_migracion_real(self, tmp_path):
        db_path = _fresh_copy(tmp_path)
        store = DecreeStore(db_path=db_path)  # no debe lanzar SchemaMismatchError
        n = store._connection.execute(
            "SELECT COUNT(*) FROM decrees WHERE pq_signature IS NOT NULL AND signature_payload_version IS NULL"
        ).fetchone()[0]
        assert n == 0

    def test_segunda_ejecucion_no_repite_backfill(self, tmp_path):
        db_path = _fresh_copy(tmp_path)
        DecreeStore(db_path=db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        one_id = conn.execute(
            "SELECT id FROM decrees WHERE pq_signature IS NOT NULL LIMIT 1"
        ).fetchone()["id"]
        # Simula la anomalía de la §V4 7.3: alguien resetea la versión a NULL
        # manualmente DESPUÉS de la primera migración.
        conn.execute("UPDATE decrees SET signature_payload_version = NULL WHERE id = ?", (one_id,))
        conn.commit()
        conn.close()

        # Segunda apertura -- la postcondición debe abortar (no repara en silencio).
        with pytest.raises(SchemaMismatchError):
            DecreeStore(db_path=db_path)


# ── 2. Casos sintéticos: esquema parcial / incompatible / rollback ──────

class TestMigracionCasosSinteticos:
    def _minimal_decrees_table(self, conn):
        conn.execute(
            """CREATE TABLE decrees (
                id TEXT PRIMARY KEY, timestamp REAL NOT NULL, query TEXT NOT NULL,
                domains TEXT NOT NULL, gods_convened TEXT NOT NULL, voices TEXT NOT NULL,
                synthesis TEXT NOT NULL, total_tokens INTEGER NOT NULL, budget_tier TEXT NOT NULL,
                parent_decree_id TEXT, has_dissent INTEGER NOT NULL DEFAULT 0,
                pq_signature TEXT, vertical TEXT NOT NULL DEFAULT 'general',
                predicted_scores TEXT NOT NULL DEFAULT '{}', client_id TEXT NOT NULL DEFAULT 'default'
            )"""
        )
        conn.commit()

    def test_esquema_parcialmente_migrado(self, tmp_path):
        """Solo 2 de las 7 columnas nuevas ya existen -- la migración
        añade el resto sin fallar por las que ya están."""
        db_path = str(tmp_path / "partial.db")
        conn = sqlite3.connect(db_path)
        self._minimal_decrees_table(conn)
        conn.execute("ALTER TABLE decrees ADD COLUMN status TEXT DEFAULT NULL")
        conn.execute("ALTER TABLE decrees ADD COLUMN wall_clock_ms REAL DEFAULT NULL")
        conn.commit()
        conn.close()

        store = DecreeStore(db_path=db_path)
        cols = {r[1] for r in store._connection.execute("PRAGMA table_info(decrees)").fetchall()}
        for expected_col in _EXPECTED_SCHEMA:
            assert expected_col in cols

    def test_columna_existente_con_default_incompatible_aborta(self, tmp_path):
        """DEFAULT 'complete' en vez de NULL -- nombre/tipo coinciden,
        pero el default falsificaría históricos. Debe abortar."""
        db_path = str(tmp_path / "bad_default.db")
        conn = sqlite3.connect(db_path)
        self._minimal_decrees_table(conn)
        conn.execute("ALTER TABLE decrees ADD COLUMN status TEXT DEFAULT 'complete'")
        conn.commit()
        conn.close()

        with pytest.raises(SchemaMismatchError):
            DecreeStore(db_path=db_path)

    def test_columna_existente_tipo_incompatible_aborta(self, tmp_path):
        db_path = str(tmp_path / "bad_type.db")
        conn = sqlite3.connect(db_path)
        self._minimal_decrees_table(conn)
        conn.execute("ALTER TABLE decrees ADD COLUMN status INTEGER DEFAULT NULL")
        conn.commit()
        conn.close()

        with pytest.raises(SchemaMismatchError):
            DecreeStore(db_path=db_path)

    def test_fallo_forzado_a_mitad_hace_rollback_completo(self, tmp_path):
        """Simula un fallo en la 3ª ALTER TABLE -- ninguna columna de ese
        intento debe quedar añadida (atomicidad real de la migración).
        sqlite3.Connection es un tipo inmutable (no se puede monkeypatchear
        su clase) -- se envuelve la conexión real en un proxy delgado que
        intercepta solo `execute`, reenviando todo lo demás."""
        db_path = str(tmp_path / "rollback.db")
        real_conn = sqlite3.connect(db_path)
        real_conn.row_factory = sqlite3.Row
        self._minimal_decrees_table(real_conn)

        call_count = {"alters": 0}

        class FlakyConnectionProxy:
            def __init__(self, inner):
                self._inner = inner

            def execute(self, sql, *args, **kwargs):
                if isinstance(sql, str) and sql.strip().startswith("ALTER TABLE decrees ADD COLUMN"):
                    call_count["alters"] += 1
                    if call_count["alters"] == 3:
                        raise sqlite3.OperationalError("fallo simulado a mitad de migración")
                return self._inner.execute(sql, *args, **kwargs)

            def __getattr__(self, name):
                return getattr(self._inner, name)

        proxy = FlakyConnectionProxy(real_conn)
        with pytest.raises(sqlite3.OperationalError):
            DecreeStore(connection=proxy)

        # Reabrir con una conexión normal -- ninguna columna nueva debe existir.
        conn2 = sqlite3.connect(db_path)
        cols = {r[1] for r in conn2.execute("PRAGMA table_info(decrees)").fetchall()}
        conn2.close()
        added_any = any(c in cols for c in _EXPECTED_SCHEMA)
        assert not added_any, "el rollback debe deshacer TODAS las columnas del intento fallido"


# ── 3. Postcondición: fila nueva defectuosa (firmado + versión NULL) ────

class TestPostcondicionFirmaHistorica:
    def test_fila_firmada_sin_version_aborta_arranque(self, tmp_path):
        db_path = str(tmp_path / "corrupt.db")
        store = DecreeStore(db_path=db_path)  # crea esquema limpio, migración completa
        store._connection.execute(
            "INSERT INTO decrees (id, timestamp, query, domains, gods_convened, voices, synthesis, "
            "total_tokens, budget_tier, pq_signature, signature_payload_version) "
            "VALUES ('x', 0, 'q', '[]', '[]', '[]', 's', 0, 'standard', 'firma_falsa', NULL)"
        )
        store._connection.commit()

        with pytest.raises(SchemaMismatchError):
            store._assert_signature_version_invariant()

    def test_fila_sin_firma_y_sin_version_no_viola_invariante(self, tmp_path):
        db_path = str(tmp_path / "clean.db")
        store = DecreeStore(db_path=db_path)
        store._connection.execute(
            "INSERT INTO decrees (id, timestamp, query, domains, gods_convened, voices, synthesis, "
            "total_tokens, budget_tier, pq_signature, signature_payload_version) "
            "VALUES ('y', 0, 'q', '[]', '[]', '[]', 's', 0, 'standard', NULL, NULL)"
        )
        store._connection.commit()
        store._assert_signature_version_invariant()  # no debe lanzar
