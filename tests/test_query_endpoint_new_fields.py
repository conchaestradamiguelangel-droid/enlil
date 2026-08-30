"""TEST 01B — /query (no streaming) expone los campos nuevos de forma
aditiva, sin romper ninguno existente. Integración HTTP real."""
import os
import uuid
import tempfile

os.environ.setdefault("OPENROUTER_API_KEY", "test")

import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from enlil.auth import init_auth_tables, create_client
from enlil.orchestrator import Orchestrator
from enlil.gods.base import GodResponse

_TEST_DB = os.path.join(tempfile.gettempdir(), f"enlil_query_fields_test_{uuid.uuid4().hex}.db")


def _resp(name):
    return GodResponse(
        god_name=name, model="mock/model", content="respuesta mock", tokens_used=10,
        latency_ms=50.0, voice_status="complete", finish_reason="stop",
    )


@pytest.fixture(scope="module")
def env():
    import enlil.auth as auth_module
    auth_module.DB_PATH = _TEST_DB
    init_auth_tables()
    client_info = create_client(name="Query Fields Test", email=f"q-{uuid.uuid4().hex}@test.invalid")
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


def test_query_expone_campos_nuevos_sin_quitar_los_existentes(env):
    orch = env["orch"]
    responses = [_resp("claude"), _resp("enki")]
    with patch.object(orch.council, "convene", new=AsyncMock(return_value=responses)), \
         patch.object(orch.council, "synthesize", new=AsyncMock(return_value=("sintesis ok", []))):
        r = env["client"].post(
            "/query",
            json={"query": "consulta de prueba"},
            headers={"X-Api-Key": env["api_key"]},
        )
    assert r.status_code == 200
    body = r.json()
    # campos legacy, sin cambios
    for key in ("decree_id", "domains", "gods_convened", "synthesis", "total_tokens",
                "budget_tier", "has_dissent", "dissenting_gods", "pq_signed",
                "predicted_scores", "voices"):
        assert key in body
    # campos nuevos, aditivos
    for key in ("status", "accounting_state", "known_token_subtotal",
                "observed_total_tokens", "wall_clock_ms"):
        assert key in body
    assert body["status"] in ("complete", "partial", "failed")
    for voice in body["voices"]:
        assert "voice_status" in voice
        assert "finish_reason" in voice
        assert "retry_count" in voice
        # campos legacy de voz tampoco desaparecen
        assert "god" in voice and "content" in voice and "tokens" in voice
