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


# Vacia a proposito -- ver docstring del modulo. Ningun modelo tiene
# hoy un metodo de contabilizacion de input verificado.
VERIFIED_INPUT_ACCOUNTING: dict[str, InputAccountingProfile] = {}


def get_verified_accounting(model: str) -> InputAccountingProfile:
    """Fail-closed: sin entrada, con `verified=False`, o con estrategia
    UNVERIFIED, siempre lanza."""
    profile = VERIFIED_INPUT_ACCOUNTING.get(model)
    if profile is None or not profile.verified or profile.strategy == AccountingStrategy.UNVERIFIED:
        raise InputAccountingNotVerifiedError(model)
    return profile
