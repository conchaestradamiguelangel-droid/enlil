"""ENLIL — Observabilidad: trazas OTEL + métricas Prometheus."""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from typing import Any

# ── Prometheus (siempre activo) ────────────────────────────────────────────────
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST

REGISTRY = CollectorRegistry(auto_describe=True)

# Contadores
DECREES_TOTAL = Counter(
    "enlil_decrees_total",
    "Decretos emitidos por el Consejo",
    ["budget_tier", "domain"],
    registry=REGISTRY,
)
TOKENS_TOTAL = Counter(
    "enlil_tokens_total",
    "Tokens consumidos",
    ["god", "tier"],
    registry=REGISTRY,
)
GOD_ERRORS_TOTAL = Counter(
    "enlil_god_errors_total",
    "Errores por dios",
    ["god"],
    registry=REGISTRY,
)
DOCUMENTS_TOTAL = Counter(
    "enlil_documents_total",
    "Documentos analizados",
    ["status"],
    registry=REGISTRY,
)

# Histogramas de latencia
GOD_LATENCY = Histogram(
    "enlil_god_latency_seconds",
    "Latencia por dios (segundos)",
    ["god", "model"],
    buckets=[0.5, 1, 2, 5, 10, 20, 30, 60],
    registry=REGISTRY,
)
DECREE_LATENCY = Histogram(
    "enlil_decree_latency_seconds",
    "Latencia total del decreto",
    ["budget_tier"],
    buckets=[1, 2, 5, 10, 20, 30, 60, 120],
    registry=REGISTRY,
)
DOCUMENT_LATENCY = Histogram(
    "enlil_document_latency_seconds",
    "Latencia por documento",
    buckets=[1, 2, 5, 10, 20, 30, 60],
    registry=REGISTRY,
)
BATCH_SIZE = Histogram(
    "enlil_batch_size",
    "Tamaño de batches de documentos",
    buckets=[1, 2, 5, 10, 25, 50, 100, 250],
    registry=REGISTRY,
)

# Gauges de reputación (actualizado periódicamente)
GOD_REPUTATION = Gauge(
    "enlil_god_reputation",
    "Reputación actual por dios y dominio",
    ["god", "domain"],
    registry=REGISTRY,
)

# ── OpenTelemetry (opcional — activo si OTEL_EXPORTER_OTLP_ENDPOINT está set) ──

_tracer = None
_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "enlil")


def setup_otel():
    """Inicializa OTEL. Llámalo al arrancar el servicio."""
    global _tracer

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource({
            "service.name": _SERVICE_NAME,
            "service.version": "2.1.0",
        })
        tp = TracerProvider(resource=resource)

        if _OTLP_ENDPOINT:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=f"{_OTLP_ENDPOINT.rstrip('/')}/v1/traces")
            tp.add_span_processor(BatchSpanProcessor(exporter))

        trace.set_tracer_provider(tp)
        _tracer = trace.get_tracer(_SERVICE_NAME)

        status = f"OTEL activo → {_OTLP_ENDPOINT}" if _OTLP_ENDPOINT else "OTEL activo (sin exportador remoto)"
        print(f"[telemetry] {status}")

    except Exception as e:
        print(f"[telemetry] OTEL no disponible: {e}")
        _tracer = None


@contextmanager
def span(name: str, **attributes):
    """Context manager que crea un span OTEL si está disponible, o no-op."""
    if _tracer is None:
        yield _NoOpSpan()
        return
    with _tracer.start_as_current_span(name) as s:
        for k, v in attributes.items():
            if v is not None:
                s.set_attribute(k, str(v))
        yield s


class _NoOpSpan:
    def set_attribute(self, *_): pass
    def add_event(self, *_): pass
    def record_exception(self, *_): pass
    def set_status(self, *_): pass


# ── Helpers para instrumentar funciones clave ─────────────────────────────────

def record_god_call(god_name: str, model: str, tokens: int, latency_ms: float, error: bool = False):
    """Registra métricas de una llamada a un dios."""
    GOD_LATENCY.labels(god=god_name, model=model).observe(latency_ms / 1000)
    if tokens > 0:
        TOKENS_TOTAL.labels(god=god_name, tier="god").inc(tokens)
    if error:
        GOD_ERRORS_TOTAL.labels(god=god_name).inc()


def record_decree(budget_tier: str, domain: str, latency_ms: float, total_tokens: int):
    """Registra métricas de un decreto completo."""
    DECREES_TOTAL.labels(budget_tier=budget_tier, domain=domain or "general").inc()
    DECREE_LATENCY.labels(budget_tier=budget_tier).observe(latency_ms / 1000)
    if total_tokens > 0:
        TOKENS_TOTAL.labels(god="synthesis", tier=budget_tier).inc(total_tokens)


def record_document(latency_ms: float, success: bool):
    """Registra métricas de análisis de un documento."""
    DOCUMENTS_TOTAL.labels(status="ok" if success else "error").inc()
    if success:
        DOCUMENT_LATENCY.observe(latency_ms / 1000)


def record_batch(size: int):
    """Registra el tamaño de un batch."""
    BATCH_SIZE.observe(size)


def update_reputation_gauges(pantheon_data: list[dict]):
    """Actualiza los gauges de reputación. Llamar periódicamente."""
    for god in pantheon_data:
        name = god.get("name", "")
        for domain, data in god.get("reputation", {}).items():
            score = data.get("score", 0) if isinstance(data, dict) else data
            GOD_REPUTATION.labels(god=name, domain=domain).set(score)


def prometheus_output() -> tuple[bytes, str]:
    """Devuelve métricas en formato Prometheus para el endpoint /metrics."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
