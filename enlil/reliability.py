"""
Observabilidad y fiabilidad de intentos — TEST 01B.

Fuente única de verdad para: clasificar un intento de llamada a modelo
(voz o síntesis), seleccionar cuál de dos intentos queda como operativo,
y agregar el estado de "usage" (tokens conocidos/parciales/desconocidos)
de un decreto completo.

Diseño: ENLIL_TEST01B_AUDITORIA_DISENO_V3.md / V4 / V5 / V6.
Nada de esto cambia qué se le pregunta a los modelos ni sube max_tokens
globalmente — solo observa y clasifica lo que ya ocurre.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ── Estados de un intento (voz o síntesis) — únicos, cerrados ──────────────

VOICE_STATES = frozenset({
    "complete", "truncated", "empty",
    "timeout", "error", "filtered", "circuit_open", "unknown",
})

# Clases de §2 (V5): A domina B domina C. Dentro de la misma clase, gana
# el primer intento — nunca se compara "truncated" contra "unknown".
_CLASS_RANK = {
    "complete": 2,
    "truncated": 1, "unknown": 1,
    "empty": 0, "filtered": 0, "error": 0, "timeout": 0, "circuit_open": 0,
}

USABLE_STATES = frozenset({"complete", "truncated", "unknown"})  # clases A+B


@dataclass(frozen=True)
class AttemptSignal:
    """Entrada mínima y suficiente para clasificar un intento. Efímera —
    `exception` vive solo en memoria durante la clasificación, nunca se
    persiste (ver AttemptResult.exception_type/error_code)."""
    circuit_open: bool = False
    timed_out: bool = False
    exception: Optional[BaseException] = None
    finish_reason: Optional[str] = None
    content: str = ""
    has_refusal: bool = False
    has_unexpected_tool_calls: bool = False


def classify_attempt(signal: AttemptSignal) -> str:
    """Única función de clasificación de estado — usada por voces y por
    síntesis, en streaming y en no-streaming. Precedencia estricta
    (ENLIL_TEST01B_AUDITORIA_DISENO_V3.md §2):

    1. circuit_open
    2. timeout
    3. excepción/error técnico
    4. tool_calls/function_call inesperados
    5. refusal / content_filter
    6. contenido vacío
    7. finish_reason == length
    8. finish_reason == stop
    9. cualquier otro valor/ausencia -> unknown

    Invariantes garantizados por el orden (nunca por revisión manual):
    - una respuesta filtrada nunca puede salir "empty" (5 antes que 6);
    - una respuesta con tool_calls nunca puede salir "complete" (4 antes que 8);
    - un finish_reason desconocido/ausente nunca puede salir "complete"
      (complete exige explícitamente "stop").
    """
    if signal.circuit_open:
        return "circuit_open"
    if signal.timed_out:
        return "timeout"
    if signal.exception is not None:
        return "error"
    if signal.has_unexpected_tool_calls:
        return "error"
    if signal.has_refusal or signal.finish_reason == "content_filter":
        return "filtered"
    if not signal.content or not signal.content.strip():
        return "empty"
    if signal.finish_reason == "length":
        return "truncated"
    if signal.finish_reason == "stop":
        return "complete"
    return "unknown"


def select_operative_attempt(attempt1, attempt2=None):
    """Selección por clases (V5 §2 / V6 confirma sin cambios). Funciona
    igual para AttemptResult (voces) y SynthesisAttempt (síntesis) — solo
    exige que el objeto tenga un atributo `.state`.

    No reescribe el estado real de ningún intento: solo decide cuál de
    los dos objetos ya clasificados alimenta el contenido operativo.
    Ambos intentos permanecen siempre en la telemetría del llamador
    (GodResponse.attempts / Decree.synthesis_attempts).
    """
    if attempt2 is None:
        return attempt1
    c1, c2 = _CLASS_RANK[attempt1.state], _CLASS_RANK[attempt2.state]
    if c2 > c1:
        return attempt2
    return attempt1   # empate de clase, o attempt1 ya en clase superior -> gana el primero


@dataclass(frozen=True)
class AttemptResult:
    """Registro completo de un intento de voz — señal + clasificación + telemetría.
    NUNCA contiene un objeto BaseException ni un traceback (ver §6, V4)."""
    attempt_number: int
    state: str
    content: str
    requested_model: str
    returned_model: Optional[str] = None
    finish_reason: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    usage_state: str = "unknown"          # "known" | "partial" | "unknown"
    reasoning_present: bool = False
    max_tokens_budget: int = 0
    latency_ms: float = 0.0
    generation_id: Optional[str] = None
    error_code: Optional[str] = None      # p.ej. "402" — nunca la excepción cruda
    exception_type: Optional[str] = None  # nombre de clase, nunca el objeto


@dataclass(frozen=True)
class SynthesisAttempt:
    """Gemelo de AttemptResult para la síntesis — con `content` explícito
    (V5 §3) para que select_operative_attempt() pueda elegir cuál síntesis
    queda como operativa."""
    attempt_number: int
    content: str
    state: str
    requested_model: str
    returned_model: Optional[str] = None
    finish_reason: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    usage_state: str = "unknown"
    max_tokens_budget: int = 0
    latency_ms: float = 0.0
    generation_id: Optional[str] = None
    error_code: Optional[str] = None
    exception_type: Optional[str] = None


def classify_usage(resp_usage) -> tuple[str, dict]:
    """Tri-estado de usage por intento (V3 §11, V6 sin cambios de fondo).
    reasoning_tokens es SIEMPRE informativo — nunca se suma aparte de
    completion_tokens/total_tokens (ya viene incluido dentro)."""
    if resp_usage is None:
        return "unknown", {
            "prompt_tokens": None, "completion_tokens": None,
            "reasoning_tokens": None, "total_tokens": None,
        }

    def _valid(x):
        return isinstance(x, int) and x >= 0

    total = getattr(resp_usage, "total_tokens", None)
    prompt = getattr(resp_usage, "prompt_tokens", None)
    completion = getattr(resp_usage, "completion_tokens", None)
    reasoning = None
    details = getattr(resp_usage, "completion_tokens_details", None)
    if details is not None:
        reasoning = getattr(details, "reasoning_tokens", None)

    if _valid(total):
        state = "known"
    elif _valid(prompt) and _valid(completion):
        total = prompt + completion   # reconstruido; reasoning_tokens NO se suma aparte
        state = "known"
    elif _valid(prompt) or _valid(completion):
        state = "partial"
    else:
        state = "unknown"

    return state, {
        "prompt_tokens": prompt, "completion_tokens": completion,
        "reasoning_tokens": reasoning, "total_tokens": total,
    }


def aggregate_accounting_state(component_states: list[str]) -> str:
    """V5 §4 / V6 §3 — sin cambios de fondo. known solo si TODOS los
    componentes son known; unknown solo si TODOS son unknown; cualquier
    otra combinación (incluida la mezcla known+unknown) -> partial."""
    if not component_states:
        return "unknown"
    if all(s == "known" for s in component_states):
        return "known"
    if all(s == "unknown" for s in component_states):
        return "unknown"
    return "partial"


def compute_known_subtotal(components) -> Optional[int]:
    """V6 §2/§3 — guardia explícita contra sum([]) == 0. Sin ningún
    componente con usage_state=='known', el resultado es None, nunca 0."""
    known_totals = [
        c.total_tokens for c in components
        if getattr(c, "usage_state", None) == "known" and c.total_tokens is not None
    ]
    if not known_totals:
        return None
    return sum(known_totals)


def compute_observed_total(accounting_state: str, known_subtotal: Optional[int]) -> Optional[int]:
    """observed_total_tokens solo es un entero cuando el agregado es
    'known' de verdad — en cualquier otro caso (incluido 'partial' con
    subtotal disponible) es None, para no presentar un subtotal como si
    fuera el total completo (V4 §11 / V6 §4)."""
    return known_subtotal if accounting_state == "known" else None


@dataclass(frozen=True)
class StreamingBehaviorProfile:
    """Qué postprocesos/enriquecimientos activar en el streaming canónico
    (ENLIL_TEST01B_AUDITORIA_DISENO_V6.md §5). Explícito, no un booleano
    genérico — cada efecto lateral verificado por separado contra el
    código real de api.py y Orchestrator.query_stream()."""
    use_corpus: bool
    use_rag: bool
    write_sqlite_memory: bool
    compute_predicted_scores: bool
    thread_parent_decree_id: bool
    do_meta_observe: bool
    do_reputation_decay: bool
    do_rl_learning: bool
    record_decree_telemetry: bool
    emit_init_event: bool
    include_model_in_god_event: bool


# == PUBLIC_API_TODAY, verificado por grep línea por línea (V6 §5) --
# el único perfil activo durante TEST 01B para /query/stream.
COMPATIBILITY_PROFILE = StreamingBehaviorProfile(
    use_corpus=False, use_rag=False,
    write_sqlite_memory=False, compute_predicted_scores=False,
    thread_parent_decree_id=False,
    do_meta_observe=False, do_reputation_decay=False, do_rl_learning=False,
    record_decree_telemetry=False,
    emit_init_event=False, include_model_in_god_event=False,
)

# == ORCHESTRATOR_STREAM_TODAY -- documentado como objetivo de una
# unificación funcional futura. NO se activa en TEST 01B.
FULL_PROFILE = StreamingBehaviorProfile(
    use_corpus=True, use_rag=True,
    write_sqlite_memory=True, compute_predicted_scores=True,
    thread_parent_decree_id=True,
    do_meta_observe=True, do_reputation_decay=True, do_rl_learning=True,
    record_decree_telemetry=True,
    emit_init_event=True, include_model_in_god_event=True,
)


def select_operative_synthesis(synthesis_attempts: list) -> SynthesisAttempt:
    """Envoltorio robusto sobre select_operative_attempt() para
    synthesis_attempts -- nunca lanza IndexError si la lista viene vacía
    (p.ej. un test que mockea Council.synthesize() con un valor legacy).
    Council.synthesize() real SIEMPRE devuelve >=1 intento."""
    if not synthesis_attempts:
        return SynthesisAttempt(
            attempt_number=0, content="", state="unknown",
            requested_model="", max_tokens_budget=0, latency_ms=0.0, usage_state="unknown",
        )
    if len(synthesis_attempts) == 1:
        return synthesis_attempts[0]
    return select_operative_attempt(synthesis_attempts[0], synthesis_attempts[1])


def compute_decree_status(voice_states: list[str], synthesis_state: str) -> str:
    """Función única compartida por /query y /query/stream (V3 §8).

    complete: todas las voces "complete" y síntesis "complete".
    failed:   ninguna voz "complete" O síntesis no utilizable.
    partial:  cualquier otra combinación con una síntesis utilizable.
    """
    synthesis_usable = synthesis_state in USABLE_STATES
    if not synthesis_usable:
        return "failed"
    if not voice_states or not any(s == "complete" for s in voice_states):
        # ninguna voz llegó a "complete" -> failed, salvo que al menos
        # haya contenido utilizable en alguna (entonces es partial, no failed)
        if any(s in USABLE_STATES for s in voice_states):
            return "partial"
        return "failed"
    if all(s == "complete" for s in voice_states) and synthesis_state == "complete":
        return "complete"
    return "partial"
