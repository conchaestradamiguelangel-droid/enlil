"""ENLIL — llamada de embeddings protegida por el MISMO guardarrail que las
llamadas de chat (enlil/cost_guard.py), sin sistema paralelo.

Las dos rutas de embeddings de ENLIL (QdrantMemoryStore._embed en
enlil/memory_qdrant.py y CorpusStore._embed en enlil/corpus.py) comparten
cliente y modelo y pasan por aqui antes de tocar la red:

  ENLIL_ENABLED (kill switch superior)
  -> pricing verificado + accounting verificado + caps (cost_guard.reserve)
  -> mark_attempting()
  -> llamada
  -> settle() con usage fiable / settle_uncertain() si hubo red pero coste
     incierto / release() solo si la red nunca se toco.

Contrato existente de las dos rutas: cualquier fallo devuelve None y el
llamador degrada (Qdrant sin memoria / sin corpus, como ya hacia ante
cualquier excepcion del proveedor). Esta funcion mantiene exactamente ese
contrato -- nunca lanza, nunca inventa un vector.

Modelo actual: "text-embedding-3-small" (cadena literal enviada a
OpenRouter). Pricing/accounting: ver enlil/pricing.py y
enlil/input_accounting.py (clave literal "text-embedding-3-small").
"""
from __future__ import annotations

import logging

from .budget import estimate_content_token_upper_bound
from .cost_guard import (
    BudgetDeniedError,
    mark_attempting,
    release,
    reserve,
    settle,
    settle_uncertain,
)
from .pricing import estimate_cost_usd
from .reliability import classify_usage

logger = logging.getLogger("enlil.embedding_guard")

EMBEDDING_MODEL = "text-embedding-3-small"


def guarded_embeddings_create(embed_client, text: str, *, context: str):
    """Devuelve la respuesta cruda de `embed_client.embeddings.create(...)`
    o None si la llamada esta bloqueada o fallo. Sincrona, igual que los
    dos `_embed` que la usan."""
    # Import diferido: council.py es el unico sitio donde vive el kill
    # switch (_enlil_enabled) y no debe duplicarse.
    from .council import _enlil_enabled

    if not _enlil_enabled():
        logger.warning("[EMBED] ENLIL_ENABLED no activo -- embedding bloqueado (fail-closed) context=%s", context)
        return None

    try:
        reservation = reserve(
            EMBEDDING_MODEL, 0,
            input_tokens=estimate_content_token_upper_bound(text),
            context=context,
        )
    except BudgetDeniedError as exc:
        logger.warning("[EMBED] presupuesto denegado (%s) context=%s", exc.reason, context)
        return None

    settle_mode = "released"
    actual_cost_usd = 0.0
    try:
        mark_attempting(reservation.id)
        try:
            resp = embed_client.embeddings.create(model=EMBEDDING_MODEL, input=text)
        except Exception as exc:
            # La red SI se toco -- no sabemos si se facturo algo. Conservar
            # el worst-case reservado, nunca liberar a 0.
            settle_mode = "uncertain"
            logger.warning("[EMBED] Error generando embedding: %s context=%s", exc, context)
            return None

        usage_state, usage_fields = classify_usage(getattr(resp, "usage", None))
        if usage_state == "known":
            try:
                actual_cost_usd = estimate_cost_usd(
                    EMBEDDING_MODEL,
                    prompt_tokens=usage_fields["prompt_tokens"],
                    completion_tokens=usage_fields["completion_tokens"],
                    total_tokens=usage_fields["total_tokens"],
                )
                settle_mode = "settled"
            except Exception:
                settle_mode = "uncertain"
        else:
            settle_mode = "uncertain"
        return resp
    finally:
        if settle_mode == "settled":
            settle(reservation.id, actual_cost_usd)
        elif settle_mode == "uncertain":
            settle_uncertain(reservation.id, reservation.estimated_usd)
        else:
            release(reservation.id)
