"""Guardarrail economico (fase 2, v4 -- separa CONTENT bound de BILLING
bound):

1. `enlil.budget.estimate_content_token_upper_bound()`/
   `estimate_content_tokens_from_messages()` acotan SOLO el contenido de
   texto que ENLIL construye (bytes UTF-8, propiedad estructural de BPE
   a nivel de byte) -- ya NO se presentan como cota del input facturable
   TOTAL (que puede incluir framing/tools/reasoning/caching del
   proveedor), y el "+10 tokens/mensaje" de la version anterior (un
   numero inventado sin fuente) se elimino por completo.
2. `cost_guard.reserve()` exige DOS gates independientes por modelo:
   pricing verificado (enlil.pricing) Y metodo de contabilizacion de
   input verificado (enlil.input_accounting) -- probado que CUALQUIERA
   de los dos, solo, sigue denegando; ambos son necesarios.
3. Todo lo demas del turno anterior (operation_id/retries, caps
   acumulados, SQLite, estados del ledger, timeout/settle
   failure/crash, UTC, concurrencia, fallback A+B, kill switch
   superior) se conserva sin cambios de comportamiento.
"""
import asyncio
import os
import threading
import time
from datetime import datetime, timezone

import pytest
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("OPENROUTER_API_KEY", "sk-or-test")

from enlil import cost_guard, pricing, input_accounting
from enlil.budget import estimate_content_token_upper_bound, estimate_content_tokens_from_messages
from enlil.cost_guard import BudgetDeniedError, reserve, settle, settle_uncertain, release, mark_attempting
from enlil.council import Council, EnlilDisabledError
from enlil.gods.base import GodProfile


def _set_caps(monkeypatch, *, per_request="10", daily="10", monthly="10", db_path=None):
    monkeypatch.setenv("ENLIL_MAX_COST_PER_REQUEST_USD", per_request)
    monkeypatch.setenv("ENLIL_MAX_COST_DAILY_USD", daily)
    monkeypatch.setenv("ENLIL_MAX_COST_MONTHLY_USD", monthly)
    if db_path is not None:
        monkeypatch.setenv("ENLIL_COST_LEDGER_DB", db_path)


def _set_pricing(monkeypatch, **entries):
    """entries: model=(input_usd_per_1k, output_usd_per_1k[, verified]).
    Precios SIEMPRE ficticios, definidos aqui explicitamente -- nunca se
    presentan como precios reales de produccion (esa tabla esta vacia)."""
    table = {}
    for model, spec in entries.items():
        if len(spec) == 2:
            inp, out, verified = spec[0], spec[1], True
        else:
            inp, out, verified = spec
        table[model] = pricing.ModelPricing(
            input_usd_per_1k=inp, output_usd_per_1k=out, verified=verified, source="test-fixture"
        )
    monkeypatch.setattr(pricing, "VERIFIED_MODEL_PRICING", table)


def _set_accounting(monkeypatch, *models, verified=True):
    """Marca el metodo de contabilizacion de INPUT como verificado (o
    explicitamente no verificado) para los modelos dados. Estrategia
    ficticia STATIC_DOCUMENTED_BOUND -- solo para poder probar el gate,
    nunca se presenta como una estrategia real implementada."""
    strategy = (
        input_accounting.AccountingStrategy.STATIC_DOCUMENTED_BOUND
        if verified
        else input_accounting.AccountingStrategy.UNVERIFIED
    )
    table = {
        m: input_accounting.InputAccountingProfile(strategy=strategy, verified=verified, source="test-fixture")
        for m in models
    }
    monkeypatch.setattr(input_accounting, "VERIFIED_INPUT_ACCOUNTING", table)


def _set_verified(monkeypatch, **entries):
    """Combina pricing + accounting verificados para los modelos dados
    -- el caso comun en tests que no prueban especificamente el gate de
    accounting por separado. Mismo formato de entries que _set_pricing."""
    _set_pricing(monkeypatch, **entries)
    _set_accounting(monkeypatch, *entries.keys())


def _make_council(names=("MOCK_GOD",), model="test-model"):
    pantheon = {n: GodProfile(name=n, model=model, role="mock", domains=["consulta"]) for n in names}
    council = Council(pantheon=pantheon)
    council._anthropic_client = None
    return council


def _resp(content, finish_reason="stop", total_tokens=100, usage=True):
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    resp.choices[0].message.refusal = None
    resp.choices[0].message.tool_calls = None
    resp.choices[0].message.function_call = None
    resp.choices[0].finish_reason = finish_reason
    if usage:
        resp.usage = MagicMock(total_tokens=total_tokens, prompt_tokens=10, completion_tokens=max(total_tokens - 10, 0))
    else:
        resp.usage = None
    resp.model = "test-model"
    resp.id = "gen-1"
    return resp


class _FixedClock:
    def __init__(self, fixed):
        self._fixed = fixed

    def now(self, tz=None):
        return self._fixed


# ---------------------------------------------------------------------------
# 1) Content bound (bytes UTF-8) -- ya NO se presenta como billing bound
# ---------------------------------------------------------------------------

class TestContentTokenBound:
    """`estimate_content_token_upper_bound` sigue siendo una cota REAL del
    CONTENIDO de texto (bytes UTF-8, propiedad estructural de BPE a nivel
    de byte) -- lo que cambio es que ya no se llama "estimate_tokens_from_text"
    ni se presenta como cota del input facturable total. Este bloque
    prueba la propiedad matematica del contenido, no una garantia de
    facturacion."""

    def test_ascii(self):
        text = "the quick brown fox jumps over the lazy dog"
        assert estimate_content_token_upper_bound(text) == len(text.encode("utf-8"))

    def test_espanol_con_tildes_y_enies(self):
        text = "El niño comió mañana en su cumpleaños, ¡qué ilusión más grande!"
        tokens = estimate_content_token_upper_bound(text)
        assert tokens > len(text)
        assert tokens == len(text.encode("utf-8"))

    def test_unicode_emoji(self):
        text = "Deploy listo 🚀🔥 revisa el dashboard 📊✅ antes de las 5️⃣pm"
        tokens = estimate_content_token_upper_bound(text)
        assert tokens > len(text)
        assert tokens == len(text.encode("utf-8"))

    def test_codigo(self):
        code = (
            "def f(x: int, y: int = 0) -> int:\n"
            "    return (x ** 2 + y ** 2) // max(x, 1)\n"
            "\n"
            "result = [f(i, i*2) for i in range(100) if i % 3 == 0]\n"
        )
        tokens = estimate_content_token_upper_bound(code)
        assert tokens == len(code.encode("utf-8"))
        assert tokens > 0

    def test_texto_largo(self):
        long_text = ("Este es un parrafo de prueba con contenido repetido. " * 2000)
        tokens = estimate_content_token_upper_bound(long_text)
        assert tokens == len(long_text.encode("utf-8"))
        assert tokens > 50_000

    def test_vacio_es_cero(self):
        assert estimate_content_token_upper_bound("") == 0

    def test_creciente_monotono(self):
        short = estimate_content_token_upper_bound("hola")
        longer = estimate_content_token_upper_bound("hola " * 5000)
        assert longer > short

    def test_messages_es_solo_la_suma_del_contenido_sin_overhead_inventado(self):
        """La version anterior sumaba "+10 tokens/mensaje" presentado como
        margen de seguridad -- no tenia fuente verificable, se elimino.
        Ahora la funcion es exactamente la suma de las cotas de contenido,
        ni un token mas."""
        messages = [
            {"role": "system", "content": "instrucciones"},
            {"role": "user", "content": "pregunta"},
        ]
        total = estimate_content_tokens_from_messages(messages)
        raw = estimate_content_token_upper_bound("instrucciones") + estimate_content_token_upper_bound("pregunta")
        assert total == raw

    def test_estimate_tokens_from_messages_crece_con_mas_mensajes(self):
        two_msgs = estimate_content_tokens_from_messages([{"content": "hola"}, {"content": "mundo"}])
        three_msgs = estimate_content_tokens_from_messages([{"content": "hola"}, {"content": "mundo"}, {"content": "extra"}])
        assert three_msgs > two_msgs


# ---------------------------------------------------------------------------
# 2) Pricing verificado (input/output separados)
# ---------------------------------------------------------------------------

class TestPricingVerification:
    def test_produccion_real_tiene_los_9_modelos_reales_verificados(self):
        """Sin ningun monkeypatch -- confirma el estado REAL de las dos
        tablas en produccion. Poblado con datos obtenidos en vivo de
        OpenRouter (GET /api/v1/models) y https://claude.com/pricing --
        ver enlil/pricing.py y enlil/input_accounting.py para las
        fuentes/fechas exactas de cada entrada."""
        modelos_reales_del_panteon = {
            "anthropic/claude-sonnet-5",       # Claude
            "deepseek/deepseek-v4-pro",         # Enki, Nabu
            "nvidia/nemotron-3-ultra-550b-a55b",  # Ninurta
            "google/gemini-2.5-pro-preview",    # Anu
            "anthropic/claude-opus-5",          # Marduk
            "x-ai/grok-4.5",                    # Nergal
            "meta-llama/llama-4-maverick",      # Tiamat
        }
        fallback_anthropic_directo = {"claude-sonnet-5", "claude-opus-5", "claude-sonnet-4-6"}

        for model in modelos_reales_del_panteon | fallback_anthropic_directo:
            price = pricing.VERIFIED_MODEL_PRICING.get(model)
            assert price is not None and price.verified, f"pricing no verificado: {model}"
            acct = input_accounting.VERIFIED_INPUT_ACCOUNTING.get(model)
            assert acct is not None and acct.verified, f"accounting no verificado: {model}"

        # Bloqueo real documentado -- Inanna (mistralai/mistral-large-2512):
        # 0 endpoints en tiempo real en OpenRouter hoy. NO debe tener
        # entrada verificada -- si alguna vez aparece aqui sin que se haya
        # resuelto el bloqueo real, es una regresion (alguien inventando
        # una equivalencia no documentada).
        assert "mistralai/mistral-large-2512" not in pricing.VERIFIED_MODEL_PRICING
        assert "mistralai/mistral-large-2512" not in input_accounting.VERIFIED_INPUT_ACCOUNTING

    def test_input_y_output_se_facturan_a_tarifas_distintas(self, monkeypatch, tmp_path):
        _set_caps(monkeypatch, per_request="10", daily="10", monthly="10", db_path=str(tmp_path / "c.db"))
        _set_verified(monkeypatch, **{"modelo-y": (0.001, 0.001)})
        r_base = reserve("modelo-y", 500, input_tokens=1000, operation_id="op-base")
        _set_verified(monkeypatch, **{"modelo-y": (0.001, 0.01)})
        r_output_up = reserve("modelo-y", 500, input_tokens=1000, operation_id="op-out")
        assert r_output_up.estimated_usd > r_base.estimated_usd
        _set_verified(monkeypatch, **{"modelo-y": (0.01, 0.001)})
        r_input_up = reserve("modelo-y", 500, input_tokens=1000, operation_id="op-in")
        assert r_input_up.estimated_usd > r_base.estimated_usd
        assert round(r_output_up.estimated_usd, 6) != round(r_input_up.estimated_usd, 6)

    def test_estimate_cost_usd_lanza_si_falta_desglose_y_total(self, monkeypatch):
        _set_pricing(monkeypatch, **{"modelo-z": (0.001, 0.001)})
        with pytest.raises(ValueError):
            pricing.estimate_cost_usd("modelo-z")  # sin prompt+completion ni total


# ---------------------------------------------------------------------------
# 3) NUEVO -- dos gates independientes: pricing Y accounting
# ---------------------------------------------------------------------------

class TestDualVerificationGate:
    """El requisito central de este cierre: pricing verificado por si
    solo NO basta, y accounting verificado por si solo tampoco -- hacen
    falta LOS DOS para que reserve() apruebe."""

    def test_pricing_valido_accounting_no_verificado_deniega(self, monkeypatch, tmp_path):
        _set_caps(monkeypatch, per_request="10", daily="10", monthly="10", db_path=str(tmp_path / "c.db"))
        _set_pricing(monkeypatch, **{"modelo-solo-precio": (0.003, 0.003)})
        _set_accounting(monkeypatch)  # tabla vacia -- ningun modelo tiene accounting verificado
        with pytest.raises(BudgetDeniedError) as exc_info:
            reserve("modelo-solo-precio", 1000)
        assert exc_info.value.reason == "input_accounting_not_verified_fail_closed"

    def test_accounting_valido_pricing_no_verificado_deniega(self, monkeypatch, tmp_path):
        _set_caps(monkeypatch, per_request="10", daily="10", monthly="10", db_path=str(tmp_path / "c.db"))
        _set_pricing(monkeypatch)  # tabla vacia -- ningun modelo tiene pricing verificado
        _set_accounting(monkeypatch, "modelo-solo-accounting")
        with pytest.raises(BudgetDeniedError) as exc_info:
            reserve("modelo-solo-accounting", 1000)
        assert exc_info.value.reason == "pricing_not_verified_fail_closed"

    def test_accounting_marcado_no_verificado_explicitamente_deniega(self, monkeypatch, tmp_path):
        _set_caps(monkeypatch, per_request="10", daily="10", monthly="10", db_path=str(tmp_path / "c.db"))
        _set_pricing(monkeypatch, **{"modelo-w": (0.003, 0.003)})
        _set_accounting(monkeypatch, "modelo-w", verified=False)
        with pytest.raises(BudgetDeniedError) as exc_info:
            reserve("modelo-w", 1000)
        assert exc_info.value.reason == "input_accounting_not_verified_fail_closed"

    def test_ambos_verificados_reserva_correctamente(self, monkeypatch, tmp_path):
        _set_caps(monkeypatch, per_request="10", daily="10", monthly="10", db_path=str(tmp_path / "c.db"))
        _set_verified(monkeypatch, **{"modelo-completo": (0.003, 0.003)})
        r = reserve("modelo-completo", 1000)
        assert r.estimated_usd > 0

    @pytest.mark.asyncio
    async def test_solo_ambos_verificados_llega_al_mock_del_proveedor(self, monkeypatch, tmp_path):
        """Integracion real con Council: sin accounting verificado, el
        mock del proveedor NUNCA se invoca, aunque el pricing si lo este."""
        monkeypatch.setenv("ENLIL_ENABLED", "true")
        db = str(tmp_path / "dual.db")
        _set_caps(monkeypatch, per_request="10", daily="10", monthly="10", db_path=db)
        _set_pricing(monkeypatch, **{"test-model": (0.003, 0.003)})
        _set_accounting(monkeypatch)  # vacio -- accounting NO verificado

        council = _make_council()
        calls = []

        async def fake_create(**kwargs):
            calls.append(kwargs)
            return _resp("no deberia llegar aqui")

        council._client = MagicMock()
        council._client.chat.completions.create = AsyncMock(side_effect=fake_create)

        with pytest.raises(BudgetDeniedError) as exc_info:
            await council.consult_god("MOCK_GOD", "query", max_tokens=100)
        assert exc_info.value.reason == "input_accounting_not_verified_fail_closed"
        assert len(calls) == 0

        # Ahora SI verificamos accounting tambien -- debe llegar al mock.
        _set_accounting(monkeypatch, "test-model")
        await council.consult_god("MOCK_GOD", "query", max_tokens=100, operation_id="op-2")
        assert len(calls) == 1


# ---------------------------------------------------------------------------
# 4) Cap por OPERACION logica (no por intento aislado) -- sin cambios de comportamiento
# ---------------------------------------------------------------------------

class TestOperationCap:
    def test_dos_intentos_de_la_misma_operacion_superan_el_cap(self, monkeypatch, tmp_path):
        db = str(tmp_path / "c.db")
        _set_verified(monkeypatch, **{"custom/model-a": (0.003, 0.003)})
        _set_caps(monkeypatch, per_request="0.10", daily="10", monthly="10", db_path=db)
        op = "op-shared-1"
        r1 = reserve("custom/model-a", 20000, operation_id=op)
        assert round(r1.estimated_usd, 6) == 0.06
        settle(r1.id, r1.estimated_usd)
        with pytest.raises(BudgetDeniedError) as exc_info:
            reserve("custom/model-a", 20000, operation_id=op)
        assert exc_info.value.reason == "per_request_cap_exceeded"

    def test_dos_intentos_dentro_del_cap_ambos_pasan(self, monkeypatch, tmp_path):
        db = str(tmp_path / "c.db")
        _set_verified(monkeypatch, **{"custom/model-a": (0.003, 0.003)})
        _set_caps(monkeypatch, per_request="0.20", daily="10", monthly="10", db_path=db)
        op = "op-shared-2"
        r1 = reserve("custom/model-a", 20000, operation_id=op)
        settle(r1.id, r1.estimated_usd)
        r2 = reserve("custom/model-a", 20000, operation_id=op)
        assert r2.estimated_usd == r1.estimated_usd

    def test_llamada_sin_operation_id_recibe_uno_automatico(self, monkeypatch, tmp_path):
        db = str(tmp_path / "c.db")
        _set_verified(monkeypatch, **{"custom/model-a": (0.003, 0.003)})
        _set_caps(monkeypatch, per_request="10", daily="10", monthly="10", db_path=db)
        r = reserve("custom/model-a", 1000)
        assert r.operation_id
        assert len(r.operation_id) >= 16

    def test_dos_operaciones_distintas_no_comparten_cap_por_operacion(self, monkeypatch, tmp_path):
        db = str(tmp_path / "c.db")
        _set_verified(monkeypatch, **{"custom/model-a": (0.003, 0.003)})
        _set_caps(monkeypatch, per_request="0.10", daily="10", monthly="10", db_path=db)
        r_a = reserve("custom/model-a", 20000, operation_id="op-A")
        r_b = reserve("custom/model-a", 20000, operation_id="op-B")
        assert r_a.estimated_usd == r_b.estimated_usd == 0.06


# ---------------------------------------------------------------------------
# 5) Estados del ledger -- sin cambios de comportamiento
# ---------------------------------------------------------------------------

class TestLedgerStates:
    def test_release_pone_actual_usd_a_cero(self, monkeypatch, tmp_path):
        db = str(tmp_path / "c.db")
        _set_verified(monkeypatch, **{"custom/model-a": (0.003, 0.003)})
        _set_caps(monkeypatch, per_request="10", daily="0.06", monthly="10", db_path=db)
        r1 = reserve("custom/model-a", 20000)
        release(r1.id)
        r2 = reserve("custom/model-a", 20000)
        assert r2.estimated_usd == 0.06

    def test_settle_uncertain_conserva_el_worst_case_completo(self, monkeypatch, tmp_path):
        db = str(tmp_path / "c.db")
        _set_verified(monkeypatch, **{"custom/model-a": (0.003, 0.003)})
        _set_caps(monkeypatch, per_request="10", daily="0.06", monthly="10", db_path=db)
        r1 = reserve("custom/model-a", 20000)
        settle_uncertain(r1.id, r1.estimated_usd)
        with pytest.raises(BudgetDeniedError) as exc_info:
            reserve("custom/model-a", 1000)
        assert exc_info.value.reason == "daily_cap_exceeded"

    def test_settle_con_coste_real_menor_libera_diferencia(self, monkeypatch, tmp_path):
        db = str(tmp_path / "c.db")
        _set_verified(monkeypatch, **{"custom/model-a": (0.003, 0.003)})
        _set_caps(monkeypatch, per_request="10", daily="0.10", monthly="10", db_path=db)
        r1 = reserve("custom/model-a", 20000)
        settle(r1.id, 0.02)
        r2 = reserve("custom/model-a", 20000)
        assert r2.estimated_usd == 0.06

    def test_mark_attempting_no_lanza_y_no_cambia_el_monto_contado(self, monkeypatch, tmp_path):
        db = str(tmp_path / "c.db")
        _set_verified(monkeypatch, **{"custom/model-a": (0.003, 0.003)})
        _set_caps(monkeypatch, per_request="10", daily="0.06", monthly="10", db_path=db)
        r1 = reserve("custom/model-a", 20000)
        mark_attempting(r1.id)
        with pytest.raises(BudgetDeniedError) as exc_info:
            reserve("custom/model-a", 1000)
        assert exc_info.value.reason == "daily_cap_exceeded"


# ---------------------------------------------------------------------------
# 6) Fallo de almacenamiento -- sin cambios de comportamiento
# ---------------------------------------------------------------------------

class TestStorageFailureNeverLosesSpend:
    def test_reserve_falla_si_sqlite_no_disponible(self, monkeypatch, tmp_path):
        _set_verified(monkeypatch, **{"anthropic/claude-sonnet-5": (0.003, 0.003)})
        _set_caps(monkeypatch, per_request="10", daily="10", monthly="10", db_path=str(tmp_path / "c.db"))

        def _boom(path):
            raise OSError("disco no disponible (simulado)")

        monkeypatch.setattr(cost_guard, "_db", _boom)
        with pytest.raises(BudgetDeniedError) as exc_info:
            reserve("anthropic/claude-sonnet-5", 1000)
        assert exc_info.value.reason == "storage_unavailable_fail_closed"

    def test_settle_no_lanza_si_storage_falla(self, tmp_path):
        settle(999999, 0.001, db_path=str(tmp_path / "no-such-dir" / "x.db"))

    def test_settle_fallido_no_borra_el_gasto_ya_reservado(self, monkeypatch, tmp_path):
        db = str(tmp_path / "c.db")
        _set_verified(monkeypatch, **{"custom/model-a": (0.003, 0.003)})
        _set_caps(monkeypatch, per_request="10", daily="0.06", monthly="10", db_path=db)
        r1 = reserve("custom/model-a", 20000)

        original_db = cost_guard._db

        def _boom(path):
            raise OSError("disco no disponible durante el settle (simulado)")

        cost_guard._db = _boom
        try:
            settle(r1.id, 0.001)
        finally:
            cost_guard._db = original_db

        with pytest.raises(BudgetDeniedError) as exc_info:
            reserve("custom/model-a", 1000)
        assert exc_info.value.reason == "daily_cap_exceeded"


# ---------------------------------------------------------------------------
# 7) Concurrencia real -- sin cambios de comportamiento
# ---------------------------------------------------------------------------

class TestConcurrency:
    def test_dos_reservas_concurrentes_solo_una_cabe(self, monkeypatch, tmp_path):
        db = str(tmp_path / "concurrent.db")
        _set_verified(monkeypatch, **{"anthropic/claude-opus-5": (0.015, 0.015)})
        _set_caps(monkeypatch, per_request="10", daily="0.015", monthly="10", db_path=db)
        cost_guard._db(db).close()

        results = {}
        barrier = threading.Barrier(2)

        def worker(idx):
            barrier.wait()
            try:
                r = reserve("anthropic/claude-opus-5", 1000, operation_id=f"op-conc-{idx}")
                results[idx] = ("ok", r.estimated_usd)
            except BudgetDeniedError as exc:
                results[idx] = ("denied", exc.reason)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        outcomes = [v[0] for v in results.values()]
        assert outcomes.count("ok") == 1, f"esperaba exactamente 1 aprobado, obtuve: {results}"
        assert outcomes.count("denied") == 1, f"esperaba exactamente 1 denegado, obtuve: {results}"
        denied_reason = next(v[1] for v in results.values() if v[0] == "denied")
        assert denied_reason == "daily_cap_exceeded"


# ---------------------------------------------------------------------------
# 8) Cap diario / mensual -- sin cambios de comportamiento
# ---------------------------------------------------------------------------

class TestDailyCap:
    def test_segunda_llamada_supera_cap_diario(self, monkeypatch, tmp_path):
        db = str(tmp_path / "c.db")
        _set_verified(monkeypatch, **{
            "meta-llama/llama-4-maverick": (0.0002, 0.0002),
            "anthropic/claude-opus-5": (0.015, 0.015),
        })
        _set_caps(monkeypatch, per_request="10", daily="0.02", monthly="10", db_path=db)
        r1 = reserve("meta-llama/llama-4-maverick", 2000)
        settle(r1.id, r1.estimated_usd)
        with pytest.raises(BudgetDeniedError) as exc_info:
            reserve("anthropic/claude-opus-5", 2000)
        assert exc_info.value.reason == "daily_cap_exceeded"


class TestMonthlyCap:
    def test_dentro_del_dia_pero_supera_el_mes(self, monkeypatch, tmp_path):
        db = str(tmp_path / "c.db")
        _set_verified(monkeypatch, **{
            "meta-llama/llama-4-maverick": (0.0002, 0.0002),
            "anthropic/claude-opus-5": (0.015, 0.015),
        })
        _set_caps(monkeypatch, per_request="10", daily="10", monthly="0.02", db_path=db)
        r1 = reserve("meta-llama/llama-4-maverick", 2000)
        settle(r1.id, r1.estimated_usd)
        with pytest.raises(BudgetDeniedError) as exc_info:
            reserve("anthropic/claude-opus-5", 2000)
        assert exc_info.value.reason == "monthly_cap_exceeded"


# ---------------------------------------------------------------------------
# 9) Fronteras UTC -- sin cambios de comportamiento
# ---------------------------------------------------------------------------

class TestUtcBoundaries:
    def test_dos_instantes_a_2s_cruzando_medianoche_utc_son_dias_distintos(self, monkeypatch, tmp_path):
        db = str(tmp_path / "c.db")
        _set_verified(monkeypatch, **{"custom/model-a": (0.003, 0.003)})
        _set_caps(monkeypatch, per_request="10", daily="0.06", monthly="10", db_path=db)

        before_midnight = datetime(2026, 1, 31, 23, 59, 59, tzinfo=timezone.utc)
        after_midnight = datetime(2026, 2, 1, 0, 0, 1, tzinfo=timezone.utc)

        monkeypatch.setattr(cost_guard, "datetime", _FixedClock(before_midnight))
        r1 = reserve("custom/model-a", 20000, operation_id="op-day1")
        settle(r1.id, r1.estimated_usd)

        monkeypatch.setattr(cost_guard, "datetime", _FixedClock(after_midnight))
        r2 = reserve("custom/model-a", 20000, operation_id="op-day2")
        assert r2.estimated_usd == 0.06

    def test_mismo_dia_utc_sigue_acumulando(self, monkeypatch, tmp_path):
        db = str(tmp_path / "c.db")
        _set_verified(monkeypatch, **{"custom/model-a": (0.003, 0.003)})
        _set_caps(monkeypatch, per_request="10", daily="0.06", monthly="10", db_path=db)
        t1 = datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 3, 15, 10, 0, 5, tzinfo=timezone.utc)

        monkeypatch.setattr(cost_guard, "datetime", _FixedClock(t1))
        r1 = reserve("custom/model-a", 20000, operation_id="op-same-day-1")
        settle(r1.id, r1.estimated_usd)

        monkeypatch.setattr(cost_guard, "datetime", _FixedClock(t2))
        with pytest.raises(BudgetDeniedError) as exc_info:
            reserve("custom/model-a", 20000, operation_id="op-same-day-2")
        assert exc_info.value.reason == "daily_cap_exceeded"


# ---------------------------------------------------------------------------
# 10) ENLIL_ENABLED sigue siendo el gate superior -- sin cambios
# ---------------------------------------------------------------------------

class TestEnlilEnabledFalseGatesFirst:
    @pytest.mark.asyncio
    async def test_enlil_disabled_nunca_llega_al_guardarrail(self, monkeypatch):
        monkeypatch.delenv("ENLIL_ENABLED", raising=False)

        def _fail_if_called(*a, **kw):
            raise AssertionError("reserve() no deberia llamarse con ENLIL_ENABLED off")

        monkeypatch.setattr("enlil.council._reserve_budget", _fail_if_called)
        council = _make_council()
        with pytest.raises(EnlilDisabledError):
            await council.consult_god("MOCK_GOD", "query de prueba")


# ---------------------------------------------------------------------------
# 11) Integracion real con Council -- sin cambios de comportamiento
# ---------------------------------------------------------------------------

class TestCouncilIntegration:
    @pytest.mark.asyncio
    async def test_retry_se_deniega_si_agotaria_el_cap_de_la_operacion(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ENLIL_ENABLED", "true")
        db = str(tmp_path / "retry.db")
        _set_verified(monkeypatch, **{"test-model": (0.003, 0.003)})
        _set_caps(monkeypatch, per_request="0.0035", daily="10", monthly="10", db_path=db)

        council = _make_council()
        calls = []

        async def fake_create(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return _resp("", finish_reason="length", total_tokens=200)
            return _resp("respuesta completa", finish_reason="stop", total_tokens=50)

        council._client = MagicMock()
        council._client.chat.completions.create = AsyncMock(side_effect=fake_create)

        deadline = time.monotonic() + 300.0
        resp = await council._consult_god_with_retry(
            "MOCK_GOD", "query", "", max_tokens=100, deadline=deadline,
        )

        assert len(calls) == 1
        assert resp.attempts[-1].exception_type == "BudgetDeniedError"

    @pytest.mark.asyncio
    async def test_retry_dentro_del_cap_de_operacion_si_llega_al_proveedor(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ENLIL_ENABLED", "true")
        db = str(tmp_path / "retry2.db")
        _set_verified(monkeypatch, **{"test-model": (0.003, 0.003)})
        _set_caps(monkeypatch, per_request="10", daily="10", monthly="10", db_path=db)

        council = _make_council()
        calls = []

        async def fake_create(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return _resp("", finish_reason="length", total_tokens=200)
            return _resp("respuesta completa", finish_reason="stop", total_tokens=50)

        council._client = MagicMock()
        council._client.chat.completions.create = AsyncMock(side_effect=fake_create)

        deadline = time.monotonic() + 300.0
        resp = await council._consult_god_with_retry(
            "MOCK_GOD", "query", "", max_tokens=100, deadline=deadline,
        )

        assert len(calls) == 2
        assert resp.retry_count == 1
        assert resp.content == "respuesta completa"

    @pytest.mark.asyncio
    async def test_timeout_tras_tocar_la_red_conserva_el_worst_case(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ENLIL_ENABLED", "true")
        db = str(tmp_path / "timeout.db")
        _set_verified(monkeypatch, **{"test-model": (0.003, 0.003)})
        _set_caps(monkeypatch, per_request="10", daily="10", monthly="10", db_path=db)

        council_probe = _make_council()

        async def fake_create_timeout(**kwargs):
            raise asyncio.TimeoutError()

        council_probe._client = MagicMock()
        council_probe._client.chat.completions.create = AsyncMock(side_effect=fake_create_timeout)

        with pytest.raises(asyncio.TimeoutError):
            await council_probe.consult_god("MOCK_GOD", "query", max_tokens=100)

        conn = cost_guard._db(db)
        row = conn.execute(
            "SELECT status, reserved_usd, actual_usd FROM cost_ledger ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        assert row["status"] == "uncertain"
        assert row["actual_usd"] == row["reserved_usd"]

    @pytest.mark.asyncio
    async def test_circuit_abierto_sin_fallback_libera_presupuesto(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ENLIL_ENABLED", "true")
        db = str(tmp_path / "circuit.db")
        _set_verified(monkeypatch, **{"test-model": (0.003, 0.003)})
        _set_caps(monkeypatch, per_request="10", daily="10", monthly="10", db_path=db)

        council = _make_council()
        council._anthropic_client = None
        monkeypatch.setattr(council._circuit, "is_open", lambda: True)

        result = await council.consult_god("MOCK_GOD", "query", max_tokens=100)
        assert result.state == "circuit_open"

        conn = cost_guard._db(db)
        row = conn.execute(
            "SELECT status, actual_usd FROM cost_ledger ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        assert row["status"] == "released"
        assert row["actual_usd"] == 0.0


# ---------------------------------------------------------------------------
# 12) Fallback OpenRouter -> Anthropic reserva con el modelo/precio de B
#     -- sin cambios de comportamiento
# ---------------------------------------------------------------------------

class TestFallbackReservesCorrectModel:
    @pytest.mark.asyncio
    async def test_circuito_ya_abierto_reserva_con_modelo_de_fallback(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ENLIL_ENABLED", "true")
        db = str(tmp_path / "fallback1.db")
        _set_verified(monkeypatch, **{
            "custom/model-a": (0.001, 0.001),
            "claude-sonnet-5": (0.05, 0.05),
        })
        _set_caps(monkeypatch, per_request="10", daily="10", monthly="10", db_path=db)

        council = _make_council(model="custom/model-a")
        openrouter_calls, anthropic_calls = [], []

        async def fake_openrouter(**kwargs):
            openrouter_calls.append(kwargs)
            raise RuntimeError("A nunca deberia llamarse con el circuito abierto")

        async def fake_anthropic(**kwargs):
            anthropic_calls.append(kwargs)
            return _resp("respuesta B", finish_reason="stop", total_tokens=50)

        council._client = MagicMock()
        council._client.chat.completions.create = AsyncMock(side_effect=fake_openrouter)
        council._anthropic_client = MagicMock()
        council._anthropic_client.chat.completions.create = AsyncMock(side_effect=fake_anthropic)
        monkeypatch.setattr(council._circuit, "is_open", lambda: True)

        await council.consult_god("MOCK_GOD", "query", max_tokens=100)

        assert len(openrouter_calls) == 0
        assert len(anthropic_calls) == 1

        conn = cost_guard._db(db)
        row = conn.execute("SELECT model FROM cost_ledger ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        assert row["model"] == "claude-sonnet-5"

    @pytest.mark.asyncio
    async def test_A_cabe_pero_A_mas_B_no_B_bloqueado_antes_de_invocar(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ENLIL_ENABLED", "true")
        db = str(tmp_path / "fallback2.db")
        _set_verified(monkeypatch, **{
            "test-model": (0.0005, 0.0005),
            "claude-sonnet-5": (0.05, 0.05),
        })
        _set_caps(monkeypatch, per_request="0.003", daily="10", monthly="10", db_path=db)

        council = _make_council(model="test-model")
        openrouter_calls, anthropic_calls = [], []

        async def fake_openrouter(**kwargs):
            openrouter_calls.append(kwargs)
            return _resp("", finish_reason="length", total_tokens=50)

        async def fake_anthropic(**kwargs):
            anthropic_calls.append(kwargs)
            return _resp("no deberia llegar aqui", finish_reason="stop", total_tokens=50)

        council._client = MagicMock()
        council._client.chat.completions.create = AsyncMock(side_effect=fake_openrouter)
        council._anthropic_client = MagicMock()
        council._anthropic_client.chat.completions.create = AsyncMock(side_effect=fake_anthropic)

        call_n = {"n": 0}

        def fake_is_open():
            call_n["n"] += 1
            return call_n["n"] > 1

        monkeypatch.setattr(council._circuit, "is_open", fake_is_open)

        deadline = time.monotonic() + 300.0
        resp = await council._consult_god_with_retry(
            "MOCK_GOD", "query", "", max_tokens=100, deadline=deadline,
        )

        assert len(openrouter_calls) == 1
        assert len(anthropic_calls) == 0
        assert resp.attempts[-1].exception_type == "BudgetDeniedError"

        conn = cost_guard._db(db)
        rows = conn.execute("SELECT model, status FROM cost_ledger ORDER BY id").fetchall()
        conn.close()
        models_seen = [r["model"] for r in rows]
        assert "test-model" in models_seen
        assert "claude-sonnet-5" not in models_seen
