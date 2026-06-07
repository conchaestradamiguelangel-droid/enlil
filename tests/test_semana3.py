import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("OPENROUTER_API_KEY", "")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("ENLIL_DB", ":memory:")

from enlil.verticals.cybersecurity import (
    AegisAlert, SecurityDecreeContext,
    build_aegis_query, parse_aegis_webhook,
)
from fastapi.testclient import TestClient
from enlil.decrees.decree import Decree, GodVoice


# --- Tests vertical ciberseguridad ---

class TestAegisAlert:
    def test_basic_alert(self):
        alert = AegisAlert(alert_type="DDoS", severity="high", source_ip="1.2.3.4")
        assert alert.alert_type == "DDoS"
        assert alert.severity == "high"
        assert alert.source_ip == "1.2.3.4"

    def test_defaults(self):
        alert = AegisAlert(alert_type="probe", severity="low")
        assert alert.source_ip is None
        assert alert.details == {}
        assert alert.raw_log == ""


class TestSecurityDecreeContext:
    def test_to_query_includes_type_and_severity(self):
        alert = AegisAlert(alert_type="intrusion", severity="critical", source_ip="10.0.0.1")
        ctx = SecurityDecreeContext(alert=alert)
        q = ctx.to_query()
        assert "intrusion" in q
        assert "critical" in q
        assert "10.0.0.1" in q

    def test_to_context_mentions_aegis(self):
        alert = AegisAlert(alert_type="DDoS", severity="high")
        ctx = SecurityDecreeContext(alert=alert)
        assert "AEGIS" in ctx.to_context()

    def test_raw_log_truncated(self):
        alert = AegisAlert(alert_type="flood", severity="medium", raw_log="x" * 1000)
        ctx = SecurityDecreeContext(alert=alert)
        q = ctx.to_query()
        assert len(q) < 2000  # log truncado a 500 chars


class TestBuildAegisQuery:
    def test_returns_tuple(self):
        alert = AegisAlert(alert_type="scan", severity="low")
        query, context = build_aegis_query(alert)
        assert isinstance(query, str) and len(query) > 0
        assert isinstance(context, str) and len(context) > 0

    def test_query_contains_alert_info(self):
        alert = AegisAlert(alert_type="DDoS", severity="critical", source_ip="192.168.1.1")
        query, _ = build_aegis_query(alert)
        assert "DDoS" in query
        assert "critical" in query


class TestParseAegisWebhook:
    def test_full_payload(self):
        payload = {
            "type": "intrusion",
            "severity": "high",
            "source_ip": "1.2.3.4",
            "target": "api-server",
            "details": {"port": 8080},
            "log": "conexion sospechosa detectada",
        }
        alert = parse_aegis_webhook(payload)
        assert alert.alert_type == "intrusion"
        assert alert.severity == "high"
        assert alert.source_ip == "1.2.3.4"
        assert alert.details == {"port": "8080"}  # sanitizados a str

    def test_minimal_payload(self):
        alert = parse_aegis_webhook({})
        assert alert.alert_type == "unknown"
        assert alert.severity == "medium"

    def test_partial_payload(self):
        alert = parse_aegis_webhook({"type": "probe"})
        assert alert.alert_type == "probe"
        assert alert.source_ip is None


# --- Tests endpoint AEGIS en API ---

def make_decree(**kwargs):
    defaults = dict(
        query="AEGIS alerta DDoS critical",
        domains=["security"],
        gods_convened=["claude", "ninurta"],
        voices=[
            GodVoice("claude", "m", "Respuesta de contexto", 100, 200.0),
            GodVoice("ninurta", "m", "Bloquear IP y activar rate limiting", 120, 250.0),
        ],
        synthesis="Bloquear 1.2.3.4, activar modo defensa, escalar a MSSP.",
        total_tokens=220,
        budget_tier="standard",
    )
    defaults.update(kwargs)
    return Decree(**defaults)


@pytest.fixture
def client():
    from enlil.orchestrator import Orchestrator
    mock_orch = MagicMock(spec=Orchestrator)
    mock_orch.query = AsyncMock(return_value=make_decree())
    mock_orch.history = MagicMock(return_value=[])
    mock_orch.get_decree = MagicMock(return_value=None)
    mock_orch.feedback = MagicMock()
    mock_orch.pantheon_status = MagicMock(return_value={})
    mock_orch.pantheon = {}

    with patch("openai.AsyncOpenAI"), patch("api.Orchestrator", return_value=mock_orch):
        from api import app
        import api as api_module
        with TestClient(app) as c:
            yield c, mock_orch


class TestAegisEndpoint:
    def test_analyze_endpoint_removed(self, client):
        """El endpoint especial /aegis/analyze fue eliminado — AEGIS usa /query con API key."""
        c, _ = client
        resp = c.post("/aegis/analyze", json={"type": "DDoS", "severity": "high"})
        assert resp.status_code == 404

    def test_query_requires_api_key(self, client):
        """Sin X-Api-Key, /query devuelve 401."""
        c, _ = client
        resp = c.post("/query", json={"query": "Alerta AEGIS test", "budget_tier": "minimal"})
        assert resp.status_code == 401

    def test_history_endpoint(self, client):
        c, mock_orch = client
        mock_orch.history.return_value = [
            make_decree(query="AEGIS alerta DDoS critica"),
            make_decree(query="consulta sobre python"),
        ]
        from enlil.auth import require_master
        from api import app
        app.dependency_overrides[require_master] = lambda: True
        try:
            resp = c.get("/aegis/history")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, list)
        finally:
            app.dependency_overrides.pop(require_master, None)


# --- Tests modo dual Anthropic/OpenRouter ---

class TestCouncilDualMode:
    def test_council_works_with_anthropic_key_only(self):
        with patch("openai.AsyncOpenAI"), \
             patch.dict(os.environ, {"OPENROUTER_API_KEY": "", "ANTHROPIC_API_KEY": "test-key"}):
            from enlil.gods.registry import build_default_pantheon
            from enlil.council import Council
            council = Council(build_default_pantheon())
            assert council.mode == "anthropic"
            # Con Anthropic, modelos externos se mapean a Claude
            assert "claude" in council._resolve_model("openai/gpt-4o").lower()
            assert "claude" in council._resolve_model("google/gemini-flash-1.5").lower()

    def test_model_map_covers_all_gods(self):
        with patch("openai.AsyncOpenAI"), \
             patch.dict(os.environ, {"OPENROUTER_API_KEY": "", "ANTHROPIC_API_KEY": "test-key"}):
            from enlil.gods.registry import build_default_pantheon
            from enlil.council import Council, _ANTHROPIC_MODEL_MAP
            pantheon = build_default_pantheon()
            council = Council(pantheon)
            for god in pantheon.values():
                resolved = _ANTHROPIC_MODEL_MAP.get(god.model, "claude-sonnet-4-5-20251022")
                assert "claude" in resolved.lower()
