"""Corrección post-auditoría Codex sobre 6486a31 -- invariante:
concatenación de tokens SSE entregados al cliente == contenido terminal
persistido == contenido cubierto por la firma V2. Round-trip HTTP real:
reconstruye el texto recibido por SSE, lee el decreto persistido,
verifica igualdad exacta y revalida la firma sobre ese mismo contenido."""
import asyncio
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
from enlil.quantum import verify_decree, is_available

_TEST_DB = os.path.join(tempfile.gettempdir(), f"enlil_sse_integrity_test_{uuid.uuid4().hex}.db")


def _voice():
    return GodResponse(
        god_name="claude", model="mock/model", content="voz", tokens_used=10,
        latency_ms=1.0, voice_status="complete", finish_reason="stop",
    )


async def _fake_convene_stream(*args, **kwargs):
    yield _voice()


@pytest.fixture
def env():
    import enlil.auth as auth_module
    auth_module.DB_PATH = _TEST_DB
    init_auth_tables()
    client_info = create_client(name="SSE Integrity Test", email=f"sse-{uuid.uuid4().hex}@test.invalid")
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


def _run_and_reconstruct(env, query="consulta de prueba suficientemente larga para tier full"):
    r = env["client"].post("/query/stream", json={"query": query}, headers=_headers(env["api_key"]))
    assert r.status_code == 200
    events = _parse_sse(r.text)
    sse_text = "".join(e["token"] for e in events if e["type"] == "synthesis_token")
    done = [e for e in events if e["type"] == "done"][0]
    decree = env["orch"].store.get(done["decree_id"])
    return sse_text, decree


class TestCasoNormalCompleto:
    def test_sse_igual_a_persistido(self, env):
        async def fake_stream():
            for piece in ("Primera parte. ", "Segunda parte. ", "Cierre del decreto."):
                chunk = MagicMock()
                chunk.id = "gen-x"
                chunk.model = "claude-opus-5"
                chunk.usage = None
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta = MagicMock(content=piece, tool_calls=None, function_call=None)
                chunk.choices[0].finish_reason = None
                yield chunk
            final = MagicMock()
            final.id = "gen-x"
            final.model = "claude-opus-5"
            final.usage = MagicMock(total_tokens=30, prompt_tokens=10, completion_tokens=20, completion_tokens_details=None)
            final.choices = [MagicMock()]
            final.choices[0].delta = MagicMock(content=None, tool_calls=None, function_call=None)
            final.choices[0].finish_reason = "stop"
            yield final

        with patch.object(env["orch"].council, "convene_stream", new=_fake_convene_stream):
            env["orch"].council._anthropic_client = None
            env["orch"].council._client = MagicMock()
            env["orch"].council._client.chat.completions.create = AsyncMock(return_value=fake_stream())
            sse_text, decree = _run_and_reconstruct(env)

        assert sse_text == "Primera parte. Segunda parte. Cierre del decreto."
        assert decree.synthesis == sse_text, "el texto recibido por SSE debe ser BYTE-IDENTICO al persistido"
        assert decree.status == "complete"


class TestCasoTruncado:
    def test_sse_igual_a_persistido_con_length(self, env):
        async def fake_stream():
            for piece in ("Texto ", "cortado a mit"):
                chunk = MagicMock()
                chunk.id = "gen-y"
                chunk.model = "claude-opus-5"
                chunk.usage = None
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta = MagicMock(content=piece, tool_calls=None, function_call=None)
                chunk.choices[0].finish_reason = None
                yield chunk
            final = MagicMock()
            final.id = "gen-y"
            final.model = "claude-opus-5"
            final.usage = MagicMock(total_tokens=6000, prompt_tokens=100, completion_tokens=5900, completion_tokens_details=None)
            final.choices = [MagicMock()]
            final.choices[0].delta = MagicMock(content=None, tool_calls=None, function_call=None)
            final.choices[0].finish_reason = "length"
            yield final

        with patch.object(env["orch"].council, "convene_stream", new=_fake_convene_stream):
            env["orch"].council._anthropic_client = None
            env["orch"].council._client = MagicMock()
            env["orch"].council._client.chat.completions.create = AsyncMock(return_value=fake_stream())
            sse_text, decree = _run_and_reconstruct(env)

        assert sse_text == "Texto cortado a mit"
        assert decree.synthesis == sse_text
        assert decree.synthesis_attempts[0].state == "truncated"


class TestCasoTimeout:
    def test_sse_igual_a_persistido_tras_timeout_sin_marcador_extra(self, env):
        """Antes: se emitía un marcador de texto adicional que nunca
        entraba en lo persistido. Ahora: cero texto extra en cualquiera
        de los dos lados."""
        async def fake_stream():
            chunk = MagicMock()
            chunk.id = "gen-z"
            chunk.model = "claude-opus-5"
            chunk.usage = None
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta = MagicMock(content="poco antes de agotarse", tool_calls=None, function_call=None)
            chunk.choices[0].finish_reason = None
            yield chunk
            await asyncio.sleep(2.0)  # dispara el asyncio.timeout interno
            yield chunk  # nunca se llega aquí

        with patch.object(env["orch"].council, "convene_stream", new=_fake_convene_stream):
            env["orch"].council._anthropic_client = None
            env["orch"].council._client = MagicMock()
            env["orch"].council._client.chat.completions.create = AsyncMock(return_value=fake_stream())
            # Deadline muy corto -> stream_timeout ínfimo -> asyncio.timeout real dispara.
            with patch("enlil.orchestrator._total_budget_seconds", return_value=0.3):
                sse_text, decree = _run_and_reconstruct(env)

        assert sse_text == "poco antes de agotarse"
        assert "tiempo agotado" not in sse_text
        assert decree.synthesis == sse_text
        assert decree.synthesis_attempts[0].state in ("truncated", "timeout")


@pytest.mark.skipif(not is_available(), reason="oqs no disponible en este entorno")
class TestFirmaCubreElContenidoRealmenteRecibido:
    def test_firma_v2_verifica_sobre_el_texto_exacto_del_sse(self, env):
        async def fake_stream():
            chunk = MagicMock()
            chunk.id = "gen-w"
            chunk.model = "claude-opus-5"
            chunk.usage = MagicMock(total_tokens=10, prompt_tokens=5, completion_tokens=5, completion_tokens_details=None)
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta = MagicMock(content="contenido firmado", tool_calls=None, function_call=None)
            chunk.choices[0].finish_reason = "stop"
            yield chunk

        with patch.object(env["orch"].council, "convene_stream", new=_fake_convene_stream):
            env["orch"].council._anthropic_client = None
            env["orch"].council._client = MagicMock()
            env["orch"].council._client.chat.completions.create = AsyncMock(return_value=fake_stream())
            sse_text, decree = _run_and_reconstruct(env)

        assert decree.pq_signature
        valid = verify_decree(
            decree.id, decree.query, decree.synthesis, decree.timestamp, decree.pq_signature,
            payload_version=decree.signature_payload_version, status=decree.status,
        )
        assert valid is True
        # Y si se intentara verificar con el texto SSE recibido pero
        # DISTINTO del persistido, tendría que fallar -- prueba negativa
        # de que la firma realmente cubre el contenido, no solo lo asume.
        invalid = verify_decree(
            decree.id, decree.query, sse_text + " manipulado", decree.timestamp, decree.pq_signature,
            payload_version=decree.signature_payload_version, status=decree.status,
        )
        assert invalid is False
