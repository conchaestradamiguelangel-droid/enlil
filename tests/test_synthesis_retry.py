"""TEST 01B — síntesis: máximo 2 intentos totales (402 incluido), estados
degradados, synthesis_attempts completo. ENLIL_TEST01B_AUDITORIA_DISENO_V4/V6.md."""
import asyncio
import os
import time
import pytest
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("OPENROUTER_API_KEY", "sk-or-test")

import openai as _oai
from enlil import council as _council_module
from enlil.council import Council
from enlil.gods.base import GodProfile, GodResponse


class _FakeMonotonicClock:
    """Reloj determinista para test_sin_margen_no_lanza_segundo_intento.
    Sustituye SOLO la referencia a `time` dentro del modulo enlil.council
    (via monkeypatch.setattr(_council_module, "time", ...)) -- nunca el
    modulo `time` global compartido por el resto del proceso/asyncio.
    Devuelve la secuencia de valores dada, y si se llama mas veces de las
    previstas sigue avanzando de forma pequena y determinista (nunca
    lanza ni se congela) para no romper si el codigo productivo llegara
    a leer el reloj una vez mas de lo esperado."""

    def __init__(self, values):
        self._values = list(values)
        self._i = 0

    def monotonic(self):
        if self._i < len(self._values):
            v = self._values[self._i]
        else:
            v = self._values[-1] + 0.000001 * (self._i - len(self._values) + 1)
        self._i += 1
        return v


def _make_council():
    pantheon = {"MOCK_GOD": GodProfile(name="MOCK_GOD", model="test-model", role="mock", domains=["consulta"])}
    council = Council(pantheon=pantheon)
    council._anthropic_client = None
    return council


@pytest.fixture(autouse=True)
def _enlil_enabled_and_verified_for_synthesis(monkeypatch):
    """Council.synthesize()/_synthesis_attempt_once() ahora comparten el
    mismo kill switch y guardarrail economico que consult_god() -- estos
    tests llaman a synthesize() directamente contra un cliente mockeado,
    igual que los de consult_god en otros ficheros, asi que necesitan el
    mismo patron de fixture (ENLIL_ENABLED=true, caps generosos, pricing
    y accounting FICTICIOS solo dentro de cada test). anthropic/claude-sonnet-5
    es el modelo real que synthesize() resuelve para estos tests
    (self._anthropic_client=None -> use_opus=False ->
    self._resolve_model("anthropic/claude-sonnet-5"))."""
    monkeypatch.setenv("ENLIL_ENABLED", "true")
    monkeypatch.setenv("ENLIL_MAX_COST_PER_REQUEST_USD", "10")
    monkeypatch.setenv("ENLIL_MAX_COST_DAILY_USD", "1000")
    monkeypatch.setenv("ENLIL_MAX_COST_MONTHLY_USD", "10000")
    monkeypatch.setenv("ENLIL_COST_LEDGER_DB", ":memory:")
    from enlil import pricing as _pricing
    monkeypatch.setattr(_pricing, "VERIFIED_MODEL_PRICING", {
        "test-model": _pricing.ModelPricing(
            input_usd_per_1k=0.003, output_usd_per_1k=0.003, verified=True, source="test-fixture"
        ),
        "anthropic/claude-sonnet-5": _pricing.ModelPricing(
            input_usd_per_1k=0.003, output_usd_per_1k=0.003, verified=True, source="test-fixture"
        ),
        "claude-sonnet-5": _pricing.ModelPricing(
            input_usd_per_1k=0.003, output_usd_per_1k=0.003, verified=True, source="test-fixture"
        ),
    })
    from enlil import input_accounting as _input_accounting
    _profile = _input_accounting.InputAccountingProfile(
        strategy=_input_accounting.AccountingStrategy.STATIC_DOCUMENTED_BOUND,
        verified=True, source="test-fixture",
    )
    monkeypatch.setattr(_input_accounting, "VERIFIED_INPUT_ACCOUNTING", {
        "test-model": _profile,
        "anthropic/claude-sonnet-5": _profile,
        "claude-sonnet-5": _profile,
    })


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
    def test_sin_margen_no_lanza_segundo_intento(self, monkeypatch):
        """Antes dependia de un margen REAL de 1ms
        (`time.monotonic() + 0.001`) entre construir `deadline` y las dos
        lecturas de reloj dentro de Council.synthesize() (la comprobacion
        de margen antes del intento 1, y la comprobacion de margen para
        el retry despues) -- bajo carga (p.ej. la suite completa) el
        overhead real de asyncio/scheduling podia comerse ese margen de
        formas distintas cada vez, hacia el test intermitente (~1 de cada
        5-10 ejecuciones dentro de la suite completa, reproducido antes
        de este fix). Fix: reloj determinista inyectado SOLO en
        enlil.council (ver _FakeMonotonicClock) -- ninguna lectura de
        reloj real decide ya el resultado. El test sigue verificando
        exactamente lo mismo: con margen insuficiente, NO se lanza un
        segundo intento de sintesis."""
        council = _make_council()
        council._client = MagicMock()
        calls = []

        async def fake_create(**kwargs):
            calls.append(1)
            return _synth_resp("", finish_reason="length")

        council._client.chat.completions.create = AsyncMock(side_effect=fake_create)

        deadline = 1_000_000.001  # arbitrario -- monotonic() nunca es un timestamp real, solo se compara consigo mismo
        fake_clock = _FakeMonotonicClock([
            1_000_000.0005,  # 1: remaining_before_attempt1 = deadline - esto = 0.0005 > 0 -> SI lanza el intento 1
            1_000_000.0006,  # 2: t0 dentro de _synthesis_attempt_once
            1_000_000.0007,  # 3: latency = esto - t0 (irrelevante para la decision de retry)
            1_000_000.5,     # 4: remaining tras el intento 1 = deadline - esto < 0 -> NO lanza el intento 2
        ])
        monkeypatch.setattr(_council_module, "time", fake_clock)

        content, attempts = asyncio.run(council.synthesize([_voice()], "q", deadline=deadline))
        assert len(calls) == 1
        assert len(attempts) == 1
