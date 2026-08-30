"""
ENLIL — Aislamiento entre clientes (P0, auditoria 2026-08-29)
================================================================
Reproduce y cierra el hallazgo confirmado: `Decree` no conservaba
`client_id`, `_row_to_decree()` no lo restauraba desde SQLite, y por
tanto el control de ownership de api.py trataba cualquier decreto
como "default" y no bloqueaba nada.

Corre contra una base SQLite TEMPORAL propia — nunca toca
data/enlil.db de produccion. No usa datos reales ni llama a ningun
modelo/LLM real (los decretos de prueba se siembran directamente via
DecreeStore, sin pasar por /query).
"""
import os
import uuid
import tempfile

os.environ.setdefault("OPENROUTER_API_KEY", "test")

import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

import enlil.auth as auth_module
from enlil.auth import init_auth_tables, create_client
from enlil.decrees.decree import Decree, GodVoice
from enlil.decrees.store import DecreeStore
from enlil.orchestrator import Orchestrator
from enlil.gods.base import GodResponse


def _mock_god_response(content: str = "respuesta mock") -> GodResponse:
    return GodResponse(
        god_name="claude", model="mock/model", content=content,
        tokens_used=10, latency_ms=50.0,
    )

_TEST_DB = os.path.join(tempfile.gettempdir(), f"enlil_isolation_test_{uuid.uuid4().hex}.db")


def _headers(api_key: str) -> dict:
    return {"X-Api-Key": api_key}


@pytest.fixture(scope="module")
def env():
    """
    Arranca la app real (sin mockear Orchestrator ni require_auth) contra
    una base SQLite temporal propia — nunca toca data/enlil.db de
    producción. Crea 2 clientes reales (A y B, vía enlil.auth de verdad)
    y 2 decretos, uno propiedad de cada uno.

    NOTA: `enlil.auth.DB_PATH` y `enlil.decrees.store.DEFAULT_DB` se leen
    de la env var ENLIL_DB una sola vez, al importar esos módulos por
    primera vez en todo el proceso de pytest — si otro fichero de test ya
    los importó antes (ej. test_api.py con ENLIL_DB=":memory:"), fijar la
    env var aquí no tiene efecto. Por eso se parchea `auth_module.DB_PATH`
    directamente (las funciones de auth.py lo releen en cada llamada) y
    se construye el Orchestrator explícitamente con db_path=_TEST_DB en
    vez de confiar en el default congelado — así el test es independiente
    del orden de import dentro de la suite completa.
    """
    auth_module.DB_PATH = _TEST_DB
    init_auth_tables()
    a = create_client(name="Test Client A", email=f"a-{uuid.uuid4().hex}@test.invalid")
    b = create_client(name="Test Client B", email=f"b-{uuid.uuid4().hex}@test.invalid")

    seed_store = DecreeStore(db_path=_TEST_DB)

    decree_a = Decree(
        query="consulta confidencial de A", domains=["technical"],
        gods_convened=["claude"],
        voices=[GodVoice("claude", "claude-sonnet", "respuesta para A", 10, 50.0)],
        synthesis="sintesis de A", total_tokens=10,
        status="complete", signature_payload_version=2,
    )
    seed_store.save(decree_a, client_id=a["client_id"])

    decree_b = Decree(
        query="consulta confidencial de B", domains=["technical"],
        gods_convened=["claude"],
        voices=[GodVoice("claude", "claude-sonnet", "respuesta para B", 10, 50.0)],
        synthesis="sintesis de B", total_tokens=10,
        status="complete", signature_payload_version=2,
    )
    seed_store.save(decree_b, client_id=b["client_id"])
    seed_store._connection.close()

    with patch("openai.AsyncOpenAI"):
        import api as api_module
        with TestClient(api_module.app) as c:
            # El lifespan ya creó api_module.enlil con el DEFAULT_DB que
            # estuviera congelado en este proceso — lo sustituimos por un
            # Orchestrator apuntando explícitamente a nuestra base, para
            # no depender de qué test se importó primero.
            api_module.enlil = Orchestrator(db_path=_TEST_DB)
            yield {
                "client": c, "a": a, "b": b,
                "decree_a_id": decree_a.id, "decree_b_id": decree_b.id,
                "orch": api_module.enlil,
            }

    try:
        os.remove(_TEST_DB)
        for ext in ("-wal", "-shm"):
            if os.path.exists(_TEST_DB + ext):
                os.remove(_TEST_DB + ext)
    except OSError:
        pass


class TestAislamientoLectura:
    """Tests 1-4 del encargo: lectura y exportación propias vs ajenas."""

    def test_1_a_lee_su_propio_decreto(self, env):
        r = env["client"].get(f"/decree/{env['decree_a_id']}", headers=_headers(env["a"]["api_key"]))
        assert r.status_code == 200
        assert r.json()["query"] == "consulta confidencial de A"

    def test_2_b_lee_su_propio_decreto(self, env):
        r = env["client"].get(f"/decree/{env['decree_b_id']}", headers=_headers(env["b"]["api_key"]))
        assert r.status_code == 200
        assert r.json()["query"] == "consulta confidencial de B"

    def test_3_a_no_puede_leer_decreto_de_b(self, env):
        r = env["client"].get(f"/decree/{env['decree_b_id']}", headers=_headers(env["a"]["api_key"]))
        assert r.status_code == 403

    def test_3b_b_no_puede_leer_decreto_de_a(self, env):
        """Simétrico — la protección no puede depender de quién pregunta."""
        r = env["client"].get(f"/decree/{env['decree_a_id']}", headers=_headers(env["b"]["api_key"]))
        assert r.status_code == 403

    def test_4_a_no_puede_exportar_decreto_de_b(self, env):
        r = env["client"].get(
            f"/decree/{env['decree_b_id']}/export?format=json",
            headers=_headers(env["a"]["api_key"]),
        )
        assert r.status_code == 403

    def test_4b_a_no_puede_exportar_decreto_de_b_markdown(self, env):
        r = env["client"].get(
            f"/decree/{env['decree_b_id']}/export?format=md",
            headers=_headers(env["a"]["api_key"]),
        )
        assert r.status_code == 403


class TestAislamientoEmailYFeedback:
    """Tests 5-8 del encargo."""

    def test_5_a_no_puede_enviar_por_email_decreto_de_b(self, env):
        with patch("smtplib.SMTP"):
            r = env["client"].post(
                f"/decree/{env['decree_b_id']}/email",
                json={"to": "destino@test.invalid"},
                headers=_headers(env["a"]["api_key"]),
            )
        assert r.status_code == 403

    def test_6_a_no_puede_dar_feedback_sobre_decreto_de_b(self, env):
        r = env["client"].post(
            f"/feedback/{env['decree_b_id']}",
            json={"useful": True},
            headers=_headers(env["a"]["api_key"]),
        )
        assert r.status_code == 403

    def test_7_feedback_sin_autenticacion_se_rechaza(self, env):
        r = env["client"].post(
            f"/feedback/{env['decree_a_id']}",
            json={"useful": True},
        )  # sin X-Api-Key
        assert r.status_code == 401

    def test_8_doc_upload_sin_autenticacion_se_rechaza(self, env):
        r = env["client"].post(
            "/doc/upload",
            files={"file": ("test.txt", b"contenido de prueba, sin datos sensibles", "text/plain")},
        )  # sin X-Api-Key
        assert r.status_code == 401


class TestFuncionamientoNormalPreservado:
    """Test 9 del encargo — un cliente legítimo no queda roto por el fix."""

    def test_9a_a_puede_dar_feedback_sobre_su_propio_decreto(self, env):
        r = env["client"].post(
            f"/feedback/{env['decree_a_id']}",
            json={"useful": True},
            headers=_headers(env["a"]["api_key"]),
        )
        assert r.status_code == 200
        assert r.json() == {"ok": True}

    def test_9b_a_puede_exportar_su_propio_decreto(self, env):
        r = env["client"].get(
            f"/decree/{env['decree_a_id']}/export?format=json",
            headers=_headers(env["a"]["api_key"]),
        )
        assert r.status_code == 200

    def test_9c_a_puede_enviar_por_email_su_propio_decreto(self, env):
        with patch("smtplib.SMTP"), patch.dict(
            os.environ, {"GMAIL_USER": "test@test.invalid", "GMAIL_APP_PASSWORD": "x"}
        ):
            r = env["client"].post(
                f"/decree/{env['decree_a_id']}/email",
                json={"to": "destino@test.invalid"},
                headers=_headers(env["a"]["api_key"]),
            )
        assert r.status_code == 200

    def test_9d_a_puede_subir_documento_autenticado(self, env):
        r = env["client"].post(
            "/doc/upload",
            files={"file": ("test.txt", b"contenido de prueba, sin datos sensibles", "text/plain")},
            headers=_headers(env["a"]["api_key"]),
        )
        assert r.status_code == 200

    def test_9e_a_ve_su_historial_normalmente(self, env):
        r = env["client"].get("/history", headers=_headers(env["a"]["api_key"]))
        assert r.status_code == 200
        ids = [d["id"] for d in r.json()]
        assert env["decree_a_id"] in ids
        assert env["decree_b_id"] not in ids  # el historial tampoco mezcla clientes


class TestDecreeClientIdRoundTrip:
    """Unitario directo sobre DecreeStore, sin pasar por la API."""

    def test_client_id_persiste_y_se_restaura(self, env):
        store = DecreeStore(db_path=_TEST_DB)
        decree = store.get(env["decree_a_id"])
        assert decree is not None
        assert decree.client_id == env["a"]["client_id"]
        store._connection.close()

    def test_decree_sin_client_id_explicito_usa_default(self):
        """Un Decree() nuevo, sin especificar client_id, sigue siendo 'default'."""
        d = Decree(query="x")
        assert d.client_id == "default"


class TestLegacyDefaultYaNoEsBypassUniversal:
    """
    P0.1, 2ª ronda de revisión (Codex, 2026-08-29): 'default' dejó de
    ser un valor aceptado en el ownership de rutas de cliente. Un
    decreto histórico sin dueño real (como los 832 reales en
    producción) ya no debe ser legible/exportable/enviable/
    feedback-eable por NINGÚN cliente autenticado normal.
    """

    @pytest.fixture(scope="class")
    def legacy_decree_id(self, env):
        seed_store = DecreeStore(db_path=_TEST_DB)
        legacy = Decree(
            query="consulta legacy sin dueño real", domains=["technical"],
            gods_convened=["claude"],
            voices=[GodVoice("claude", "claude-sonnet", "respuesta legacy", 10, 50.0)],
            synthesis="sintesis legacy", total_tokens=10,
            status="complete", signature_payload_version=2,
        )
        seed_store.save(legacy, client_id="default")
        seed_store._connection.close()
        return legacy.id

    def test_a_no_puede_leer_decreto_default(self, env, legacy_decree_id):
        r = env["client"].get(f"/decree/{legacy_decree_id}", headers=_headers(env["a"]["api_key"]))
        assert r.status_code == 403

    def test_a_no_puede_exportar_decreto_default(self, env, legacy_decree_id):
        r = env["client"].get(
            f"/decree/{legacy_decree_id}/export?format=json",
            headers=_headers(env["a"]["api_key"]),
        )
        assert r.status_code == 403

    def test_a_no_puede_enviar_por_email_decreto_default(self, env, legacy_decree_id):
        with patch("smtplib.SMTP"):
            r = env["client"].post(
                f"/decree/{legacy_decree_id}/email",
                json={"to": "destino@test.invalid"},
                headers=_headers(env["a"]["api_key"]),
            )
        assert r.status_code == 403

    def test_a_no_puede_dar_feedback_sobre_decreto_default(self, env, legacy_decree_id):
        r = env["client"].post(
            f"/feedback/{legacy_decree_id}",
            json={"useful": True},
            headers=_headers(env["a"]["api_key"]),
        )
        assert r.status_code == 403


class TestClientIdPropagadoEnEndpointsDeAnalisis:
    """
    P0.2, 2ª ronda de revisión (Codex, 2026-08-29): /legal/analyze y
    /analyze-doc llamaban a Orchestrator.query() sin client_id, creando
    decretos "default" pese a estar autenticados. El Consejo/LLM real
    se mockea (patch de council.convene/synthesize) — no se llama a
    ningún modelo real ni se gasta un solo token real.
    """

    @pytest.fixture(scope="class")
    def legal_decree_id(self, env):
        with patch.object(env["orch"].council, "convene", new=AsyncMock(return_value=[_mock_god_response()])), \
             patch.object(env["orch"].council, "synthesize", new=AsyncMock(return_value=("Analisis legal mock, sin datos reales", []))):
            r = env["client"].post(
                "/legal/analyze",
                json={"type": "contrato", "text": "Texto de contrato de prueba, sin datos reales.", "jurisdiction": "España"},
                headers=_headers(env["a"]["api_key"]),
            )
        assert r.status_code == 200
        return r.json()["decree_id"]

    @pytest.fixture(scope="class")
    def analyze_doc_decree_id(self, env):
        with patch.object(env["orch"].council, "convene", new=AsyncMock(return_value=[_mock_god_response()])), \
             patch.object(env["orch"].council, "synthesize", new=AsyncMock(return_value=("Analisis de documento mock", []))):
            r = env["client"].post(
                "/analyze-doc",
                files={"file": ("test.txt", b"contenido de prueba, sin datos sensibles", "text/plain")},
                headers=_headers(env["a"]["api_key"]),
            )
        assert r.status_code == 200
        return r.json()["decree_id"]

    def test_6_legal_analyze_crea_decreto_propiedad_de_a(self, env, legal_decree_id):
        store = DecreeStore(db_path=_TEST_DB)
        saved = store.get(legal_decree_id)
        store._connection.close()
        assert saved is not None
        assert saved.client_id == env["a"]["client_id"], (
            f"/legal/analyze creó un decreto 'default' pese a auth — client_id={saved.client_id!r}"
        )

    def test_7_analyze_doc_crea_decreto_propiedad_de_a(self, env, analyze_doc_decree_id):
        store = DecreeStore(db_path=_TEST_DB)
        saved = store.get(analyze_doc_decree_id)
        store._connection.close()
        assert saved is not None
        assert saved.client_id == env["a"]["client_id"], (
            f"/analyze-doc creó un decreto 'default' pese a auth — client_id={saved.client_id!r}"
        )

    def test_8_propietario_recupera_decreto_de_legal_analyze(self, env, legal_decree_id):
        r = env["client"].get(f"/decree/{legal_decree_id}", headers=_headers(env["a"]["api_key"]))
        assert r.status_code == 200

    def test_8b_propietario_recupera_decreto_de_analyze_doc(self, env, analyze_doc_decree_id):
        r = env["client"].get(f"/decree/{analyze_doc_decree_id}", headers=_headers(env["a"]["api_key"]))
        assert r.status_code == 200

    def test_9_b_no_puede_recuperar_decreto_de_legal_analyze_de_a(self, env, legal_decree_id):
        r = env["client"].get(f"/decree/{legal_decree_id}", headers=_headers(env["b"]["api_key"]))
        assert r.status_code == 403

    def test_9b_b_no_puede_recuperar_decreto_de_analyze_doc_de_a(self, env, analyze_doc_decree_id):
        r = env["client"].get(f"/decree/{analyze_doc_decree_id}", headers=_headers(env["b"]["api_key"]))
        assert r.status_code == 403
