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


# Vacia a proposito -- ver docstring del modulo. Rellenarla con precios
# reales verificados es una decision humana explicita, no algo que este
# codigo deba inferir.
VERIFIED_MODEL_PRICING: dict[str, ModelPricing] = {}


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
