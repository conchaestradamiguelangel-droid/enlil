"""TEST 01B — retry de voz (máx. 2 intentos), deadline único, cancelación
real (interna Y externa). ENLIL_TEST01B_AUDITORIA_DISENO_V3/V4/V5.md."""
import asyncio
import os
import time
import pytest
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("OPENROUTER_API_KEY", "sk-or-test")


@pytest.fixture(autouse=True)
def _enlil_enabled_for_council_calls(monkeypatch):
    """Estos tests llaman a Council.consult_god()/convene() directamente contra
    un cliente mockeado -- necesitan el kill switch en ON solo dentro de cada
    test, nunca en el proceso real. No toca .env ni el comportamiento
    productivo de _enlil_enabled()."""
    monkeypatch.setenv("ENLIL_ENABLED", "true")
    # Guardarrail economico (fase 2): caps generosos solo para que estos
    # tests mockeados lleguen a la logica que estan probando, en una BD
    # en memoria propia por conexion -- no comparten estado entre tests.
    monkeypatch.setenv("ENLIL_MAX_COST_PER_REQUEST_USD", "10")
    monkeypatch.setenv("ENLIL_MAX_COST_DAILY_USD", "1000")
    monkeypatch.setenv("ENLIL_MAX_COST_MONTHLY_USD", "10000")
    monkeypatch.setenv("ENLIL_COST_LEDGER_DB", ":memory:")
    # Pricing verificado (fase 2, cierre de garantias): VERIFIED_MODEL_PRICING
    # esta vacia en produccion a proposito -- estos tests inyectan precios
    # FICTICIOS explicitos solo para poder llegar a la logica que prueban,
    # nunca se presentan como precios reales. Cubre "test-model" (el modelo
    # mockeado de estos tests) y "claude-sonnet-5" (fallback Anthropic por
    # defecto si algun test dispara esa rama).
    from enlil import pricing as _pricing
    monkeypatch.setattr(_pricing, "VERIFIED_MODEL_PRICING", {
        "test-model": _pricing.ModelPricing(
            input_usd_per_1k=0.003, output_usd_per_1k=0.003, verified=True, source="test-fixture"
        ),
        "claude-sonnet-5": _pricing.ModelPricing(
            input_usd_per_1k=0.003, output_usd_per_1k=0.003, verified=True, source="test-fixture"
        ),
    })
    # Input accounting verificado (cierre de garantia adicional): pricing
    # verificado ya NO basta por si solo -- reserve() exige ademas un
    # metodo de contabilizacion de input verificado para el modelo,
    # independiente del pricing. Ficticio, solo para estos tests.
    from enlil import input_accounting as _input_accounting
    monkeypatch.setattr(_input_accounting, "VERIFIED_INPUT_ACCOUNTING", {
        "test-model": _input_accounting.InputAccountingProfile(
            strategy=_input_accounting.AccountingStrategy.STATIC_DOCUMENTED_BOUND,
            verified=True, source="test-fixture",
        ),
        "claude-sonnet-5": _input_accounting.InputAccountingProfile(
            strategy=_input_accounting.AccountingStrategy.STATIC_DOCUMENTED_BOUND,
            verified=True, source="test-fixture",
        ),
    })


from enlil.council import Council
from enlil.gods.base import GodProfile


def _make_council(names=("MOCK_GOD",), timeout_map=None):
    pantheon = {n: GodProfile(name=n, model="test-model", role="mock", domains=["consulta"]) for n in names}
    council = Council(pantheon=pantheon)
    council._anthropic_client = None
    return council


def _resp(content, finish_reason="stop", total_tokens=100):
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    resp.choices[0].message.refusal = None
    resp.choices[0].message.tool_calls = None
    resp.choices[0].message.function_call = None
    resp.choices[0].finish_reason = finish_reason
    resp.usage = MagicMock()
    resp.usage.total_tokens = total_tokens
    resp.usage.prompt_tokens = 10
    resp.usage.completion_tokens = total_tokens - 10
    resp.usage.completion_tokens_details = None
    resp.model = "test-model"
    resp.id = "gen-123"
    return resp


class TestRetrySimple:
    def test_intento1_empty_length_intento2_complete_retry_count_1(self):
        council = _make_council()
        calls = []

        async def fake_create(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return _resp("", finish_reason="length")
            return _resp("respuesta completa al fin", finish_reason="stop")

        council._client = MagicMock()
        council._client.chat.completions.create = AsyncMock(side_effect=fake_create)

        deadline = time.monotonic() + 300.0
        result = asyncio.run(council._consult_god_with_retry(
            "MOCK_GOD", "query", "", max_tokens=100, deadline=deadline,
        ))
        assert len(calls) == 2
        assert result.retry_count == 1
        assert result.voice_status == "complete"
        assert result.content == "respuesta completa al fin"

    def test_ambos_intentos_fallan_retry_count_fijo_nunca_tercero(self):
        council = _make_council()
        calls = []

        async def fake_create(**kwargs):
            calls.append(kwargs)
            return _resp("", finish_reason="length")

        council._client = MagicMock()
        council._client.chat.completions.create = AsyncMock(side_effect=fake_create)

        deadline = time.monotonic() + 300.0
        result = asyncio.run(council._consult_god_with_retry(
            "MOCK_GOD", "query", "", max_tokens=100, deadline=deadline,
        ))
        assert len(calls) == 2, "nunca debe haber un tercer intento"
        assert result.retry_count == 1
        assert result.voice_status == "empty"

    def test_timeout_en_intento1_no_reintenta(self):
        council = _make_council()

        async def fake_create(**kwargs):
            await asyncio.sleep(10)
            return _resp("nunca llega")

        council._client = MagicMock()
        council._client.chat.completions.create = AsyncMock(side_effect=fake_create)

        deadline = time.monotonic() + 300.0
        result = asyncio.run(asyncio.wait_for(
            council._consult_god_with_retry(
                "MOCK_GOD", "query", "", max_tokens=100, deadline=deadline, timeout_override=0.05,
            ),
            timeout=5.0,
        ))
        assert result.voice_status == "timeout"
        assert result.retry_count == 0

    def test_filtered_nunca_reintenta(self):
        council = _make_council()
        calls = []

        async def fake_create(**kwargs):
            calls.append(kwargs)
            return _resp("contenido filtrado", finish_reason="content_filter")

        council._client = MagicMock()
        council._client.chat.completions.create = AsyncMock(side_effect=fake_create)

        deadline = time.monotonic() + 300.0
        result = asyncio.run(council._consult_god_with_retry(
            "MOCK_GOD", "query", "", max_tokens=100, deadline=deadline,
        ))
        assert len(calls) == 1
        assert result.voice_status == "filtered"
        assert result.retry_count == 0


class TestDeadlineNoSeExtiendeConRetry:
    def test_deadline_insuficiente_no_lanza_segundo_intento(self):
        council = _make_council()
        calls = []

        async def fake_create(**kwargs):
            calls.append(kwargs)
            return _resp("", finish_reason="length")

        council._client = MagicMock()
        council._client.chat.completions.create = AsyncMock(side_effect=fake_create)

        # Deadline apenas por encima de "ahora" -- no hay margen para un
        # segundo intento completo (GOD_TIMEOUTS por defecto es 45s).
        deadline = time.monotonic() + 0.01
        result = asyncio.run(council._consult_god_with_retry(
            "MOCK_GOD", "query", "", max_tokens=100, deadline=deadline,
        ))
        assert len(calls) == 1, "sin margen de deadline, no se lanza el retry"
        assert result.retry_count == 0
        assert result.voice_status == "empty"


class TestCancelacionReal:
    def test_convene_cancela_tareas_pendientes_de_verdad(self):
        """No solo retorno temprano -- la tarea NUNCA llega a completar su
        efecto tras la cancelación (V5 §5.1)."""
        council = _make_council(names=("SLOW_GOD",))
        side_effect_ran = {"value": False}

        async def fake_create(**kwargs):
            await asyncio.sleep(5.0)
            side_effect_ran["value"] = True
            return _resp("tarde")

        council._client = MagicMock()
        council._client.chat.completions.create = AsyncMock(side_effect=fake_create)

        deadline = time.monotonic() + 0.2
        results = asyncio.run(council.convene(["SLOW_GOD"], "query", deadline=deadline))
        assert len(results) == 1
        assert results[0].voice_status == "timeout"
        assert side_effect_ran["value"] is False, (
            "la tarea debió cancelarse de verdad -- si esto es True, "
            "convene() solo dejó de esperar mientras la llamada seguía viva"
        )

    def test_wait_for_externo_cancela_y_recoge_tareas(self):
        """Reproduce el patrón real de /task: asyncio.wait_for(...) más
        corto que convene() cancelando desde fuera."""
        council = _make_council(names=("SLOW_GOD",))
        side_effect_ran = {"value": False}

        async def fake_create(**kwargs):
            await asyncio.sleep(5.0)
            side_effect_ran["value"] = True
            return _resp("tarde")

        council._client = MagicMock()
        council._client.chat.completions.create = AsyncMock(side_effect=fake_create)

        async def run():
            deadline = time.monotonic() + 300.0  # deadline interno generoso
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(
                    council.convene(["SLOW_GOD"], "query", deadline=deadline),
                    timeout=0.2,   # el timeout EXTERNO es el que corta, no el interno
                )
            await asyncio.sleep(0.1)  # dar tiempo a que el finally termine de recoger

        asyncio.run(run())
        assert side_effect_ran["value"] is False, (
            "el timeout externo (patrón /task) debe cancelar las tareas hijas "
            "de verdad, no dejarlas huérfanas corriendo en background"
        )

    def test_ningun_resultado_tardio_se_incorpora(self):
        council = _make_council(names=("A", "B"))
        calls_b = {"count": 0}

        async def fake_create(**kwargs):
            model = kwargs.get("model", "")
            await asyncio.sleep(5.0)
            calls_b["count"] += 1
            return _resp("tarde")

        council._client = MagicMock()
        council._client.chat.completions.create = AsyncMock(side_effect=fake_create)

        deadline = time.monotonic() + 0.2
        results = asyncio.run(council.convene(["A", "B"], "query", deadline=deadline))
        assert len(results) == 2
        assert all(r.voice_status == "timeout" for r in results)
        assert calls_b["count"] == 0
