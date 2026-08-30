"""TEST 01B — síntesis: máximo 2 intentos totales (402 incluido), estados
degradados, synthesis_attempts completo. ENLIL_TEST01B_AUDITORIA_DISENO_V4/V6.md."""
import asyncio
import os
import time
import pytest
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("OPENROUTER_API_KEY", "sk-or-test")

import openai as _oai
from enlil.council import Council
from enlil.gods.base import GodProfile, GodResponse


def _make_council():
    pantheon = {"MOCK_GOD": GodProfile(name="MOCK_GOD", model="test-model", role="mock", domains=["consulta"])}
    council = Council(pantheon=pantheon)
    council._anthropic_client = None
    return council


def _voice(state="complete"):
    return GodResponse(
        god_name="MOCK_GOD", model="m", content="voz", tokens_used=10, latency_ms=1.0,
        voice_status=state, finish_reason="stop" if state == "complete" else None,
    )


def _synth_resp(content, finish_reason="stop"):
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    resp.choices[0].message.refusal = None
    resp.choices[0].message.tool_calls = None
    resp.choices[0].message.function_call = None
    resp.choices[0].finish_reason = finish_reason
    resp.usage = MagicMock()
    resp.usage.total_tokens = 200
    resp.usage.prompt_tokens = 50
    resp.usage.completion_tokens = 150
    resp.usage.completion_tokens_details = None
    resp.model = "claude-opus-5"
    resp.id = "gen-syn-1"
    return resp


class TestSintesisMaximo2Intentos:
    def test_402_incluido_dentro_del_maximo_de_2(self):
        council = _make_council()
        council._client = MagicMock()
        calls = []

        async def fake_create(**kwargs):
            calls.append(kwargs.get("max_tokens"))
            raise _oai.APIStatusError(
                message="insufficient credit", response=MagicMock(status_code=402), body=None,
            )

        council._client.chat.completions.create = AsyncMock(side_effect=fake_create)
        deadline = time.monotonic() + 300.0
        content, attempts = asyncio.run(council.synthesize([_voice()], "q", deadline=deadline))
        assert len(calls) == 2, "402 debe consumir un intento, no generar una escalera aparte"
        assert len(attempts) == 2
        assert attempts[1].max_tokens_budget < attempts[0].max_tokens_budget

    def test_truncated_reintenta_con_presupuesto_mayor(self):
        council = _make_council()
        council._client = MagicMock()
        calls = []

        async def fake_create(**kwargs):
            calls.append(kwargs.get("max_tokens"))
            if len(calls) == 1:
                return _synth_resp("cortado a mit", finish_reason="length")
            return _synth_resp("decreto completo con sello final", finish_reason="stop")

        council._client.chat.completions.create = AsyncMock(side_effect=fake_create)
        deadline = time.monotonic() + 300.0
        content, attempts = asyncio.run(council.synthesize([_voice()], "q", deadline=deadline))
        assert len(attempts) == 2
        assert attempts[1].max_tokens_budget > attempts[0].max_tokens_budget
        assert content == "decreto completo con sello final"

    def test_nunca_un_tercer_intento(self):
        council = _make_council()
        council._client = MagicMock()
        calls = []

        async def fake_create(**kwargs):
            calls.append(1)
            return _synth_resp("", finish_reason="length")

        council._client.chat.completions.create = AsyncMock(side_effect=fake_create)
        deadline = time.monotonic() + 300.0
        content, attempts = asyncio.run(council.synthesize([_voice()], "q", deadline=deadline))
        assert len(calls) == 2
        assert len(attempts) == 2

    def test_sintesis_no_propaga_excepcion_se_degrada(self):
        """Cambio deliberado respecto a pre-TEST01B: ya no se relanza la
        excepción -- se clasifica y se refleja en Decree.status."""
        council = _make_council()
        council._client = MagicMock()

        async def fake_create(**kwargs):
            raise RuntimeError("fallo catastrofico de red")

        council._client.chat.completions.create = AsyncMock(side_effect=fake_create)
        deadline = time.monotonic() + 300.0
        content, attempts = asyncio.run(council.synthesize([_voice()], "q", deadline=deadline))
        assert attempts[-1].state == "error"
        assert attempts[-1].exception_type == "RuntimeError"

    def test_todos_los_dioses_fallaron_no_llama_a_la_api(self):
        council = _make_council()
        council._client = MagicMock()
        council._client.chat.completions.create = AsyncMock()
        deadline = time.monotonic() + 300.0
        failed_voice = _voice(state="timeout")
        content, attempts = asyncio.run(council.synthesize([failed_voice], "q", deadline=deadline))
        council._client.chat.completions.create.assert_not_called()
        assert len(attempts) == 1
        assert "no pudo reunirse" in content.lower()


class TestSintesisDeadline:
    def test_sin_margen_no_lanza_segundo_intento(self):
        council = _make_council()
        council._client = MagicMock()
        calls = []

        async def fake_create(**kwargs):
            calls.append(1)
            return _synth_resp("", finish_reason="length")

        council._client.chat.completions.create = AsyncMock(side_effect=fake_create)
        deadline = time.monotonic() + 0.001
        content, attempts = asyncio.run(council.synthesize([_voice()], "q", deadline=deadline))
        assert len(calls) == 1
        assert len(attempts) == 1
