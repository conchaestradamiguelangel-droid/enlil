"""ENLIL — Pipeline de documentos: extracción, chunking y análisis en masa."""
from __future__ import annotations
from enlil.telemetry import span, record_document, record_batch

import asyncio
import io
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Awaitable

# Threadpool para extracción CPU-bound (pdfminer/pypdf no son async)
_executor = ThreadPoolExecutor(max_workers=4)


# --- Extracción de texto ---

def extract_text(file_bytes: bytes, filename: str) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        return _extract_pdf(file_bytes)
    if name.endswith(".docx"):
        return _extract_docx(file_bytes)
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            return file_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return file_bytes.decode("utf-8", errors="replace")


async def extract_text_async(file_bytes: bytes, filename: str) -> str:
    """Extracción no bloqueante — corre en threadpool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, extract_text, file_bytes, filename)


def _extract_pdf(data: bytes) -> str:
    from pdfminer.high_level import extract_text_to_fp
    from pdfminer.layout import LAParams
    buf = io.StringIO()
    extract_text_to_fp(io.BytesIO(data), buf, laparams=LAParams())
    text = buf.getvalue()
    if len(text.strip()) > 100:
        return text
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(data))
        return "\n".join(p.extract_text() or "" for p in reader.pages)
    except Exception:
        return text


def _extract_docx(data: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


# --- Chunking ---

def chunk_text(text: str, size: int = 24000, overlap: int = 1200) -> list[str]:
    """Divide texto en trozos con solapamiento. Default 24K chars (~6K tokens)."""
    if len(text) <= size:
        return [text]
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return chunks


# --- Resultados ---

@dataclass
class DocumentResult:
    filename: str
    char_count: int
    chunk_count: int
    decree_id: str
    synthesis: str
    gods_convened: list[str]
    total_tokens: int
    latency_ms: float
    error: str | None = None


@dataclass
class BatchResult:
    documents: list[DocumentResult]
    cross_synthesis: str | None = None
    cross_decree_id: str | None = None
    total_tokens: int = 0
    total_latency_ms: float = 0.0


# --- Retry con backoff exponencial ---

async def _query_with_retry(
    orchestrator: Any,
    query: str,
    context: str,
    budget_tier: str,
    max_retries: int = 3,
) -> Any:
    last_exc = None
    for attempt in range(max_retries):
        try:
            return await orchestrator.query(query, context=context, budget_tier=budget_tier)
        except Exception as e:
            last_exc = e
            msg = str(e).lower()
            if any(x in msg for x in ("429", "rate limit", "too many")) and attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
                continue
            raise
    raise last_exc


# --- Motor de análisis ---

async def _summarize_chunks(
    orchestrator: Any,
    filename: str,
    chunks: list[str],
    chunk_concurrency: int = 5,
) -> str:
    """Resume cada chunk en paralelo con semáforo propio y retry."""
    sem = asyncio.Semaphore(chunk_concurrency)

    async def _summarize_one(i: int, chunk: str) -> str:
        async with sem:
            try:
                decree = await _query_with_retry(
                    orchestrator,
                    f"Resume el fragmento {i+1}/{len(chunks)} del documento '{filename}'. "
                    "Extrae puntos clave, datos, cifras y argumentos principales. "
                    "Respuesta concisa, máximo 300 palabras.",
                    context=chunk,
                    budget_tier="minimal",
                )
                return f"[Fragmento {i+1}/{len(chunks)}]\n{decree.synthesis}"
            except Exception as e:
                return f"[Fragmento {i+1}/{len(chunks)}] Error: {e}"

    summaries = await asyncio.gather(*[_summarize_one(i, c) for i, c in enumerate(chunks)])
    return "\n\n".join(summaries)


async def analyze_document(
    orchestrator: Any,
    filename: str,
    text: str,
    query: str,
    budget_tier: str = "standard",
    chunk_size: int = 24000,
) -> DocumentResult:
    t0 = time.monotonic()
    try:
        chunks = chunk_text(text, size=chunk_size)
        if len(chunks) > 1:
            context = await _summarize_chunks(orchestrator, filename, chunks)
        else:
            context = text[:32000]

        decree = await _query_with_retry(
            orchestrator,
            query,
            context=f"[Documento: {filename}]\n\n{context}",
            budget_tier=budget_tier,
        )
        _lat = round((time.monotonic() - t0) * 1000, 1)
        record_document(_lat, success=True)
        with span("enlil.document.analyze", filename=filename,
                  char_count=len(text), chunk_count=len(chunks),
                  decree_id=decree.id, latency_ms=_lat):
            pass
        return DocumentResult(
            filename=filename,
            char_count=len(text),
            chunk_count=len(chunks),
            decree_id=decree.id,
            synthesis=decree.synthesis,
            gods_convened=decree.gods_convened,
            total_tokens=decree.total_tokens,
            latency_ms=_lat,
        )
    except Exception as exc:
        _lat = round((time.monotonic() - t0) * 1000, 1)
        record_document(_lat, success=False)
        return DocumentResult(
            filename=filename,
            char_count=len(text),
            chunk_count=0,
            decree_id="",
            synthesis="",
            gods_convened=[],
            total_tokens=0,
            latency_ms=_lat,
            error=str(exc),
        )


async def batch_analyze(
    orchestrator: Any,
    documents: list[tuple[str, str]],
    query: str,
    budget_tier: str = "standard",
    cross_synthesis: bool = False,
    chunk_size: int = 24000,
    concurrency: int = 10,
    on_progress: Callable[[DocumentResult], Awaitable[None]] | None = None,
) -> BatchResult:
    """Analiza múltiples documentos con concurrencia controlada y callback de progreso."""
    semaphore = asyncio.Semaphore(concurrency)

    async def _bounded(filename: str, text: str) -> DocumentResult:
        async with semaphore:
            result = await analyze_document(
                orchestrator, filename, text, query, budget_tier, chunk_size
            )
            if on_progress:
                await on_progress(result)
            return result

    record_batch(len(documents))
    t0 = time.monotonic()
    results = list(await asyncio.gather(*[_bounded(fn, tx) for fn, tx in documents]))

    total_tokens = sum(r.total_tokens for r in results)
    total_latency = round((time.monotonic() - t0) * 1000, 1)

    cross_synth = None
    cross_id = None
    if cross_synthesis and len(results) > 1:
        ok = [r for r in results if not r.error and r.synthesis]
        if ok:
            summaries = "\n\n---\n\n".join(
                f"**{r.filename}**\n{r.synthesis[:2000]}" for r in ok
            )
            cross_decree = await _query_with_retry(
                orchestrator,
                f"Has recibido {len(ok)} análisis individuales. "
                "Sintetiza patrones comunes, contradicciones, tendencias y conclusión global.",
                context=summaries,
                budget_tier="full",
            )
            cross_synth = cross_decree.synthesis
            cross_id = cross_decree.id
            total_tokens += cross_decree.total_tokens

    return BatchResult(
        documents=results,
        cross_synthesis=cross_synth,
        cross_decree_id=cross_id,
        total_tokens=total_tokens,
        total_latency_ms=total_latency,
    )
