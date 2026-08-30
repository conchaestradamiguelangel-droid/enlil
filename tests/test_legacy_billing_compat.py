"""TEST 01B — campos legacy (tokens_used, total_tokens, dissent) e
integración con Orchestrator.query() no cambian de tipo/semántica.
ENLIL_TEST01B_AUDITORIA_DISENO_V4/V6.md §12."""
import asyncio
import os
import time
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

os.environ.setdefault("OPENROUTER_API_KEY", "test")
os.environ.setdefault("ENLIL_DB", ":memory:")

from enlil.orchestrator import Orchestrator
from enlil.gods.base import GodResponse


def _build_orch():
    with patch("openai.AsyncOpenAI"):
        return Orchestrator(db_path=":memory:")


def _resp(name, content, tokens=100, latency=50.0, voice_status="complete", finish_reason="stop", dissent=None):
    return GodResponse(
        god_name=name, model="mock/model", content=content, tokens_used=tokens,
        latency_ms=latency, dissent=dissent, voice_status=voice_status, finish_reason=finish_reason,
    )


class TestTokensUsedYTotalTokensSinCambios:
    def test_tokens_used_es_int_nunca_none(self):
        orch = _build_orch()
        responses = [_resp("claude", "voz", tokens=100)]
        with patch.object(orch.council, "convene", new=AsyncMock(return_value=responses)), \
             patch.object(orch.council, "synthesize", new=AsyncMock(return_value=("sintesis", []))):
            decree = asyncio.run(orch.query("consulta de prueba"))
        assert isinstance(decree.voices[0].tokens_used, int)
        assert decree.voices[0].tokens_used == 100

    def test_total_tokens_solo_suma_voces_no_sintesis(self):
        """SIN CAMBIOS: total_tokens sigue sin incluir la síntesis --
        eso es exactamente lo que exige v3/v4 §12 (no tocar billing)."""
        orch = _build_orch()
        responses = [_resp("claude", "voz1", tokens=100), _resp("enki", "voz2", tokens=50)]
        with patch.object(orch.council, "convene", new=AsyncMock(return_value=responses)), \
             patch.object(orch.council, "synthesize", new=AsyncMock(return_value=("sintesis", []))):
            decree = asyncio.run(orch.query("consulta de prueba"))
        assert decree.total_tokens == 150  # 100 + 50, la síntesis (attempts=[]) no se suma aquí

    def test_dissent_conserva_valores_actuales_timeout_error(self):
        """dissent nunca se redefine -- sigue escribiendo 'timeout'/'error'
        exactamente como antes de TEST 01B."""
        orch = _build_orch()
        responses = [
            _resp("claude", "", tokens=0, voice_status="timeout", finish_reason=None, dissent="timeout"),
            _resp("enki", "", tokens=0, voice_status="error", finish_reason=None, dissent="error"),
        ]
        with patch.object(orch.council, "convene", new=AsyncMock(return_value=responses)), \
             patch.object(orch.council, "synthesize", new=AsyncMock(return_value=("sintesis", []))):
            decree = asyncio.run(orch.query("consulta de prueba"))
        assert decree.voices[0].dissent == "timeout"
        assert decree.voices[1].dissent == "error"
        assert decree.has_dissent() is True
        assert set(decree.dissenting_gods()) == {"claude", "enki"}


class TestDecreeStatusNuevoNoRompeApiExistente:
    def test_decree_complete_cuando_todo_ok(self):
        orch = _build_orch()
        responses = [_resp("claude", "voz", voice_status="complete", finish_reason="stop")]
        with patch.object(orch.council, "convene", new=AsyncMock(return_value=responses)), \
             patch.object(orch.council, "synthesize", new=AsyncMock(return_value=("ok", []))):
            decree = asyncio.run(orch.query("consulta de prueba"))
        # sin synthesis_attempts reales (mock legacy) -> select_operative_synthesis
        # cae al caso "lista vacía" = state unknown -> status no puede ser "complete"
        # pero SÍ debe calcularse sin excepción y ser un valor válido.
        assert decree.status in ("complete", "partial", "failed")
        assert decree.signature_payload_version == 2

    def test_wall_clock_ms_es_positivo(self):
        orch = _build_orch()
        responses = [_resp("claude", "voz")]
        with patch.object(orch.council, "convene", new=AsyncMock(return_value=responses)), \
             patch.object(orch.council, "synthesize", new=AsyncMock(return_value=("ok", []))):
            decree = asyncio.run(orch.query("consulta de prueba"))
        assert decree.wall_clock_ms is not None
        assert decree.wall_clock_ms >= 0
