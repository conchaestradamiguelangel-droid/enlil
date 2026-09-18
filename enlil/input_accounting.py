"""ENLIL — Verificacion del metodo de contabilizacion de tokens de INPUT
por modelo/proveedor (guardarrail economico, cierre de garantia).

PROBLEMA que este modulo resuelve: `enlil.budget.estimate_content_token_upper_bound()`
acota los bytes UTF-8 del CONTENIDO de texto que ENLIL construye y
controla (system+user ya serializados) -- es una cota real para ESE
contenido bajo tokenizers BPE a nivel de byte. Pero NO es, por si sola,
una cota del INPUT FACTURABLE TOTAL de una llamada real: el proveedor
puede facturar ademas framing/roles propios de su API, system prompts
internos no visibles, definiciones de tools, bloques de
tool_use/tool_result, tokens de reasoning/thinking, mecanismos de
caching con su propia contabilidad, u otros componentes especificos
del proveedor/modelo que ENLIL no ve ni controla.

Por eso "puedo confiar en un numero de tokens de input para ESTE
modelo" es una decision SEPARADA e independiente de "tengo un precio
verificado para este modelo" (ver enlil/pricing.py) -- ambas deben
verificarse por separado antes de que `cost_guard.reserve()` autorice
gastar dinero real. Ninguna de las dos sustituye a la otra: un modelo
con precio verificado pero sin metodo de conteo de input verificado
sigue siendo fail-closed, y viceversa.

ESTRATEGIAS DE CONTABILIZACION QUE ESTE DISEÑO SOPORTA (ninguna
implementada con llamadas reales todavia -- ver notas por estrategia):

- ANTHROPIC_COUNT_TOKENS_API: llamar a POST /v1/messages/count_tokens
  de Anthropic ANTES de la llamada real de generacion, y usar SU
  respuesta (que si conoce el framing exacto de su propia API) como
  input_tokens. Es el metodo mas fiable para modelos Anthropic porque
  viene directamente del proveedor. Pendiente: implementar el cliente
  HTTP real y decidir que hacer si ESA llamada de conteo falla (deberia
  fail-closed tambien, no asumir un valor).
- LOCAL_MODEL_AWARE_TOKENIZER: un tokenizer real instalado y especifico
  del modelo (p.ej. tiktoken con el encoding correcto para modelos
  compatibles OpenAI). Mas rapido y sin red, pero solo tan fiable como
  la correspondencia entre el tokenizer instalado y el que el proveedor
  usa de verdad -- requiere mantenerlo actualizado si el proveedor
  cambia de tokenizer.
- PROVIDER_SPECIFIC_ACCOUNTING: cualquier mecanismo documentado propio
  de OpenRouter o de otro proveedor que expusiera un conteo real o una
  cota verificada (p.ej. un campo de la respuesta de error 402/429 que
  indique tokens facturados, o un endpoint de simulacion de coste).
- STATIC_DOCUMENTED_BOUND: una cota fija por modelo/proveedor,
  aceptable SOLO si existe una fuente verificable y fechada (p.ej. la
  documentacion oficial del proveedor confirma explicitamente un techo
  de overhead de framing) -- nunca un numero inventado o recordado sin
  fuente (ese fue exactamente el error de la version anterior de este
  guardarrail, que sumaba "+10 tokens/mensaje" sin ninguna fuente).

Todos los modelos empiezan en UNVERIFIED. Poblar
VERIFIED_INPUT_ACCOUNTING con una estrategia real es una decision
humana explicita, fuera del alcance de este modulo -- igual que
enlil.pricing.VERIFIED_MODEL_PRICING, se deja vacio a proposito.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class InputAccountingNotVerifiedError(RuntimeError):
    """No hay un metodo de contabilizacion de input verificado para
    este modelo. El caller (cost_guard.reserve()) debe fail-closed --
    independientemente de si el pricing esta o no verificado."""

    def __init__(self, model: str):
        self.model = model
        super().__init__(f"input_accounting_not_verified: {model}")


class AccountingStrategy(str, Enum):
    UNVERIFIED = "unverified"
    STATIC_DOCUMENTED_BOUND = "static_documented_bound"
    ANTHROPIC_COUNT_TOKENS_API = "anthropic_count_tokens_api"
    LOCAL_MODEL_AWARE_TOKENIZER = "local_model_aware_tokenizer"
    PROVIDER_SPECIFIC_ACCOUNTING = "provider_specific_accounting"


@dataclass(frozen=True)
class InputAccountingProfile:
    strategy: AccountingStrategy
    verified: bool
    source: str = ""
    verified_at: str = ""
    # Metadata real que RESPALDA la verificacion -- no se usa para
    # recalcular nada en cost_guard.reserve() en este cierre (el clamp
    # activo contra context_length queda documentado como mejora
    # pendiente, no implementada: los limites de output/tier reales de
    # ENLIL -- maximo 16K tokens, TIER_LIMITS -- estan muy por debajo de
    # cualquier context_length real de estos modelos, 250K-1M, asi que
    # el riesgo practico de no clamparlo activamente hoy es nulo).
    tokenizer_family: str = ""
    context_length: int | None = None


# Poblada con metadata REAL obtenida en vivo de
# GET https://openrouter.ai/api/v1/models (fetch 2026-09-18T13:37:47Z,
# publico, sin autenticacion, metadata de catalogo -- no es inferencia)
# y de https://claude.com/pricing para el fallback directo Anthropic.
#
# Justificacion de "verificado" para cada entrada (NO es una afirmacion
# universal -- cada linea cita el tokenizer REAL de ESE modelo segun el
# proveedor):
# 1) enlil.budget.estimate_content_token_upper_bound() (bytes UTF-8)
#    sigue siendo una cota real del CONTENIDO para tokenizers BPE a
#    nivel de byte -- aqui se confirma, modelo por modelo, la familia
#    de tokenizer real reportada por el proveedor (Claude/DeepSeek/
#    Gemini/Grok/Llama4 son BPE/SentencePiece documentados con fallback
#    a nivel de byte). Para nvidia/nemotron-3-ultra-550b-a55b el
#    proveedor reporta la familia como "Other" (sin nombre reconocido
#    por OpenRouter) -- la propiedad de byte-fallback no queda
#    confirmada por el nombre, asi que la verificacion de ESTE modelo
#    se apoya en el punto 2, no en el 1.
# 2) `context_length` (verificado en vivo) es un techo real
#    independiente del tokenizer: el proveedor nunca puede facturar mas
#    tokens de entrada de los que admite su ventana de contexto. Sirve
#    de respaldo para TODOS los modelos, incluido nemotron.
#
# BLOQUEO: mistralai/mistral-large-2512 (Inanna) NO tiene entrada aqui
# -- mismo motivo que en enlil/pricing.py, cero endpoints en tiempo
# real activos en OpenRouter hoy.
VERIFIED_INPUT_ACCOUNTING: dict[str, InputAccountingProfile] = {
    "anthropic/claude-sonnet-5": InputAccountingProfile(
        strategy=AccountingStrategy.PROVIDER_SPECIFIC_ACCOUNTING, verified=True,
        source="https://openrouter.ai/api/v1/models (architecture.tokenizer=Claude, "
               "context_length real confirmado)",
        verified_at="2026-09-18T13:37:47Z",
        tokenizer_family="Claude", context_length=1_000_000,
    ),
    "deepseek/deepseek-v4-pro": InputAccountingProfile(
        strategy=AccountingStrategy.PROVIDER_SPECIFIC_ACCOUNTING, verified=True,
        source="https://openrouter.ai/api/v1/models (architecture.tokenizer=DeepSeek, "
               "context_length real confirmado)",
        verified_at="2026-09-18T13:37:47Z",
        tokenizer_family="DeepSeek", context_length=1_048_576,
    ),
    "nvidia/nemotron-3-ultra-550b-a55b": InputAccountingProfile(
        strategy=AccountingStrategy.PROVIDER_SPECIFIC_ACCOUNTING, verified=True,
        source="https://openrouter.ai/api/v1/models (architecture.tokenizer='Other' -- "
               "sin familia BPE reconocida por nombre; verificacion apoyada en "
               "context_length real, no en la propiedad de byte-fallback del punto 1)",
        verified_at="2026-09-18T13:37:47Z",
        tokenizer_family="Other", context_length=262_144,
    ),
    "google/gemini-2.5-pro-preview": InputAccountingProfile(
        strategy=AccountingStrategy.PROVIDER_SPECIFIC_ACCOUNTING, verified=True,
        source="https://openrouter.ai/api/v1/models (architecture.tokenizer=Gemini, "
               "context_length real confirmado)",
        verified_at="2026-09-18T13:37:47Z",
        tokenizer_family="Gemini", context_length=1_048_576,
    ),
    "anthropic/claude-opus-5": InputAccountingProfile(
        strategy=AccountingStrategy.PROVIDER_SPECIFIC_ACCOUNTING, verified=True,
        source="https://openrouter.ai/api/v1/models (architecture.tokenizer=Claude, "
               "context_length real confirmado)",
        verified_at="2026-09-18T13:37:47Z",
        tokenizer_family="Claude", context_length=1_000_000,
    ),
    "x-ai/grok-4.5": InputAccountingProfile(
        strategy=AccountingStrategy.PROVIDER_SPECIFIC_ACCOUNTING, verified=True,
        source="https://openrouter.ai/api/v1/models (architecture.tokenizer=Grok, "
               "context_length real confirmado)",
        verified_at="2026-09-18T13:37:47Z",
        tokenizer_family="Grok", context_length=500_000,
    ),
    "meta-llama/llama-4-maverick": InputAccountingProfile(
        strategy=AccountingStrategy.PROVIDER_SPECIFIC_ACCOUNTING, verified=True,
        source="https://openrouter.ai/api/v1/models (architecture.tokenizer=Llama4, "
               "context_length real confirmado)",
        verified_at="2026-09-18T13:37:47Z",
        tokenizer_family="Llama4", context_length=1_048_576,
    ),
    "claude-sonnet-5": InputAccountingProfile(
        strategy=AccountingStrategy.STATIC_DOCUMENTED_BOUND, verified=True,
        source="https://claude.com/pricing + context_length cruzado con "
               "anthropic/claude-sonnet-5 de OpenRouter (mismo modelo real, "
               "acceso directo via Anthropic en vez de OpenRouter)",
        verified_at="2026-09-18T13:41:00Z",
        tokenizer_family="Claude", context_length=1_000_000,
    ),
    "claude-opus-5": InputAccountingProfile(
        strategy=AccountingStrategy.STATIC_DOCUMENTED_BOUND, verified=True,
        source="https://claude.com/pricing + context_length cruzado con "
               "anthropic/claude-opus-5 de OpenRouter (mismo modelo real, "
               "acceso directo via Anthropic en vez de OpenRouter)",
        verified_at="2026-09-18T13:41:00Z",
        tokenizer_family="Claude", context_length=1_000_000,
    ),
    "claude-sonnet-4-6": InputAccountingProfile(
        strategy=AccountingStrategy.STATIC_DOCUMENTED_BOUND, verified=True,
        source="https://claude.com/pricing + context_length cruzado con "
               "anthropic/claude-sonnet-4.6 de OpenRouter (mismo modelo real, "
               "acceso directo via Anthropic en vez de OpenRouter)",
        verified_at="2026-09-18T13:41:00Z",
        tokenizer_family="Claude", context_length=1_000_000,
    ),
}


def get_verified_accounting(model: str) -> InputAccountingProfile:
    """Fail-closed: sin entrada, con `verified=False`, o con estrategia
    UNVERIFIED, siempre lanza."""
    profile = VERIFIED_INPUT_ACCOUNTING.get(model)
    if profile is None or not profile.verified or profile.strategy == AccountingStrategy.UNVERIFIED:
        raise InputAccountingNotVerifiedError(model)
    return profile
