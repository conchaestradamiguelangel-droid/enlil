"""TEST 01B — /query/stream mantiene el contrato SSE público actual y
COMPATIBILITY_PROFILE reproduce exactamente PUBLIC_API_TODAY (cero
efectos laterales que hoy no existen en esa ruta).
ENLIL_TEST01B_AUDITORIA_DISENO_V5/V6.md §5/§6."""
import os
import uuid
import tempfile
import json

os.environ.setdefault("OPENROUTER_API_KEY", "test")

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from enlil.auth import init_auth_tables, create_client
from enlil.orchestrator import Orchestrator
from enlil.gods.base import GodResponse
from enlil.reliability import SynthesisAttempt

_TEST_DB = os.path.join(tempfile.gettempdir(), f"enlil_stream_compat_test_{uuid.uuid4().hex}.db")


def _mock_god_response(name="claude") -> GodResponse:
    return GodResponse(
        god_name=name, model="mock/model", content="respuesta mock",
        tokens_used=10, latency_ms=50.0, voice_status="complete", finish_reason="stop",
    )


async def _fake_convene_stream(*args, **kwargs):
    yield _mock_god_response("claude")
    yield _mock_god_response("enki")


async def _fake_synthesize_stream(*args, **kwargs):
    yield "hola "
    yield "mundo"
    yield SynthesisAttempt(
        attempt_number=1, content="hola mundo", state="complete",
        requested_model="claude-opus-5", finish_reason="stop",
        total_tokens=50, usage_state="known",
    )


@pytest.fixture(scope="module")
def env():
    import enlil.auth as auth_module
    auth_module.DB_PATH = _TEST_DB
    init_auth_tables()
    client_info = create_client(name="Stream Test Client", email=f"s-{uuid.uuid4().hex}@test.invalid")

    with patch("openai.AsyncOpenAI"):
        import api as api_module
        with TestClient(api_module.app) as c:
            api_module.enlil = Orchestrator(db_path=_TEST_DB)
            yield {"client": c, "orch": api_module.enlil, "api_key": client_info["api_key"]}

    try:
        os.remove(_TEST_DB)
        for ext in ("-wal", "-shm"):
            if os.path.exists(_TEST_DB + ext):
                os.remove(_TEST_DB + ext)
    except OSError:
        pass


def _headers(api_key):
    return {"X-Api-Key": api_key}


def _parse_sse(body: str) -> list[dict]:
    events = []
    for line in body.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: "):]))
    return events


class TestContratoSSEPublicoIntacto:
    def test_eventos_y_orden_esperados(self, env):
        with patch.object(env["orch"].council, "convene_stream", new=_fake_convene_stream), \
             patch.object(env["orch"].council, "synthesize_stream", new=_fake_synthesize_stream):
            r = env["client"].post(
                "/query/stream",
                json={"query": "consulta de prueba suficientemente larga para tier full quizas"},
                headers=_headers(env["api_key"]),
            )
        assert r.status_code == 200
        events = _parse_sse(r.text)
        types = [e["type"] for e in events]
        # Contrato actual: SIN evento "init", 2x "god", 2x "synthesis_token", "done"
        assert "init" not in types, "el evento init no existe en el contrato público hoy"
        assert types.count("god") == 2
        assert types.count("synthesis_token") == 2
        assert types[-1] == "done"

    def test_evento_god_sin_campo_model(self, env):
        with patch.object(env["orch"].council, "convene_stream", new=_fake_convene_stream), \
             patch.object(env["orch"].council, "synthesize_stream", new=_fake_synthesize_stream):
            r = env["client"].post(
                "/query/stream",
                json={"query": "consulta de prueba suficientemente larga para tier full quizas"},
                headers=_headers(env["api_key"]),
            )
        events = _parse_sse(r.text)
        god_events = [e for e in events if e["type"] == "god"]
        assert len(god_events) == 2
        for ev in god_events:
            assert "model" not in ev, "el campo 'model' no existe hoy en el evento god público"

    def test_synthesis_token_no_synthesis_chunk(self, env):
        with patch.object(env["orch"].council, "convene_stream", new=_fake_convene_stream), \
             patch.object(env["orch"].council, "synthesize_stream", new=_fake_synthesize_stream):
            r = env["client"].post(
                "/query/stream",
                json={"query": "consulta de prueba suficientemente larga para tier full quizas"},
                headers=_headers(env["api_key"]),
            )
        events = _parse_sse(r.text)
        syn_events = [e for e in events if e["type"] == "synthesis_token"]
        assert len(syn_events) == 2
        for ev in syn_events:
            assert "token" in ev
            assert "text" not in ev

    def test_done_incluye_peer_review_no_domains(self, env):
        with patch.object(env["orch"].council, "convene_stream", new=_fake_convene_stream), \
             patch.object(env["orch"].council, "synthesize_stream", new=_fake_synthesize_stream):
            r = env["client"].post(
                "/query/stream",
                json={"query": "consulta de prueba suficientemente larga para tier full quizas"},
                headers=_headers(env["api_key"]),
            )
        events = _parse_sse(r.text)
        done = [e for e in events if e["type"] == "done"][0]
        assert "peer_review" in done
        assert "domains" not in done


class TestCompatibilityProfileSinEfectosLaterales:
    def test_corpus_meta_decay_rl_no_se_llaman(self, env):
        orch = env["orch"]
        # orch.corpus puede ser None en este entorno de test (sin Qdrant
        # real) -- en ese caso el propio `if profile.use_corpus and
        # self.corpus:` ya haria que nunca se llame, pero se sustituye por
        # un doble consultable para que la aserción sea significativa en
        # cualquier entorno, no solo "no hay corpus disponible".
        fake_corpus = MagicMock()
        fake_corpus.search = MagicMock(return_value="")
        with patch.object(orch, "corpus", fake_corpus), \
             patch.object(orch.council, "convene_stream", new=_fake_convene_stream), \
             patch.object(orch.council, "synthesize_stream", new=_fake_synthesize_stream), \
             patch.object(orch.meta, "observe") as mock_meta, \
             patch("enlil.orchestrator.apply_decay") as mock_decay, \
             patch.object(orch.memory, "store") as mock_mem_store:
            r = env["client"].post(
                "/query/stream",
                json={"query": "consulta de prueba suficientemente larga para tier full quizas"},
                headers=_headers(env["api_key"]),
            )
        assert r.status_code == 200
        fake_corpus.search.assert_not_called()
        mock_meta.assert_not_called()
        mock_decay.assert_not_called()
        mock_mem_store.assert_not_called()

    def test_predicted_scores_vacio_y_parent_decree_id_ignorado(self, env):
        """Hallazgo V6 §5 fila 18/19 -- se replica el bug actual a
        propósito: parent_decree_id se pierde en COMPATIBILITY_PROFILE."""
        orch = env["orch"]
        with patch.object(orch.council, "convene_stream", new=_fake_convene_stream), \
             patch.object(orch.council, "synthesize_stream", new=_fake_synthesize_stream):
            r = env["client"].post(
                "/query/stream",
                json={
                    "query": "consulta de prueba suficientemente larga para tier full quizas",
                    "parent_decree_id": "algun-id-padre",
                },
                headers=_headers(env["api_key"]),
            )
        events = _parse_sse(r.text)
        done = [e for e in events if e["type"] == "done"][0]
        decree = orch.store.get(done["decree_id"])
        assert decree.predicted_scores == {}
        assert decree.parent_decree_id is None

    def test_status_accounting_se_calculan_igualmente_en_streaming(self, env):
        """El profile solo apaga efectos laterales -- NO apaga la
        observabilidad nueva (status/accounting), que es el objetivo de
        TEST 01B y debe funcionar igual en streaming que en /query."""
        orch = env["orch"]
        with patch.object(orch.council, "convene_stream", new=_fake_convene_stream), \
             patch.object(orch.council, "synthesize_stream", new=_fake_synthesize_stream):
            r = env["client"].post(
                "/query/stream",
                json={"query": "consulta de prueba suficientemente larga para tier full quizas"},
                headers=_headers(env["api_key"]),
            )
        events = _parse_sse(r.text)
        done = [e for e in events if e["type"] == "done"][0]
        decree = orch.store.get(done["decree_id"])
        assert decree.status == "complete"
        assert decree.signature_payload_version == 2
        assert decree.accounting_state in ("known", "partial", "unknown")
