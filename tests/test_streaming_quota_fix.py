"""Corrección post-auditoría Codex sobre 6486a31 -- api.py:293-305:
cuotas registradas exactamente una vez, ANTES de emitir "done", con el
tier realmente resuelto por Orchestrator (no el crudo de la petición)."""
import os
import uuid
import tempfile
import json

os.environ.setdefault("OPENROUTER_API_KEY", "test")

import pytest
from unittest.mock import patch, AsyncMock

from enlil.auth import init_auth_tables, create_client, client_usage_log
from enlil.orchestrator import Orchestrator
from enlil.gods.base import GodResponse
from enlil.reliability import SynthesisAttempt

_TEST_DB = os.path.join(tempfile.gettempdir(), f"enlil_quota_fix_test_{uuid.uuid4().hex}.db")


def _resp(name):
    return GodResponse(
        god_name=name, model="mock/model", content="respuesta mock", tokens_used=42,
        latency_ms=10.0, voice_status="complete", finish_reason="stop",
    )


async def _fake_convene_stream(*args, **kwargs):
    yield _resp("claude")


async def _fake_synthesize_stream(*args, **kwargs):
    yield "hola"
    yield SynthesisAttempt(
        attempt_number=1, content="hola", state="complete",
        requested_model="claude-opus-5", finish_reason="stop", usage_state="known", total_tokens=10,
    )


@pytest.fixture
def env():
    import enlil.auth as auth_module
    auth_module.DB_PATH = _TEST_DB
    init_auth_tables()
    client_info = create_client(name="Quota Fix Test", email=f"qf-{uuid.uuid4().hex}@test.invalid")
    with patch("openai.AsyncOpenAI"):
        from fastapi.testclient import TestClient
        import api as api_module
        with TestClient(api_module.app) as c:
            api_module.enlil = Orchestrator(db_path=_TEST_DB)
            yield {"client": c, "orch": api_module.enlil, "api_key": client_info["api_key"], "client_id": client_info["client_id"]}
    try:
        os.remove(_TEST_DB)
        for ext in ("-wal", "-shm"):
            if os.path.exists(_TEST_DB + ext):
                os.remove(_TEST_DB + ext)
    except OSError:
        pass


def _headers(api_key):
    return {"X-Api-Key": api_key}


class TestUsageRegistradoExactamenteUnaVez:
    def test_usage_log_una_sola_fila_tras_completar(self, env):
        with patch.object(env["orch"].council, "convene_stream", new=_fake_convene_stream), \
             patch.object(env["orch"].council, "synthesize_stream", new=_fake_synthesize_stream):
            r = env["client"].post(
                "/query/stream",
                json={"query": "consulta de prueba suficientemente larga para tier full quizas"},
                headers=_headers(env["api_key"]),
            )
        assert r.status_code == 200
        rows = client_usage_log(env["client_id"])
        assert len(rows) == 1

    def test_usage_ya_registrado_al_momento_de_ver_done(self, env):
        """Prueba directa del invariante 'antes de emitir done': se
        consulta usage_log EN VIVO, mientras el stream todavía se está
        consumiendo, en cuanto se ve la línea 'done' -- si el registro
        ocurriera después de emitir done (bug original), esta consulta
        podría no ver la fila todavía (condición de carrera real)."""
        with patch.object(env["orch"].council, "convene_stream", new=_fake_convene_stream), \
             patch.object(env["orch"].council, "synthesize_stream", new=_fake_synthesize_stream):
            with env["client"].stream(
                "POST", "/query/stream",
                json={"query": "consulta de prueba suficientemente larga para tier full quizas"},
                headers=_headers(env["api_key"]),
            ) as response:
                saw_done = False
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        parsed = json.loads(line[len("data: "):])
                        if parsed.get("type") == "done":
                            saw_done = True
                            # consulta EN VIVO, sin esperar a que termine el stream
                            rows = client_usage_log(env["client_id"])
                            assert len(rows) == 1, (
                                "usage_log debe tener la fila ANTES de que el "
                                "consumidor termine de ver el evento done"
                            )
                            break
                assert saw_done

    def test_no_doble_contabilizacion(self, env):
        with patch.object(env["orch"].council, "convene_stream", new=_fake_convene_stream), \
             patch.object(env["orch"].council, "synthesize_stream", new=_fake_synthesize_stream):
            env["client"].post(
                "/query/stream",
                json={"query": "consulta de prueba suficientemente larga para tier full quizas"},
                headers=_headers(env["api_key"]),
            )
        rows = client_usage_log(env["client_id"])
        assert len(rows) == 1


class TestTierRealmenteResuelto:
    def test_voices_count_9_tier_ausente_registra_full(self, env):
        with patch.object(env["orch"].council, "convene_stream", new=_fake_convene_stream), \
             patch.object(env["orch"].council, "synthesize_stream", new=_fake_synthesize_stream):
            r = env["client"].post(
                "/query/stream",
                json={"query": "q corta", "voices_count": 9},
                headers=_headers(env["api_key"]),
            )
        assert r.status_code == 200
        rows = client_usage_log(env["client_id"])
        assert len(rows) == 1
        assert rows[0]["budget_tier"] == "full", (
            f"se registró {rows[0]['budget_tier']!r} en vez del tier real resuelto por Orchestrator"
        )
