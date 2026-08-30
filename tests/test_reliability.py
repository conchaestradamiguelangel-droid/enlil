"""TEST 01B — classify_attempt() (fuente única), select_operative_attempt()
(clases A/B/C), accounting known/partial/unknown, compute_decree_status().
ENLIL_TEST01B_AUDITORIA_DISENO_V3/V5/V6.md."""
import pytest

from enlil.reliability import (
    AttemptSignal, AttemptResult, SynthesisAttempt,
    classify_attempt, select_operative_attempt, select_operative_synthesis,
    aggregate_accounting_state, compute_known_subtotal, compute_observed_total,
    compute_decree_status,
)


def _attempt(state, attempt_number=1, total_tokens=None, usage_state="unknown"):
    return AttemptResult(
        attempt_number=attempt_number, state=state, content="x" if state != "empty" else "",
        requested_model="m", max_tokens_budget=100, latency_ms=1.0,
        total_tokens=total_tokens, usage_state=usage_state,
    )


# ── classify_attempt(): precedencia exacta, combinatoria ────────────────

class TestClassifyAttemptPrecedencia:
    def test_stop_con_contenido_es_complete(self):
        s = AttemptSignal(finish_reason="stop", content="hola")
        assert classify_attempt(s) == "complete"

    def test_length_es_truncated(self):
        s = AttemptSignal(finish_reason="length", content="hola")
        assert classify_attempt(s) == "truncated"

    def test_finish_reason_none_con_contenido_es_unknown(self):
        s = AttemptSignal(finish_reason=None, content="hola")
        assert classify_attempt(s) == "unknown"

    def test_finish_reason_no_reconocido_es_unknown(self):
        s = AttemptSignal(finish_reason="algo_raro_no_documentado", content="hola")
        assert classify_attempt(s) == "unknown"

    def test_content_filter_es_filtered(self):
        s = AttemptSignal(finish_reason="content_filter", content="hola")
        assert classify_attempt(s) == "filtered"

    def test_refusal_es_filtered(self):
        s = AttemptSignal(finish_reason="stop", content="hola", has_refusal=True)
        assert classify_attempt(s) == "filtered"

    def test_vacio_con_refusal_es_filtered_no_empty(self):
        """Invariante 1: una respuesta filtrada nunca sale 'empty'."""
        s = AttemptSignal(finish_reason="stop", content="", has_refusal=True)
        assert classify_attempt(s) == "filtered"

    def test_vacio_con_tool_calls_es_error_no_empty(self):
        """Invariante 2: tool_calls inesperados nunca salen 'complete',
        y aquí tampoco 'empty' -- error domina."""
        s = AttemptSignal(finish_reason="tool_calls", content="", has_unexpected_tool_calls=True)
        assert classify_attempt(s) == "error"

    def test_contenido_con_stop_y_tool_calls_es_error_nunca_complete(self):
        """Invariante 2, caso límite con contenido presente."""
        s = AttemptSignal(finish_reason="stop", content="hola", has_unexpected_tool_calls=True)
        assert classify_attempt(s) == "error"

    def test_contenido_con_content_filter_es_filtered_aunque_haya_texto(self):
        s = AttemptSignal(finish_reason="content_filter", content="texto parcial generado")
        assert classify_attempt(s) == "filtered"

    def test_finish_reason_desconocido_con_contenido_nunca_complete(self):
        """Invariante 3."""
        s = AttemptSignal(finish_reason="weird_value", content="hola")
        result = classify_attempt(s)
        assert result != "complete"
        assert result == "unknown"

    def test_circuit_open_domina_sobre_cualquier_otra_señal(self):
        s = AttemptSignal(circuit_open=True, finish_reason="stop", content="hola", has_refusal=True)
        assert classify_attempt(s) == "circuit_open"

    def test_timeout_domina_sobre_contenido_presente(self):
        s = AttemptSignal(timed_out=True, finish_reason="stop", content="hola")
        assert classify_attempt(s) == "timeout"

    def test_excepcion_es_error(self):
        s = AttemptSignal(exception=RuntimeError("boom"))
        assert classify_attempt(s) == "error"

    def test_contenido_vacio_sin_otra_señal_es_empty(self):
        s = AttemptSignal(finish_reason="stop", content="   ")
        assert classify_attempt(s) == "empty"


# ── select_operative_attempt(): clases A/B/C, casos obligatorios de V5 ──

class TestSeleccionPorClases:
    @pytest.mark.parametrize("s1,s2,expected_state", [
        ("empty", "truncated", "truncated"),
        ("empty", "unknown", "unknown"),
        ("truncated", "empty", "truncated"),
        ("unknown", "error", "unknown"),
        ("truncated", "unknown", "truncated"),
        ("unknown", "truncated", "unknown"),
        ("empty", "complete", "complete"),
        ("filtered", "complete", "complete"),
        ("complete", "empty", "complete"),
        ("complete", "truncated", "complete"),
    ])
    def test_casos_obligatorios_v5(self, s1, s2, expected_state):
        a1, a2 = _attempt(s1, 1), _attempt(s2, 2)
        chosen = select_operative_attempt(a1, a2)
        assert chosen.state == expected_state

    def test_sin_segundo_intento_devuelve_el_primero(self):
        a1 = _attempt("truncated")
        assert select_operative_attempt(a1, None) is a1

    def test_no_reescribe_el_estado_de_ningun_intento(self):
        a1, a2 = _attempt("truncated"), _attempt("empty")
        select_operative_attempt(a1, a2)
        assert a1.state == "truncated"
        assert a2.state == "empty"

    def test_select_operative_synthesis_lista_vacia_no_revienta(self):
        result = select_operative_synthesis([])
        assert result.state == "unknown"

    def test_select_operative_synthesis_un_solo_intento(self):
        s1 = SynthesisAttempt(attempt_number=1, content="x", state="complete", requested_model="m")
        assert select_operative_synthesis([s1]) is s1


# ── Accounting: known/partial/unknown, subtotal nunca inventa 0 ─────────

class TestAccounting:
    def test_todos_known_es_known(self):
        assert aggregate_accounting_state(["known", "known"]) == "known"

    def test_todos_unknown_es_unknown(self):
        assert aggregate_accounting_state(["unknown", "unknown"]) == "unknown"

    def test_mezcla_known_unknown_es_partial(self):
        assert aggregate_accounting_state(["known", "unknown"]) == "partial"

    def test_algun_partial_es_partial(self):
        assert aggregate_accounting_state(["known", "partial"]) == "partial"

    def test_lista_vacia_es_unknown(self):
        assert aggregate_accounting_state([]) == "unknown"

    def test_subtotal_none_si_no_hay_ningun_known(self):
        comps = [_attempt("empty", usage_state="unknown"), _attempt("empty", usage_state="unknown")]
        assert compute_known_subtotal(comps) is None

    def test_subtotal_none_no_cero_lista_vacia(self):
        """Guardia explícita contra sum([]) == 0 (V6 §2)."""
        assert compute_known_subtotal([]) is None

    def test_subtotal_none_con_todos_partial_sin_known(self):
        comps = [
            _attempt("truncated", total_tokens=None, usage_state="partial"),
            _attempt("truncated", total_tokens=None, usage_state="partial"),
        ]
        assert compute_known_subtotal(comps) is None

    def test_subtotal_suma_solo_los_known(self):
        comps = [
            _attempt("complete", total_tokens=100, usage_state="known"),
            _attempt("truncated", total_tokens=None, usage_state="partial"),
            _attempt("empty", total_tokens=None, usage_state="unknown"),
        ]
        assert compute_known_subtotal(comps) == 100

    def test_subtotal_suma_dos_known(self):
        comps = [
            _attempt("complete", total_tokens=100, usage_state="known"),
            _attempt("complete", total_tokens=50, usage_state="known"),
        ]
        assert compute_known_subtotal(comps) == 150

    def test_observed_total_solo_cuando_accounting_es_known(self):
        assert compute_observed_total("known", 150) == 150
        assert compute_observed_total("partial", 100) is None
        assert compute_observed_total("unknown", None) is None

    def test_tabla_completa_v6_fila_por_fila(self):
        # unknown + unknown -> unknown, subtotal None, observed None
        comps = [_attempt("empty", usage_state="unknown"), _attempt("empty", usage_state="unknown")]
        acc = aggregate_accounting_state([c.usage_state for c in comps])
        sub = compute_known_subtotal(comps)
        assert (acc, sub, compute_observed_total(acc, sub)) == ("unknown", None, None)

        # known(100) + unknown -> partial, subtotal=100, observed None
        comps = [_attempt("complete", total_tokens=100, usage_state="known"),
                 _attempt("empty", usage_state="unknown")]
        acc = aggregate_accounting_state([c.usage_state for c in comps])
        sub = compute_known_subtotal(comps)
        assert (acc, sub, compute_observed_total(acc, sub)) == ("partial", 100, None)

        # known(100) + known(50) -> known, subtotal=150, observed=150
        comps = [_attempt("complete", total_tokens=100, usage_state="known"),
                 _attempt("complete", total_tokens=50, usage_state="known")]
        acc = aggregate_accounting_state([c.usage_state for c in comps])
        sub = compute_known_subtotal(comps)
        assert (acc, sub, compute_observed_total(acc, sub)) == ("known", 150, 150)


# ── compute_decree_status() ──────────────────────────────────────────────

class TestComputeDecreeStatus:
    def test_todo_complete_es_complete(self):
        assert compute_decree_status(["complete", "complete"], "complete") == "complete"

    def test_una_voz_degradada_es_partial(self):
        assert compute_decree_status(["complete", "truncated"], "complete") == "partial"

    def test_sintesis_no_utilizable_es_failed(self):
        assert compute_decree_status(["complete", "complete"], "empty") == "failed"

    def test_ninguna_voz_complete_pero_sintesis_ok_es_partial_si_hay_utilizable(self):
        assert compute_decree_status(["truncated", "unknown"], "complete") == "partial"

    def test_todas_las_voces_fallidas_es_failed(self):
        assert compute_decree_status(["error", "timeout"], "complete") == "failed"
