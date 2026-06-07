import os
os.environ.setdefault("OPENROUTER_API_KEY", "test")
os.environ.setdefault("ENLIL_DB", ":memory:")

import pytest
from unittest.mock import AsyncMock, MagicMock
from enlil.synthesis_evaluator import SynthesisEvaluator
from enlil.decrees.decree import Decree, GodVoice


def make_decree(query="¿Cómo mejorar seguridad?", synthesis="Usar firewalls.", score_context=None):
    return Decree(
        query=query, synthesis=synthesis,
        gods_convened=["Claude", "Ninurta"], domains=["security", "technical"],
        voices=[GodVoice("Claude", "claude-sonnet-4-6", "R1", 100, 500.0),
                GodVoice("Ninurta", "nemotron-120b", "R2", 80, 400.0)]
    )


def make_evaluator(api_response='{"score": 7, "reasoning": "buena síntesis"}'):
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=MagicMock(
        choices=[MagicMock(message=MagicMock(content=api_response))],
        usage=MagicMock(total_tokens=50)
    ))
    mock_council = MagicMock()
    mock_council._anthropic_client = None
    mock_council._client = mock_client
    mock_council.mode = "openrouter"
    mock_council._resolve_model = lambda m: m
    mock_reputation = MagicMock()
    mock_pantheon = {"Claude": MagicMock(), "Ninurta": MagicMock()}
    evaluator = SynthesisEvaluator(mock_council, mock_reputation, mock_pantheon)
    return evaluator, mock_reputation


class TestSynthesisEvaluator:
    @pytest.mark.asyncio
    async def test_score_parsed_correctly(self):
        ev, _ = make_evaluator('{"score": 7, "reasoning": "buena"}')
        result = await ev.evaluate(make_decree())
        assert result["score"] == 7
        assert result["reasoning"] == "buena"

    @pytest.mark.asyncio
    async def test_score_gte_6_is_useful(self):
        ev, _ = make_evaluator('{"score": 7, "reasoning": "ok"}')
        result = await ev.evaluate(make_decree())
        assert result["useful"] is True

    @pytest.mark.asyncio
    async def test_score_lt_6_is_not_useful(self):
        ev, _ = make_evaluator('{"score": 4, "reasoning": "incompleto"}')
        result = await ev.evaluate(make_decree())
        assert result["useful"] is False

    @pytest.mark.asyncio
    async def test_score_10_is_useful(self):
        ev, _ = make_evaluator('{"score": 10, "reasoning": "perfecto"}')
        result = await ev.evaluate(make_decree())
        assert result["useful"] is True

    @pytest.mark.asyncio
    async def test_score_0_is_not_useful(self):
        ev, _ = make_evaluator('{"score": 0, "reasoning": "inútil"}')
        result = await ev.evaluate(make_decree())
        assert result["useful"] is False

    @pytest.mark.asyncio
    async def test_api_failure_returns_none(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API error"))
        mock_council = MagicMock()
        mock_council._client = mock_client
        mock_council.mode = "openrouter"
        mock_council._resolve_model = lambda m: m
        ev = SynthesisEvaluator(mock_council, MagicMock(), {})
        result = await ev.evaluate(make_decree())
        assert result["score"] is None
        assert result["useful"] is None

    @pytest.mark.asyncio
    async def test_json_parse_failure_returns_none(self):
        ev, _ = make_evaluator("esto no es json")
        result = await ev.evaluate(make_decree())
        assert result["score"] is None

    @pytest.mark.asyncio
    async def test_reputation_updated_on_success(self):
        ev, mock_rep = make_evaluator('{"score": 8, "reasoning": "excelente"}')
        decree = make_decree()
        await ev.evaluate(decree)
        mock_rep.record_feedback.assert_called_once_with(
            decree.gods_convened, decree.domains, True, ev.pantheon
        )

    @pytest.mark.asyncio
    async def test_reputation_not_updated_on_failure(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("fallo"))
        mock_council = MagicMock()
        mock_council._client = mock_client
        mock_council.mode = "openrouter"
        mock_council._resolve_model = lambda m: m
        mock_rep = MagicMock()
        ev = SynthesisEvaluator(mock_council, mock_rep, {})
        await ev.evaluate(make_decree())
        mock_rep.record_feedback.assert_not_called()

    @pytest.mark.asyncio
    async def test_evaluate_returns_dict_structure(self):
        ev, _ = make_evaluator('{"score": 6, "reasoning": "aceptable"}')
        result = await ev.evaluate(make_decree())
        assert "score" in result and "reasoning" in result and "useful" in result
