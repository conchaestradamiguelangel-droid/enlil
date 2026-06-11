import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("OPENROUTER_API_KEY", "test")
os.environ.setdefault("ENLIL_DB", ":memory:")

from fastapi.testclient import TestClient
from enlil.decrees.decree import Decree, GodVoice


def make_decree(**kwargs) -> Decree:
    defaults = dict(
        query="consulta api test",
        domains=["technical"],
        gods_convened=["claude", "enki"],
        voices=[
            GodVoice("claude", "claude-sonnet", "respuesta claude", 100, 200.0),
            GodVoice("enki", "gpt-4o", "respuesta enki", 120, 250.0),
        ],
        synthesis="Sintesis del Consejo via API.",
        total_tokens=220,
        budget_tier="standard",
    )
    defaults.update(kwargs)
    return Decree(**defaults)


@pytest.fixture
def client():
    """
    Crea un TestClient con el orquestador completamente mockeado.
    Parchea Orchestrator en el módulo api ANTES de que el lifespan lo instancie.
    """
    from enlil.orchestrator import Orchestrator
    from enlil.auth import require_auth
    mock_orch = MagicMock(spec=Orchestrator)
    mock_orch.query = AsyncMock(return_value=make_decree())
    mock_orch.history = MagicMock(return_value=[])
    mock_orch.get_decree = MagicMock(return_value=None)
    mock_orch.feedback = MagicMock()
    mock_orch.pantheon_status = MagicMock(return_value={})
    mock_orch.pantheon = {}

    with patch("openai.AsyncOpenAI"), patch("api.Orchestrator", return_value=mock_orch), patch("api.log_usage"):
        from api import app
        app.dependency_overrides[require_auth] = lambda: {"id": "test-client", "active": True}
        with TestClient(app) as c:
            yield c, mock_orch
        app.dependency_overrides.pop(require_auth, None)


class TestQueryEndpoint:
    def test_query_returns_200(self, client):
        c, mock_orch = client
        resp = c.post("/query", json={"query": "consulta de prueba"})
        assert resp.status_code == 200

    def test_query_response_structure(self, client):
        c, mock_orch = client
        resp = c.post("/query", json={"query": "consulta de prueba"})
        data = resp.json()
        for field in ["decree_id", "synthesis", "voices", "domains", "gods_convened", "total_tokens", "budget_tier", "has_dissent"]:
            assert field in data, f"Campo ausente: {field}"

    def test_query_voices_structure(self, client):
        c, mock_orch = client
        resp = c.post("/query", json={"query": "test"})
        voices = resp.json()["voices"]
        assert len(voices) == 2
        for v in voices:
            assert "god" in v and "content" in v and "tokens" in v

    def test_query_with_budget_tier(self, client):
        c, mock_orch = client
        c.post("/query", json={"query": "hola", "budget_tier": "minimal"})
        mock_orch.query.assert_called_once()
        _, kwargs = mock_orch.query.call_args
        assert kwargs.get("budget_tier") == "minimal" or mock_orch.query.call_args[0][2] == "minimal"

    def test_query_dissent_flagged(self, client):
        c, mock_orch = client
        mock_orch.query = AsyncMock(return_value=make_decree(voices=[
            GodVoice("claude", "m", "ok", 100, 200.0),
            GodVoice("enki", "m", "ok", 100, 200.0, dissent="Disiento"),
        ]))
        resp = c.post("/query", json={"query": "test disidencia"})
        data = resp.json()
        assert data["has_dissent"] is True
        assert "enki" in data["dissenting_gods"]

    def test_query_no_dissent(self, client):
        c, mock_orch = client
        resp = c.post("/query", json={"query": "test"})
        assert resp.json()["has_dissent"] is False


class TestFeedbackEndpoint:
    def test_feedback_useful(self, client):
        c, mock_orch = client
        resp = c.post("/feedback/decreto-123", json={"useful": True})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        mock_orch.feedback.assert_called_once_with("decreto-123", True)

    def test_feedback_not_useful(self, client):
        c, mock_orch = client
        resp = c.post("/feedback/decreto-456", json={"useful": False})
        assert resp.status_code == 200
        mock_orch.feedback.assert_called_once_with("decreto-456", False)


class TestHistoryEndpoint:
    def test_history_returns_list(self, client):
        c, mock_orch = client
        mock_orch.history.return_value = [make_decree(), make_decree()]
        resp = c.get("/history")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_history_empty(self, client):
        c, mock_orch = client
        mock_orch.history.return_value = []
        resp = c.get("/history")
        assert resp.json() == []

    def test_history_limit_param(self, client):
        c, mock_orch = client
        mock_orch.history.return_value = []
        c.get("/history?limit=5")
        mock_orch.history.assert_called_with(5, client_id="test-client")

    def test_history_fields(self, client):
        c, mock_orch = client
        mock_orch.history.return_value = [make_decree()]
        data = c.get("/history").json()
        item = data[0]
        for field in ["id", "query", "domains", "gods_convened", "total_tokens", "budget_tier"]:
            assert field in item


class TestDecreeEndpoint:
    def test_get_existing_decree(self, client):
        c, mock_orch = client
        d = make_decree()
        mock_orch.get_decree.return_value = d
        resp = c.get(f"/decree/{d.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == d.id
        assert data["query"] == d.query
        assert len(data["voices"]) == 2

    def test_get_nonexistent_returns_404(self, client):
        c, mock_orch = client
        mock_orch.get_decree.return_value = None
        assert c.get("/decree/id-inexistente").status_code == 404

    def test_decree_includes_all_fields(self, client):
        c, mock_orch = client
        d = make_decree()
        mock_orch.get_decree.return_value = d
        data = c.get(f"/decree/{d.id}").json()
        for field in ["id", "query", "synthesis", "domains", "gods_convened", "voices", "total_tokens", "budget_tier"]:
            assert field in data


class TestPantheonEndpoint:
    def test_pantheon_returns_list(self, client):
        c, mock_orch = client
        mock_orch.pantheon = {
            "claude": MagicMock(
                name="Claude", model="claude-sonnet", role="Dios de Contexto",
                domains=["context"], reputation={}
            )
        }
        mock_orch.pantheon_status.return_value = {}
        resp = c.get("/pantheon")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_pantheon_god_structure(self, client):
        c, mock_orch = client
        mock_orch.pantheon = {
            "enki": MagicMock(
                name="Enki", model="gpt-4o", role="Dios del Conocimiento",
                domains=["technical"], reputation={}
            )
        }
        mock_orch.pantheon_status.return_value = {}
        data = c.get("/pantheon").json()
        god = data[0]
        for field in ["name", "display_name", "model", "role", "domains"]:
            assert field in god


class TestDashboard:
    def test_returns_html(self, client):
        c, _ = client
        resp = c.get("/")
        assert resp.status_code == 200
        assert "ENLIL" in resp.text
        assert "text/html" in resp.headers["content-type"]

    def test_dashboard_has_query_form(self, client):
        c, _ = client
        resp = c.get("/")
        assert "queryInput" in resp.text
        assert "Convocar el Consejo" in resp.text

class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        c, _ = client

        resp = c.get("/health")

        assert resp.status_code == 200

    def test_health_response_structure(self, client):
        c, _ = client

        resp = c.get("/health")
        data = resp.json()

        for field in [
            "status",
            "council_mode",
            "qdrant_active",
            "decree_count",
        ]:
            assert field in data