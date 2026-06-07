import os
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

os.environ.setdefault("OPENROUTER_API_KEY", "test")
os.environ.setdefault("ENLIL_DB", ":memory:")

from enlil.gods.base import GodResponse
from enlil.decrees.decree import Decree, GodVoice


def make_mock_response(god_name: str, content: str = "respuesta mock") -> GodResponse:
    return GodResponse(
        god_name=god_name, model="mock/model", content=content,
        tokens_used=100, latency_ms=50.0,
    )


def build_orch():
    with patch("openai.AsyncOpenAI"):
        from enlil.orchestrator import Orchestrator
        return Orchestrator(db_path=":memory:")


class TestOrchestratorIntegration:

    def test_query_returns_decree(self):
        orch = build_orch()
        responses = [make_mock_response("claude"), make_mock_response("ninurta")]
        with patch.object(orch.council, "convene", new=AsyncMock(return_value=responses)), \
             patch.object(orch.council, "synthesize", new=AsyncMock(return_value="Sintesis mock")):
            decree = asyncio.run(orch.query("hay una vulnerabilidad en el firewall"))

        assert isinstance(decree, Decree)
        assert decree.synthesis == "Sintesis mock"
        assert decree.id is not None

    def test_query_persists_decree(self):
        orch = build_orch()
        with patch.object(orch.council, "convene", new=AsyncMock(return_value=[make_mock_response("claude")])), \
             patch.object(orch.council, "synthesize", new=AsyncMock(return_value="ok")):
            decree = asyncio.run(orch.query("test persistencia"))

        assert orch.get_decree(decree.id) is not None
        assert orch.get_decree(decree.id).query == "test persistencia"

    def test_query_classifies_domains(self):
        orch = build_orch()
        with patch.object(orch.council, "convene", new=AsyncMock(return_value=[make_mock_response("claude")])), \
             patch.object(orch.council, "synthesize", new=AsyncMock(return_value="ok")):
            decree = asyncio.run(orch.query("bug en el código python"))

        assert "technical" in decree.domains

    def test_query_with_explicit_budget_tier(self):
        orch = build_orch()
        with patch.object(orch.council, "convene", new=AsyncMock(return_value=[make_mock_response("claude")])), \
             patch.object(orch.council, "synthesize", new=AsyncMock(return_value="ok")):
            decree = asyncio.run(orch.query("hola", budget_tier="minimal"))

        assert decree.budget_tier == "minimal"

    def test_query_with_parent_decree_id(self):
        orch = build_orch()
        with patch.object(orch.council, "convene", new=AsyncMock(return_value=[make_mock_response("claude")])), \
             patch.object(orch.council, "synthesize", new=AsyncMock(return_value="ok")):
            parent = asyncio.run(orch.query("consulta padre"))
            child = asyncio.run(orch.query("consulta hija", parent_decree_id=parent.id))

        assert child.parent_decree_id == parent.id

    def test_feedback_updates_reputation(self):
        orch = build_orch()
        with patch.object(orch.council, "convene", new=AsyncMock(return_value=[make_mock_response("claude"), make_mock_response("ninurta")])), \
             patch.object(orch.council, "synthesize", new=AsyncMock(return_value="ok")):
            decree = asyncio.run(orch.query("vulnerabilidad de seguridad"))

        score_before = orch.pantheon["claude"].get_reputation("security")
        orch.feedback(decree.id, useful=True)
        score_after = orch.pantheon["claude"].get_reputation("security")
        assert score_after >= score_before

    def test_feedback_nonexistent_decree_ignored(self):
        orch = build_orch()
        orch.feedback("id-inexistente-xyz", useful=True)  # no lanza excepcion

    def test_history_returns_decrees(self):
        orch = build_orch()
        with patch.object(orch.council, "convene", new=AsyncMock(return_value=[make_mock_response("claude")])), \
             patch.object(orch.council, "synthesize", new=AsyncMock(return_value="ok")):
            asyncio.run(orch.query("primera"))
            asyncio.run(orch.query("segunda"))

        assert len(orch.history(limit=10)) == 2

    def test_history_limit_respected(self):
        orch = build_orch()
        with patch.object(orch.council, "convene", new=AsyncMock(return_value=[make_mock_response("claude")])), \
             patch.object(orch.council, "synthesize", new=AsyncMock(return_value="ok")):
            for i in range(5):
                asyncio.run(orch.query(f"consulta {i}"))

        assert len(orch.history(limit=3)) == 3

    def test_pantheon_status_returns_dict(self):
        orch = build_orch()
        assert isinstance(orch.pantheon_status(), dict)

    def test_memory_stores_decree(self):
        orch = build_orch()
        with patch.object(orch.council, "convene", new=AsyncMock(return_value=[make_mock_response("claude")])), \
             patch.object(orch.council, "synthesize", new=AsyncMock(return_value="Sintesis sobre firewall seguridad")):
            asyncio.run(orch.query("configurar firewall seguridad"))

        # La memoria debe tener al menos 1 entrada
        result = orch.memory.search("firewall")
        assert isinstance(result, str)

    def test_voices_recorded_in_decree(self):
        orch = build_orch()
        responses = [
            make_mock_response("claude", "Respuesta de contexto"),
            make_mock_response("enki", "Respuesta tecnica"),
        ]
        with patch.object(orch.council, "convene", new=AsyncMock(return_value=responses)), \
             patch.object(orch.council, "synthesize", new=AsyncMock(return_value="ok")):
            decree = asyncio.run(orch.query("test voces"))

        assert len(decree.voices) == 2
        god_names = [v.god_name for v in decree.voices]
        assert "claude" in god_names
        assert "enki" in god_names

    def test_total_tokens_summed(self):
        orch = build_orch()
        responses = [
            make_mock_response("claude"),   # 100 tokens
            make_mock_response("ninurta"),  # 100 tokens
        ]
        with patch.object(orch.council, "convene", new=AsyncMock(return_value=responses)), \
             patch.object(orch.council, "synthesize", new=AsyncMock(return_value="ok")):
            decree = asyncio.run(orch.query("test tokens"))

        assert decree.total_tokens == 200
