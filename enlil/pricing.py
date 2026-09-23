"""ENLIL — Pricing VERIFICADO por modelo (guardarrail economico, fase 2
cierre de garantias 3/3).

Reglas del proyecto que este modulo aplica al pie de la letra (ver
CLAUDE.md, Regla XI "Proveniencia Activa" y Regla XII "Verificacion
Honesta"): ningun dato economico se presenta como verdad sin
proveniencia verificada, y si algo no esta verificado hay que decirlo
explicitamente en vez de asumir que un valor recordado sigue vigente.

`enlil/budget.py::MODEL_COSTS` es una tabla histórica de precios
aproximados ("mayo 2026", sin fuente citada, sin fecha de verificacion,
sin separar input/output) que YA EXISTIA para otro proposito
(`resolve_budget()`, dimensionar el `budget_tier` de una consulta antes
de saber que modelos concretos se van a usar) -- sigue existiendo tal
cual para eso, sin tocar. Pero el guardarrail economico real (cost_guard)
NO puede usarla como base de una decision de gasto: es un precio unico
"promedio" sin distinguir input/output (el output suele costar varias
veces mas que el input en la mayoria de proveedores -- usar la misma
tarifa para ambos puede INFRAESTIMAR el coste real de una respuesta
larga), y nadie la ha verificado contra una fuente viva en esta sesion.

Este modulo define una tabla NUEVA y SEPARADA, `VERIFIED_MODEL_PRICING`,
con input/output separados y un flag `verified` explicito.

**Esta tabla se deja VACIA a proposito.** No se ha hecho ninguna
llamada de red a una API de pricing (OpenRouter, Anthropic, etc.) en
esta sesion, y "recordar" un precio de entrenamiento no es
verificacion -- seria exactamente el tipo de cifra no verificada que la
Regla XII prohibe presentar como vigente. `get_verified_pricing()`
lanza `PricingNotVerifiedError` para CUALQUIER modelo mientras esta
tabla siga vacia -- lo que hace que `cost_guard.reserve()` deniegue
fail-closed toda llamada real (via `cost_unknown`/`pricing_not_verified`),
para TODOS los modelos, hasta que un humano popule esta tabla con
precios verificados de verdad (fuente + fecha), una decision explicita
y fuera del alcance de este modulo.

Los tests pueden (y deben) inyectar entradas ficticias en
`VERIFIED_MODEL_PRICING` via monkeypatch para probar el comportamiento
con pricing disponible -- eso es legitimo porque el test declara
explicitamente que el precio es ficticio, no porque el codigo de
produccion lo asuma.
"""
from __future__ import annotations

from dataclasses import dataclass


class PricingNotVerifiedError(RuntimeError):
    """No hay pricing verificado (input+output, con fuente/fecha) para
    este modelo. El caller (cost_guard.reserve()) debe fail-closed."""

    def __init__(self, model: str):
        self.model = model
        super().__init__(f"pricing_not_verified: {model}")


@dataclass(frozen=True)
class ModelPricing:
    input_usd_per_1k: float
    output_usd_per_1k: float
    verified: bool
    source: str = ""
    verified_at: str = ""  # fecha ISO de verificacion, "" si nunca


# Poblada con datos REALES obtenidos en vivo de dos fuentes oficiales
# (nunca recordados/inferidos -- ver Regla XI/XII de CLAUDE.md):
#
# REVERIFICACION 2026-09-23: los 7 modelos OpenRouter y los 3 Anthropic se
# volvieron a comprobar en vivo. Solo cambiaron (a la baja) deepseek-v4-pro
# (0.0016/0.0032 -> 0.000946386/0.001892772 por 1K) y nemotron-3-ultra
# (0.000625/0.003125 -> 0.0006/0.0024 por 1K). El precio de catalogo de
# OpenRouter es el del proveedor MAS BARATO del modelo; otros proveedores
# cobran mas (p.ej. deepseek hasta ~2x). Como provider.max_price se envia
# con este mismo precio, OpenRouter solo enruta a proveedores <= este
# precio: protege el gasto, pero si ese proveedor barato cae o sube de
# precio la llamada la rechaza OpenRouter (sin gasto).
# - OpenRouter: GET https://openrouter.ai/api/v1/models (publico, sin
#   autenticacion, metadata de catalogo -- no es una llamada de
#   inferencia). Fetch en vivo: 2026-09-23T20:47:27Z.
# - Anthropic: https://claude.com/pricing (pagina oficial de precios,
#   sin fecha de actualizacion publicada en la propia pagina -- fecha
#   de verificacion aqui es la fecha en que Claude Code la consulto,
#   no una fecha declarada por Anthropic).
#
# Los precios de OpenRouter llegan en USD/token; aqui se guardan en
# USD/1K tokens (multiplicados x1000), sin cambiar cifra significativa.
#
# BLOQUEO REAL DOCUMENTADO -- Inanna (mistralai/mistral-large-2512):
# el modelo EXISTE como entidad en el catalogo de OpenRouter, pero
# GET /api/v1/models/mistralai/mistral-large-2512/endpoints devuelve
# "endpoints": [] -- CERO endpoints en tiempo real activos hoy. Solo
# existe la variante ":batch" (procesamiento asincrono por lotes, NO
# compatible con una consulta de consejo en vivo). NO se ha inventado
# ninguna equivalencia ni sustituto -- Inanna se queda sin pricing
# verificado a proposito hasta que OpenRouter active un endpoint
# sincrono real para este modelo, o Miguel decida una sustitucion
# explicita y documentada.
#
# LIMITACION CONOCIDA (no oculta): 2 de estos modelos (gemini-2.5-pro-
# preview y grok-4.5) tienen tarificacion ESCALONADA en OpenRouter --
# una tarifa mayor si el prompt supera 200,000 tokens. Aqui se guarda
# SOLO la tarifa base (<200K prompt). Si algun dia una consulta real
# de ENLIL superase 200K tokens de entrada (hoy tecnicamente imposible:
# TIER_LIMITS tope 16,000 tokens de salida y los prompts del consejo
# son ordenes de magnitud menores), el coste real superaria la
# estimacion de este guardarrail -- riesgo residual documentado, no
# implementado en este cierre por no ser alcanzable con el uso actual.
VERIFIED_MODEL_PRICING: dict[str, ModelPricing] = {
    # --- Ruta primaria OpenRouter (7 modelos reales del panteon; falta
    #     mistralai/mistral-large-2512 de Inanna, bloqueado arriba) ---
    "anthropic/claude-sonnet-5": ModelPricing(
        input_usd_per_1k=0.002, output_usd_per_1k=0.01, verified=True,
        source="https://openrouter.ai/api/v1/models (id=anthropic/claude-sonnet-5, "
               "canonical_slug=anthropic/claude-sonnet-5-20260630)",
        verified_at="2026-09-23T20:47:27Z",
    ),
    "deepseek/deepseek-v4-pro": ModelPricing(
        input_usd_per_1k=0.000946386, output_usd_per_1k=0.001892772, verified=True,
        source="https://openrouter.ai/api/v1/models (id=deepseek/deepseek-v4-pro, "
               "canonical_slug=deepseek/deepseek-v4-pro-20260423)",
        verified_at="2026-09-23T20:47:27Z",
    ),
    "nvidia/nemotron-3-ultra-550b-a55b": ModelPricing(
        input_usd_per_1k=0.0006, output_usd_per_1k=0.0024, verified=True,
        source="https://openrouter.ai/api/v1/models (id=nvidia/nemotron-3-ultra-550b-a55b, "
               "canonical_slug=nvidia/nemotron-3-ultra-550b-a55b-20260604)",
        verified_at="2026-09-23T20:47:27Z",
    ),
    "google/gemini-2.5-pro-preview": ModelPricing(
        input_usd_per_1k=0.00125, output_usd_per_1k=0.01, verified=True,
        source="https://openrouter.ai/api/v1/models (id=google/gemini-2.5-pro-preview, "
               "canonical_slug=google/gemini-2.5-pro-preview-06-05; tarifa BASE, "
               "<200K prompt tokens -- ver nota de tarificacion escalonada arriba)",
        verified_at="2026-09-23T20:47:27Z",
    ),
    "anthropic/claude-opus-5": ModelPricing(
        input_usd_per_1k=0.005, output_usd_per_1k=0.025, verified=True,
        source="https://openrouter.ai/api/v1/models (id=anthropic/claude-opus-5, "
               "canonical_slug=anthropic/claude-opus-5-20260723)",
        verified_at="2026-09-23T20:47:27Z",
    ),
    "x-ai/grok-4.5": ModelPricing(
        input_usd_per_1k=0.002, output_usd_per_1k=0.006, verified=True,
        source="https://openrouter.ai/api/v1/models (id=x-ai/grok-4.5, "
               "canonical_slug=x-ai/grok-4.5-20260708; tarifa BASE, <200K prompt "
               "tokens -- ver nota de tarificacion escalonada arriba)",
        verified_at="2026-09-23T20:47:27Z",
    ),
    "meta-llama/llama-4-maverick": ModelPricing(
        input_usd_per_1k=0.0001875, output_usd_per_1k=0.0006525, verified=True,
        source="https://openrouter.ai/api/v1/models (id=meta-llama/llama-4-maverick, "
               "canonical_slug=meta-llama/llama-4-maverick-17b-128e-instruct)",
        verified_at="2026-09-23T20:47:27Z",
    ),
    # --- Fallback directo Anthropic (bare, via self._anthropic_client --
    #     NO pasa por OpenRouter, claves de dict SIN prefijo de proveedor,
    #     coinciden con los valores literales de _ANTHROPIC_MODEL_MAP en
    #     enlil/council.py) ---
    "claude-sonnet-5": ModelPricing(
        input_usd_per_1k=0.002, output_usd_per_1k=0.01, verified=True,
        source="https://claude.com/pricing ('Claude Sonnet 5': $2/MTok input, "
               "$10/MTok output) -- cruzado con anthropic/claude-sonnet-5 de "
               "OpenRouter, mismas cifras exactas",
        verified_at="2026-09-23T20:52:00Z",
    ),
    "claude-opus-5": ModelPricing(
        input_usd_per_1k=0.005, output_usd_per_1k=0.025, verified=True,
        source="https://claude.com/pricing ('Claude Opus 5': $5/MTok input, "
               "$25/MTok output) -- cruzado con anthropic/claude-opus-5 de "
               "OpenRouter, mismas cifras exactas",
        verified_at="2026-09-23T20:52:00Z",
    ),
    "claude-sonnet-4-6": ModelPricing(
        input_usd_per_1k=0.003, output_usd_per_1k=0.015, verified=True,
        source="https://claude.com/pricing ('Claude Sonnet 4.6': $3/MTok input, "
               "$15/MTok output) -- cruzado con anthropic/claude-sonnet-4.6 de "
               "OpenRouter, mismas cifras exactas",
        verified_at="2026-09-23T20:52:00Z",
    ),
}


def get_verified_pricing(model: str) -> ModelPricing:
    """Fail-closed: sin entrada, o con `verified=False`, siempre lanza."""
    pricing = VERIFIED_MODEL_PRICING.get(model)
    if pricing is None or not pricing.verified:
        raise PricingNotVerifiedError(model)
    return pricing


def estimate_cost_usd(
    model: str,
    *,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
) -> float:
    """Coste en USD para `model` a partir de tokens de entrada/salida
    (preferido, tarifas correctas por componente) o, si solo se conoce
    un total sin desglose fiable, aplicando la tarifa MAS CARA de las
    dos a todo el total -- para nunca subestimar cuando falta el
    desglose. Lanza PricingNotVerifiedError (fail-closed) si el modelo
    no tiene pricing verificado."""
    pricing = get_verified_pricing(model)
    if prompt_tokens is not None and completion_tokens is not None:
        return round(
            (max(int(prompt_tokens), 0) / 1000) * pricing.input_usd_per_1k
            + (max(int(completion_tokens), 0) / 1000) * pricing.output_usd_per_1k,
            6,
        )
    if total_tokens is not None:
        worst_rate = max(pricing.input_usd_per_1k, pricing.output_usd_per_1k)
        return round((max(int(total_tokens), 0) / 1000) * worst_rate, 6)
    raise ValueError("estimate_cost_usd requiere prompt_tokens+completion_tokens o total_tokens")
