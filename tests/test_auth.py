"""
ENLIL — Fase 2 P0: almacenamiento de API keys por hash (2026-08-29)
======================================================================
Corre contra un fichero SQLite temporal propio -- nunca toca
data/enlil.db de produccion. No usa datos reales ni claves reales.

NOTA de import: enlil.auth abre una conexion NUEVA en cada llamada a
_db() (a diferencia de MemoryStore/DecreeStore, que mantienen una
conexion persistente) -- por eso aqui NO se puede usar ":memory:" como
DB_PATH (cada conexion nueva veria una base distinta y vacia). Se usa
un fichero temporal real y se parchea auth_module.DB_PATH directamente,
igual que en test_client_isolation.py, para ser independiente del
orden de import dentro de la suite completa.
"""
import os
import sqlite3
import tempfile
import uuid

os.environ.setdefault("OPENROUTER_API_KEY", "test")

import pytest

import enlil.auth as auth_module
from enlil.auth import (
    init_auth_tables, create_client, add_key, list_keys, revoke_key,
    _validate_key, hash_api_key, key_prefix, generate_key_id,
)

_TEST_DB = os.path.join(tempfile.gettempdir(), f"enlil_auth_test_{uuid.uuid4().hex}.db")


@pytest.fixture(autouse=True)
def _use_temp_db():
    auth_module.DB_PATH = _TEST_DB
    init_auth_tables()
    yield
    try:
        os.remove(_TEST_DB)
        for ext in ("-wal", "-shm"):
            if os.path.exists(_TEST_DB + ext):
                os.remove(_TEST_DB + ext)
    except OSError:
        pass


def _raw_row(key_id: str) -> dict:
    """Lee una fila directamente, para inspeccionar qué columnas existen realmente."""
    conn = sqlite3.connect(_TEST_DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM api_keys WHERE key_id=?", (key_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


class TestHash:
    def test_deterministico(self):
        assert hash_api_key("enlil_algo123") == hash_api_key("enlil_algo123")

    def test_distinto_para_claves_distintas(self):
        assert hash_api_key("enlil_aaa") != hash_api_key("enlil_bbb")

    def test_incluye_separador_de_dominio(self):
        """El hash de la clave sola (sin separador) no debe coincidir con el real."""
        import hashlib
        raw = "enlil_algo123"
        naive = hashlib.sha256(raw.encode()).hexdigest()
        assert hash_api_key(raw) != naive

    def test_prefix_no_es_el_hash(self):
        raw = "enlil_AbCdEfGhIjKlMnOp"
        assert key_prefix(raw) == raw[:11]
        assert key_prefix(raw) != hash_api_key(raw)

    def test_key_id_no_se_deriva_del_secreto(self):
        raw = "enlil_mismovalor"
        a = generate_key_id()
        b = generate_key_id()
        assert a != b  # aleatorios, no derivados de `raw`


class TestEsquemaSinPlaintext:
    def test_create_client_no_almacena_key_en_claro(self):
        r = create_client(name="Test", email=f"t-{uuid.uuid4().hex}@test.invalid")
        conn = sqlite3.connect(_TEST_DB)
        cols = [c[1] for c in conn.execute("PRAGMA table_info(api_keys)").fetchall()]
        conn.close()
        assert "key" not in cols
        assert "key_hash" in cols and "key_id" in cols and "key_prefix" in cols

        # Ninguna fila debe contener el secreto completo en ninguna columna de texto
        conn = sqlite3.connect(_TEST_DB)
        rows = conn.execute("SELECT key_id, key_hash, key_prefix, label FROM api_keys").fetchall()
        conn.close()
        secret = r["api_key"]
        for row in rows:
            for value in row:
                assert value != secret
                if isinstance(value, str):
                    assert secret not in value

    def test_add_key_no_almacena_en_claro(self):
        r = create_client(name="Test2", email=f"t2-{uuid.uuid4().hex}@test.invalid")
        new_key = add_key(r["client_id"], label="segunda")
        conn = sqlite3.connect(_TEST_DB)
        rows = conn.execute("SELECT key_id, key_hash, key_prefix FROM api_keys WHERE client_id=?", (r["client_id"],)).fetchall()
        conn.close()
        assert any(new_key[:11] == row[2] for row in rows)  # el prefix de la nueva SÍ debe aparecer
        for row in rows:
            for value in row:
                assert value != new_key


class TestAutenticacion:
    def test_clave_correcta_autentica(self):
        r = create_client(name="A", email=f"a-{uuid.uuid4().hex}@test.invalid")
        client = _validate_key(r["api_key"])
        assert client is not None
        assert client["id"] == r["client_id"]

    def test_clave_incorrecta_no_autentica(self):
        create_client(name="B", email=f"b-{uuid.uuid4().hex}@test.invalid")
        assert _validate_key("enlil_esto_no_existe_nunca") is None

    def test_clave_revocada_no_autentica(self):
        r = create_client(name="C", email=f"c-{uuid.uuid4().hex}@test.invalid")
        keys = list_keys(r["client_id"])
        assert len(keys) == 1
        revoke_key(keys[0]["key_id"])
        assert _validate_key(r["api_key"]) is None

    def test_revocar_por_key_id_no_afecta_a_otras_claves_del_cliente(self):
        r = create_client(name="D", email=f"d-{uuid.uuid4().hex}@test.invalid")
        second_key = add_key(r["client_id"], label="segunda")
        keys = list_keys(r["client_id"])
        primary_id = next(k["key_id"] for k in keys if k["label"] == "primary")
        revoke_key(primary_id)
        assert _validate_key(r["api_key"]) is None       # la primaria, revocada
        assert _validate_key(second_key) is not None      # la segunda, intacta


class TestListadoAdminSinSecretos:
    def test_list_keys_no_expone_key_ni_hash(self):
        r = create_client(name="E", email=f"e-{uuid.uuid4().hex}@test.invalid")
        keys = list_keys(r["client_id"])
        assert len(keys) == 1
        k = keys[0]
        assert set(k.keys()) == {"key_id", "key_prefix", "label", "created_at", "expires_at", "active"}
        assert r["api_key"] not in k.values()
        assert hash_api_key(r["api_key"]) not in k.values()

    def test_list_keys_incluye_key_id_y_prefix_reconocibles(self):
        r = create_client(name="F", email=f"f-{uuid.uuid4().hex}@test.invalid")
        k = list_keys(r["client_id"])[0]
        assert k["key_prefix"] == r["api_key"][:11]
        assert isinstance(k["key_id"], str) and len(k["key_id"]) > 0


class TestForeignKeysPorConexion:
    """
    P0.2 (Codex, 2026-08-29): _db() no activaba PRAGMA foreign_keys=ON.
    SQLite exige fijarlo en cada conexión -- no persiste en el fichero
    ni se hereda de una conexión anterior.
    """

    def test_1_pragma_foreign_keys_activo_en_conexion_nueva(self):
        conn = auth_module._db()
        value = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        conn.close()
        assert value == 1

    def test_2_add_key_para_cliente_inexistente_falla(self):
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
            add_key("cliente-que-no-existe-jamas", label="intento")

    def test_3_no_queda_fila_huerfana_tras_el_fallo(self):
        try:
            add_key("cliente-que-no-existe-jamas-2", label="intento")
        except sqlite3.IntegrityError:
            pass
        conn = sqlite3.connect(_TEST_DB)
        n = conn.execute(
            "SELECT COUNT(*) FROM api_keys WHERE client_id=?",
            ("cliente-que-no-existe-jamas-2",),
        ).fetchone()[0]
        conn.close()
        assert n == 0

    def test_4_transaccion_limpia_no_dejo_conexion_a_medias(self):
        """
        Tras el fallo, una nueva operación normal debe funcionar sin
        arrastrar ningún estado corrupto de la conexión anterior
        (cada llamada abre y cierra su propia conexión).
        """
        try:
            add_key("otro-cliente-inexistente", label="intento")
        except sqlite3.IntegrityError:
            pass
        r = create_client(name="G", email=f"g-{uuid.uuid4().hex}@test.invalid")
        assert _validate_key(r["api_key"]) is not None

    def test_5_creacion_para_cliente_valido_sigue_funcionando(self):
        r = create_client(name="H", email=f"h-{uuid.uuid4().hex}@test.invalid")
        new_key = add_key(r["client_id"], label="segunda")
        assert _validate_key(new_key) is not None
        assert _validate_key(new_key)["id"] == r["client_id"]

    def test_create_client_tambien_hace_rollback_limpio(self):
        """
        create_client() inserta en clients + api_keys en la misma
        conexión -- si algo fallara a mitad, no debe quedar el cliente
        sin su key ni al revés. Se fuerza un email duplicado (UNIQUE)
        para disparar el fallo tras el primer INSERT.
        """
        email = f"dup-{uuid.uuid4().hex}@test.invalid"
        create_client(name="Original", email=email)
        with pytest.raises(sqlite3.IntegrityError):
            create_client(name="Duplicado", email=email)
        conn = sqlite3.connect(_TEST_DB)
        n_clients = conn.execute(
            "SELECT COUNT(*) FROM clients WHERE email=?", (email,)
        ).fetchone()[0]
        conn.close()
        assert n_clients == 1  # el duplicado no dejó ni cliente ni key a medias
