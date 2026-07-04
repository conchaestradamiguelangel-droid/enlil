"""
Tests semana 4 — integración AEGIS→ENLIL en real.
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("OPENROUTER_API_KEY", "")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("ENLIL_DB", ":memory:")

from enlil.verticals.cybersecurity import parse_aegis_webhook, AegisAlert
from enlil.meta_observer import MetaObserver
from enlil.memory_qdrant import QdrantMemoryStore
from enlil.evolution import (
    weighted_selection, apply_decay, fitness_report,
    EXPLORATION_RATE, DECAY_RATE, PENALTY_THRESHOLD,
)
from enlil.gods.registry import build_default_pantheon
from fastapi.testclient import TestClient
from enlil.decrees.decree import Decree, GodVoice


def _make_decree(synthesis="síntesis de prueba") -> Decree:
    voice = GodVoice("ninurta", "claude-sonnet-4-6", "análisis amenaza", 150, 300.0)
    return Decree(
        query="Alerta AEGIS — Tipo: intrusion",
        domains=["security"],
        gods_convened=["ninurta"],
        synthesis=synthesis,
        voices=[voice],
        budget_tier="standard",
    )


@pytest.fixture
def aegis_client():
    from enlil.orchestrator import Orchestrator
    mock_orch = MagicMock(spec=Orchestrator)
    mock_orch.query = AsyncMock(return_value=_make_decree())
    mock_orch.history = MagicMock(return_value=[])
    mock_orch.pantheon_status = MagicMock(return_value={})
    mock_orch.pantheon = {}

    with patch("openai.AsyncOpenAI"), patch("api.Orchestrator", return_value=mock_orch):
        from api import app
        from enlil.auth import require_master
        app.dependency_overrides[require_master] = lambda: True
        try:
            with TestClient(app) as c:
                yield c, mock_orch
        finally:
            app.dependency_overrides.pop(require_master, None)


# ── Sanitización de webhooks ──────────────────────────────────────────────────

class TestWebhookSanitization:
    def test_invalid_severity_becomes_medium(self):
        alert = parse_aegis_webhook({"type": "probe", "severity": "extreme_ultra"})
        assert alert.severity == "medium"

    def test_valid_severities_pass_through(self):
        for sev in ("low", "medium", "high", "critical"):
            alert = parse_aegis_webhook({"type": "probe", "severity": sev})
            assert alert.severity == sev

    def test_type_truncated_at_50(self):
        alert = parse_aegis_webhook({"type": "A" * 200, "severity": "low"})
        assert len(alert.alert_type) <= 50

    def test_source_ip_truncated(self):
        alert = parse_aegis_webhook({"type": "probe", "severity": "low", "source_ip": "9" * 200})
        assert len(alert.source_ip) <= 45

    def test_details_limited_to_10_keys(self):
        alert = parse_aegis_webhook({
            "type": "probe",
            "severity": "low",
            "details": {f"k{i}": "val" for i in range(20)},
        })
        assert len(alert.details) <= 10

    def test_log_truncated_at_500(self):
        alert = parse_aegis_webhook({"type": "probe", "severity": "low", "log": "X" * 2000})
        assert len(alert.raw_log) <= 500


# ── Integración AEGIS→ENLIL (nueva arquitectura: /query + X-Api-Key) ─────────

class TestAegisIntegration:
    def test_aegis_analyze_endpoint_removed(self, aegis_client):
        """El endpoint especial /aegis/analyze fue eliminado — AEGIS usa /query con API key."""
        client, _ = aegis_client
        resp = client.post(
            "/aegis/analyze",
            json={"type": "intrusion", "severity": "high"},
        )
        assert resp.status_code == 404

    def test_aegis_query_via_standard_endpoint(self, aegis_client):
        """AEGIS envía alertas formateadas a /query con X-Api-Key."""
        client, mock_orch = aegis_client
        mock_orch.query = AsyncMock(return_value=_make_decree("bloquear IP"))

        from api import app
        from enlil.auth import require_auth

        async def _mock_auth():
            return {"id": "aegis-internal", "monthly_token_budget": 999_999_999,
                    "max_requests_per_hour": 10000, "max_total_requests": None}

        app.dependency_overrides[require_auth] = _mock_auth
        try:
            with patch("api.log_usage"):
                resp = client.post(
                    "/query",
                    json={
                        "query": "Alerta AEGIS — Tipo: intrusion | Severidad: high | IP origen: 10.0.0.1",
                        "context": "Eres el Consejo de ENLIL analizando una alerta del sistema AEGIS.",
                        "budget_tier": "full",
                    },
                    headers={"X-Api-Key": "enlil_test_key"},
                )
        finally:
            app.dependency_overrides.pop(require_auth, None)

        assert resp.status_code == 200
        data = resp.json()
        assert "decree_id" in data
        assert "synthesis" in data
        assert "gods_convened" in data

    def test_aegis_query_without_api_key_rejected(self, aegis_client):
        """Sin X-Api-Key, /query devuelve 401."""
        client, _ = aegis_client
        resp = client.post(
            "/query",
            json={"query": "Alerta AEGIS test", "budget_tier": "minimal"},
        )
        assert resp.status_code == 401

    def test_aegis_history_filters_correctly(self, aegis_client):
        client, mock_orch = aegis_client

        aegis_d = MagicMock()
        aegis_d.query = "Alerta AEGIS tipo DDoS"
        aegis_d.id = "aaa"
        aegis_d.timestamp = "2026-01-01"
        aegis_d.synthesis = "bloquear"
        aegis_d.gods_convened = ["ninurta"]

        other_d = MagicMock()
        other_d.query = "Consulta sobre arquitectura"
        other_d.id = "bbb"

        mock_orch.history = MagicMock(return_value=[aegis_d, other_d])

        resp = client.get("/aegis/history")
        assert resp.status_code == 200
        ids = [d["id"] for d in resp.json()]
        assert "aaa" in ids
        assert "bbb" not in ids


# ── Algoritmos evolutivos ─────────────────────────────────────────────────────

class TestWeightedSelection:
    def test_claude_always_selected(self):
        pantheon = build_default_pantheon()
        for _ in range(20):
            result = weighted_selection(["security"], pantheon, "standard")
            assert "claude" in result

    def test_minimal_returns_two_gods(self):
        pantheon = build_default_pantheon()
        result = weighted_selection(["security"], pantheon, "minimal")
        assert "claude" in result
        assert len(result) <= 2

    def test_full_returns_all_gods(self):
        pantheon = build_default_pantheon()
        result = weighted_selection(["security"], pantheon, "full")
        assert set(result) == set(pantheon.keys())

    def test_standard_returns_four_gods(self):
        pantheon = build_default_pantheon()
        result = weighted_selection(["security"], pantheon, "standard")
        assert len(result) <= 4
        assert len(result) >= 2

    def test_high_reputation_god_selected_more_often(self):
        pantheon = build_default_pantheon()
        # Dar reputación muy alta a ninurta en security
        pantheon["ninurta"].reputation["security"] = 0.99
        counts = {"ninurta": 0, "enki": 0, "inanna": 0}
        for _ in range(50):
            result = weighted_selection(["security"], pantheon, "standard")
            for god in counts:
                if god in result:
                    counts[god] += 1
        # Ninurta debería aparecer mucho más que los otros
        assert counts["ninurta"] > counts["enki"] + counts["inanna"]

    def test_penalized_god_selected_less(self):
        pantheon = build_default_pantheon()
        # Ninurta penalizado en security, enki con alta reputación en technical
        for d in pantheon["ninurta"].domains:
            pantheon["ninurta"].reputation[d] = 0.10
        pantheon["enki"].reputation["technical"] = 0.95
        counts = {"ninurta": 0, "enki": 0}
        for _ in range(60):
            result = weighted_selection(["technical"], pantheon, "standard")
            for god in counts:
                if god in result:
                    counts[god] += 1
        assert counts["enki"] > counts["ninurta"]

    def test_no_duplicates_in_result(self):
        pantheon = build_default_pantheon()
        for _ in range(30):
            result = weighted_selection(["technical"], pantheon, "full")
            assert len(result) == len(set(result))


class TestApplyDecay:
    def test_inactive_god_decays_toward_neutral(self):
        pantheon = build_default_pantheon()
        pantheon["enki"].reputation["technical"] = 0.9
        apply_decay(["claude"], pantheon)
        new_score = pantheon["enki"].reputation["technical"]
        assert new_score < 0.9
        assert new_score > 0.5  # no cae de golpe

    def test_active_god_not_decayed(self):
        pantheon = build_default_pantheon()
        pantheon["claude"].reputation["context"] = 0.9
        apply_decay(["claude"], pantheon)
        assert pantheon["claude"].reputation["context"] == 0.9

    def test_below_neutral_decays_upward(self):
        pantheon = build_default_pantheon()
        pantheon["ninurta"].reputation["security"] = 0.1
        apply_decay(["claude"], pantheon)
        assert pantheon["ninurta"].reputation["security"] > 0.1

    def test_decay_rate_applied_correctly(self):
        pantheon = build_default_pantheon()
        pantheon["enki"].reputation["technical"] = 0.8
        apply_decay([], pantheon)
        expected = round(0.8 + DECAY_RATE * (0.5 - 0.8), 4)
        assert pantheon["enki"].reputation["technical"] == expected


class TestFitnessReport:
    def test_report_includes_all_gods(self):
        pantheon = build_default_pantheon()
        report = fitness_report(pantheon)
        assert set(report["gods"].keys()) == set(pantheon.keys())

    def test_report_structure(self):
        pantheon = build_default_pantheon()
        report = fitness_report(pantheon)
        for god_data in report["gods"].values():
            assert "global_fitness" in god_data
            assert "domain_fitness" in god_data
            assert "penalized" in god_data
            assert "selection_pressure" in god_data

    def test_penalized_flag_set_below_threshold(self):
        pantheon = build_default_pantheon()
        for d in pantheon["ninurta"].domains:
            pantheon["ninurta"].reputation[d] = 0.1
        report = fitness_report(pantheon)
        assert report["gods"]["ninurta"]["penalized"] is True

    def test_healthy_god_not_penalized(self):
        pantheon = build_default_pantheon()
        report = fitness_report(pantheon)
        assert report["gods"]["claude"]["penalized"] is False

    def test_constants_in_report(self):
        pantheon = build_default_pantheon()
        report = fitness_report(pantheon)
        assert report["exploration_rate"] == EXPLORATION_RATE
        assert report["decay_rate"] == DECAY_RATE


class TestOpenRouterMode:
    """Verifica que en modo OpenRouter los modelos no se remapean."""

    def test_openrouter_mode_uses_original_model(self):
        from enlil.council import Council
        from enlil.gods.registry import build_default_pantheon
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test", "ANTHROPIC_API_KEY": ""}):
            with patch("openai.AsyncOpenAI"):
                council = Council(build_default_pantheon())
                assert council.mode == "openrouter"
                assert council._resolve_model("openai/gpt-4o") == "openai/gpt-4o"
                assert council._resolve_model("google/gemini-flash-1.5") == "google/gemini-flash-1.5"
                assert council._resolve_model("mistralai/mistral-large") == "mistralai/mistral-large"

    def test_anthropic_mode_remaps_all_to_claude(self):
        from enlil.council import Council
        from enlil.gods.registry import build_default_pantheon
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "", "ANTHROPIC_API_KEY": "sk-ant-test"}):
            with patch("openai.AsyncOpenAI"):
                council = Council(build_default_pantheon())
                assert council.mode == "anthropic"
                assert "claude" in council._resolve_model("openai/gpt-4o")
                assert "claude" in council._resolve_model("mistralai/mistral-large")

    def test_registry_uses_correct_claude_model(self):
        from enlil.gods.registry import build_default_pantheon
        pantheon = build_default_pantheon()
        assert pantheon["claude"].model == "anthropic/claude-sonnet-5"


class TestQdrantMemoryStore:
    """Verifica el comportamiento del store cuando Qdrant no está disponible."""

    def test_unavailable_without_api_key(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "", "OPENAI_API_KEY": ""}):
            store = QdrantMemoryStore(path="", url="")
            assert store.is_available is False
            assert store.mode == "inactive"

    def test_store_noop_when_unavailable(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "", "OPENAI_API_KEY": ""}):
            store = QdrantMemoryStore(path="", url="")
            store.store(_make_decree())  # no debe lanzar excepción

    def test_search_returns_empty_when_unavailable(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "", "OPENAI_API_KEY": ""}):
            store = QdrantMemoryStore(path="", url="")
            assert store.search("consulta de prueba") == ""

    def test_count_returns_zero_when_unavailable(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "", "OPENAI_API_KEY": ""}):
            store = QdrantMemoryStore(path="", url="")
            assert store.count() == 0

    def test_active_when_api_key_and_qdrant(self):
        mock_client = MagicMock()
        mock_client.get_collections.return_value = MagicMock(collections=[])

        mock_qdrant_module = MagicMock()
        mock_qdrant_module.QdrantClient.return_value = mock_client
        mock_models_module = MagicMock()

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test"}):
            with patch.dict("sys.modules", {
                "qdrant_client": mock_qdrant_module,
                "qdrant_client.models": mock_models_module,
            }):
                with patch("openai.OpenAI"):
                    store = QdrantMemoryStore(path="/tmp/test_qdrant")
                    assert store.is_available is True
                    assert store.mode == "embedded"


class TestModeEndpoint:
    def test_mode_endpoint_returns_200(self, aegis_client):
        client, mock_orch = aegis_client
        mock_orch.system_mode = MagicMock(return_value={
            "council_mode": "anthropic",
            "qdrant_active": False,
            "memory_backend": "fts",
            "gods_models": {},
            "openrouter_key_set": False,
        })
        resp = client.get("/mode")
        assert resp.status_code == 200
        data = resp.json()
        assert "council_mode" in data
        assert "qdrant_active" in data
        assert "memory_backend" in data


class TestEvolutionEndpoint:
    def test_evolution_endpoint_returns_200(self, aegis_client):
        client, mock_orch = aegis_client
        mock_orch.evolution_fitness = MagicMock(return_value={
            "gods": {},
            "exploration_rate": 0.15,
            "decay_rate": 0.02,
            "penalty_threshold": 0.25,
        })
        resp = client.get("/evolution")
        assert resp.status_code == 200
        data = resp.json()
        assert "gods" in data
        assert "exploration_rate" in data


# ── MetaObserver ──────────────────────────────────────────────────────────────

def _make_decree_full(query="consulta técnica", domains=None, gods=None,
                      synthesis="síntesis", budget_tier="standard",
                      latency=500.0, dissent=None) -> Decree:
    gods = gods or ["claude", "enki"]
    domains = domains or ["technical"]
    voices = [
        GodVoice(g, "claude-sonnet-4-6", f"respuesta de {g}", 100, latency, dissent=dissent)
        for g in gods
    ]
    return Decree(
        query=query, domains=domains, gods_convened=gods,
        synthesis=synthesis, voices=voices,
        budget_tier=budget_tier,
    )


class TestMetaObserver:
    def _store_with_decrees(self, decrees):
        store = MagicMock()
        store.recent.return_value = decrees
        return store

    def test_no_decrees_returns_learning_status(self):
        store = self._store_with_decrees([])
        obs = MetaObserver(store)
        result = obs.patterns()
        assert result["status"] == "learning"
        assert result["decree_count"] == 0

    def test_patterns_returns_active_with_data(self):
        decrees = [_make_decree_full() for _ in range(3)]
        store = self._store_with_decrees(decrees)
        obs = MetaObserver(store)
        result = obs.patterns()
        assert result["status"] == "active"
        assert result["decree_count"] == 3

    def test_top_god_per_domain_populated(self):
        decrees = [
            _make_decree_full(domains=["security"], gods=["ninurta", "claude"]),
            _make_decree_full(domains=["security"], gods=["ninurta"]),
        ]
        store = self._store_with_decrees(decrees)
        obs = MetaObserver(store)
        result = obs.patterns()
        security_gods = [e["god"] for e in result["top_god_per_domain"]["security"]]
        assert "ninurta" in security_gods
        assert result["top_god_per_domain"]["security"][0]["god"] == "ninurta"

    def test_dissent_ratio_tracked(self):
        decrees = [
            _make_decree_full(gods=["claude"], dissent="no estoy de acuerdo"),
            _make_decree_full(gods=["claude"], dissent=None),
        ]
        store = self._store_with_decrees(decrees)
        obs = MetaObserver(store)
        result = obs.patterns()
        assert "claude" in result["dissent_ratio"]
        assert result["dissent_ratio"]["claude"] == 0.5

    def test_avg_latency_calculated(self):
        decrees = [
            _make_decree_full(gods=["claude"], latency=1000.0),
            _make_decree_full(gods=["claude"], latency=2000.0),
        ]
        store = self._store_with_decrees(decrees)
        obs = MetaObserver(store)
        result = obs.patterns()
        assert result["avg_latency_ms"]["claude"] == 1500.0

    def test_budget_distribution_counted(self):
        decrees = [
            _make_decree_full(budget_tier="minimal"),
            _make_decree_full(budget_tier="minimal"),
            _make_decree_full(budget_tier="full"),
        ]
        store = self._store_with_decrees(decrees)
        obs = MetaObserver(store)
        result = obs.patterns()
        assert result["budget_distribution"]["minimal"] == 2
        assert result["budget_distribution"]["full"] == 1

    def test_observe_is_callable(self):
        store = self._store_with_decrees([])
        obs = MetaObserver(store)
        obs.observe(_make_decree_full())  # no debe lanzar excepción

    def test_recommend_gods_uses_history(self):
        decrees = [
            _make_decree_full(domains=["security"], gods=["ninurta", "claude"]),
            _make_decree_full(domains=["security"], gods=["ninurta"]),
        ]
        store = self._store_with_decrees(decrees)
        obs = MetaObserver(store)
        recommended = obs.recommend_gods(["security"], ["claude", "enki", "ninurta"])
        assert recommended[0] == "ninurta"

    def test_recommend_gods_falls_back_without_history(self):
        store = self._store_with_decrees([])
        obs = MetaObserver(store)
        available = ["claude", "enki"]
        assert obs.recommend_gods(["technical"], available) == available


class TestMetaEndpoint:
    def test_meta_endpoint_returns_200(self, aegis_client):
        client, mock_orch = aegis_client
        mock_orch.meta_patterns = MagicMock(return_value={
            "status": "active",
            "decree_count": 5,
        })
        resp = client.get("/meta")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
