import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("OPENROUTER_API_KEY", "test")
os.environ.setdefault("ENLIL_DB", ":memory:")
os.environ["ENLIL_EKURHIVE_TASK_KEY"] = "test-ekurhive-task-key-for-tests"

from fastapi.testclient import TestClient
from enlil.decrees.decree import Decree, GodVoice

_TEST_KEY = "test-ekurhive-task-key-for-tests"
_VALID_AUTH = f"Bearer {_TEST_KEY}"
_UUID_1 = "11111111-1111-1111-1111-111111111111"
_UUID_2 = "22222222-2222-2222-2222-222222222222"

_VALID_BODY = {
    "request_id": _UUID_1,
    "connection_id": _UUID_2,
    "sender_node_id": "node-ekurhive-001",
    "task": {"type": "consulta", "input": "Que implica la clausula de subencargo?"},
}


def make_decree(**kwargs) -> Decree:
    defaults = dict(
        query="task ekurhive",
        domains=["legal"],
        gods_convened=["thoth"],
        voices=[GodVoice("thoth", "claude-sonnet", "analisis del consejo", 100, 200.0)],
        synthesis="El Consejo ha deliberado: la clausula es valida.",
        total_tokens=100,
        budget_tier="standard",
    )
    defaults.update(kwargs)
    return Decree(**defaults)


def _mock_orch(decree=None):
    m = MagicMock()
    m.query = AsyncMock(return_value=decree or make_decree())
    m.history = MagicMock(return_value=[])
    m.get_decree = MagicMock(return_value=None)
    m.feedback = MagicMock()
    m.pantheon_status = MagicMock(return_value={})
    m.pantheon = {}
    return m


@pytest.fixture
def raw_client():
    mo = _mock_orch()
    with patch("openai.AsyncOpenAI"), patch("api.Orchestrator", return_value=mo), patch("api.log_usage"):
        from api import app
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c, mo


@pytest.fixture
def authed_client():
    mo = _mock_orch()
    with patch("openai.AsyncOpenAI"), patch("api.Orchestrator", return_value=mo), patch("api.log_usage"):
        from api import app, require_ekurhive_task_auth
        app.dependency_overrides[require_ekurhive_task_auth] = lambda: None
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c, mo
        app.dependency_overrides.pop(require_ekurhive_task_auth, None)


class TestTaskAuth:
    def test_missing_header_returns_401(self, raw_client):
        c, _ = raw_client
        r = c.post("/task", json=_VALID_BODY)
        assert r.status_code == 401

    def test_wrong_bearer_returns_401(self, raw_client):
        c, _ = raw_client
        r = c.post("/task", json=_VALID_BODY, headers={"Authorization": "Bearer wrong-key"})
        assert r.status_code == 401

    def test_correct_bearer_returns_200(self, raw_client):
        c, _ = raw_client
        r = c.post("/task", json=_VALID_BODY, headers={"Authorization": _VALID_AUTH})
        assert r.status_code == 200

    def test_no_auth_header_returns_401_not_422(self, raw_client):
        c, _ = raw_client
        r = c.post("/task", json={**_VALID_BODY, "request_id": "not-a-uuid"})
        assert r.status_code == 401


class TestTaskSchema:
    def test_invalid_request_uuid_returns_422(self, authed_client):
        c, _ = authed_client
        r = c.post("/task", json={**_VALID_BODY, "request_id": "not-a-uuid"})
        assert r.status_code == 422

    def test_invalid_connection_uuid_returns_422(self, authed_client):
        c, _ = authed_client
        r = c.post("/task", json={**_VALID_BODY, "connection_id": "bad"})
        assert r.status_code == 422

    def test_invalid_task_type_returns_422(self, authed_client):
        c, _ = authed_client
        body = {**_VALID_BODY, "task": {**_VALID_BODY["task"], "type": "resumen"}}
        r = c.post("/task", json=body)
        assert r.status_code == 422

    def test_empty_input_returns_422(self, authed_client):
        c, _ = authed_client
        body = {**_VALID_BODY, "task": {**_VALID_BODY["task"], "input": ""}}
        r = c.post("/task", json=body)
        assert r.status_code == 422

    def test_input_too_long_returns_422(self, authed_client):
        c, _ = authed_client
        body = {**_VALID_BODY, "task": {**_VALID_BODY["task"], "input": "x" * 8001}}
        r = c.post("/task", json=body)
        assert r.status_code == 422

    def test_missing_sender_node_id_returns_422(self, authed_client):
        c, _ = authed_client
        body = {k: v for k, v in _VALID_BODY.items() if k != "sender_node_id"}
        r = c.post("/task", json=body)
        assert r.status_code == 422


class TestTaskBehavior:
    def test_response_structure(self, authed_client):
        c, _ = authed_client
        r = c.post("/task", json=_VALID_BODY)
        assert r.status_code == 200
        data = r.json()
        j4_fields = (
            "request_id", "agent_id", "algorithm", "status",
            "result", "error", "result_sha3_256", "signature_version",
            "pq_signature", "key_id",
        )
        for field in j4_fields:
            assert field in data, f"Campo J4 ausente: {field}"
        assert data["algorithm"] == "ML-DSA-87"
        assert data["signature_version"] == "1"
        assert data["pq_signature"] is not None
        assert data["key_id"] is not None
        assert len(data["result_sha3_256"]) == 64

    def test_request_id_preserved(self, authed_client):
        c, _ = authed_client
        r = c.post("/task", json=_VALID_BODY)
        assert r.json()["request_id"] == _UUID_1

    def test_agent_id_is_node_enlil_001(self, authed_client):
        c, _ = authed_client
        r = c.post("/task", json=_VALID_BODY)
        assert r.json()["agent_id"] == "node-enlil-001"

    def test_completed_status_on_success(self, authed_client):
        c, _ = authed_client
        r = c.post("/task", json=_VALID_BODY)
        data = r.json()
        assert data["status"] == "completed"
        assert data["error"] is None
        assert data["result"] is not None

    def test_timeout_returns_failed(self, authed_client):
        c, mo = authed_client
        mo.query = AsyncMock(side_effect=asyncio.TimeoutError())
        r = c.post("/task", json=_VALID_BODY)
        data = r.json()
        assert data["status"] == "failed"
        assert data["error"] == "timeout"
        assert data["result"] is None

    def test_internal_error_returns_failed(self, authed_client):
        c, mo = authed_client
        mo.query = AsyncMock(side_effect=RuntimeError("fallo interno"))
        r = c.post("/task", json=_VALID_BODY)
        data = r.json()
        assert data["status"] == "failed"
        assert data["error"] == "internal_error"
        assert data["result"] is None

    def test_no_stack_trace_in_error_response(self, authed_client):
        c, mo = authed_client
        mo.query = AsyncMock(side_effect=RuntimeError("secreto interno"))
        r = c.post("/task", json=_VALID_BODY)
        body_str = r.text
        assert "secreto interno" not in body_str
        assert "Traceback" not in body_str

    def test_no_key_in_response_body(self, raw_client):
        c, _ = raw_client
        r = c.post("/task", json=_VALID_BODY, headers={"Authorization": _VALID_AUTH})
        assert _TEST_KEY not in r.text

    def test_context_optional(self, authed_client):
        c, _ = authed_client
        body = {k: v for k, v in _VALID_BODY.items() if k != "context"}
        r = c.post("/task", json=body)
        assert r.status_code == 200

    def test_all_task_types_accepted(self, authed_client):
        c, _ = authed_client
        for t in ("analisis", "sintesis", "consulta", "verificacion"):
            body = {**_VALID_BODY, "task": {**_VALID_BODY["task"], "type": t}}
            r = c.post("/task", json=body)
            assert r.status_code == 200, f"Tipo {t!r} rechazado inesperadamente"
