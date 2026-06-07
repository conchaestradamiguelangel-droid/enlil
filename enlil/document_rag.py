"""
ENLIL — Document RAG con BM25 (sin API calls, sin conflicto async/sync)

Indexacion y recuperacion por BM25 puro. Sin llamadas de red durante el proceso.
Los keywords de dominio enriquecen la query para direccionar bien cada dios.

Flujo:
  1. ingest(text)           -- trocea y construye indice BM25 en memoria
  2. retrieve_for_god(...)  -- cada dios busca sus fragmentos por BM25
  3. El council usa RAG en lugar del chunker posicional para docs grandes
"""

import re
import hashlib
import logging
import math
from typing import Optional

logger = logging.getLogger("enlil.rag")

CHUNK_SIZE      = 1_500   # chars por fragmento
CHUNK_OVERLAP   = 200     # solapamiento entre fragmentos
TOP_K           = 6       # fragmentos por dios
RAG_THRESHOLD   = 500_000  # desactivado: el pipeline RAG completo consume demasiada RAM en instancias pequeñas

# Palabras clave por dominio para enriquecer la query BM25
_DOMAIN_KEYWORDS: dict[str, str] = {
    "context":       "contexto situacion antecedentes partes implicadas",
    "alignment":     "alineacion coherencia objetivo proposito",
    "technical":     "tecnico implementacion sistema arquitectura",
    "code":          "codigo funcion metodo clase algoritmo",
    "security":      "seguridad riesgo vulnerabilidad amenaza proteccion",
    "threat":        "amenaza ataque vector riesgo exposicion",
    "audit":         "auditoria cumplimiento control revision",
    "legal":         "clausula contrato obligacion derecho jurisdiccion ley articulo",
    "logic":         "razonamiento deduccion premisa conclusion contradiccion",
    "strategy":      "estrategia decision oportunidad ventaja competitiva",
    "analysis":      "analisis datos cifras indicadores metricas",
    "math":          "calculo numero importe porcentaje fecha plazo",
    "creative":      "propuesta alternativa innovacion solucion creativa",
    "evolution":     "tendencia cambio progresion patron historico",
    "meta":          "resumen global estructura indice seccion capitulo",
    "supreme":       "conclusion dictamen veredicto decision final",
    "judgment":      "valoracion criterio ponderacion impacto consecuencia",
}

_DEFAULT_KEYWORDS = "informacion relevante contenido clave"

_TOKEN_RE = re.compile(r'\w+', re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _domain_query(domains: list, user_query: str) -> str:
    kw = " ".join(
        _DOMAIN_KEYWORDS.get(d, "") for d in domains if d in _DOMAIN_KEYWORDS
    ).strip() or _DEFAULT_KEYWORDS
    return f"{user_query} {kw}"


def _split_chunks(text: str) -> list[str]:
    chunks = []
    pos = 0
    while pos < len(text):
        end = pos + CHUNK_SIZE
        chunk = text[pos:end]
        if end < len(text):
            nl = chunk.rfind("\n\n")
            if nl > CHUNK_SIZE // 2:
                chunk = chunk[:nl]
            else:
                nl = chunk.rfind("\n")
                if nl > CHUNK_SIZE * 0.8:
                    chunk = chunk[:nl]
        chunks.append(chunk.strip())
        pos += len(chunk) - CHUNK_OVERLAP
        if pos >= len(text):
            break
    return [c for c in chunks if len(c) > 100]


def _doc_id_from_text(text: str) -> str:
    return hashlib.sha256(text[:5000].encode()).hexdigest()[:16]


class _BM25Index:
    """Indice BM25 minimo en puro Python. Sin dependencias externas."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.chunks: list[str] = []
        self._doc_tokens: list[list[str]] = []
        self._df: dict[str, int] = {}
        self._avgdl: float = 0.0
        self._idf: dict[str, float] = {}

    def build(self, chunks: list[str]) -> None:
        self.chunks = chunks
        self._doc_tokens = [_tokenize(c) for c in chunks]
        n = len(chunks)
        self._avgdl = sum(len(t) for t in self._doc_tokens) / max(n, 1)

        self._df = {}
        for tokens in self._doc_tokens:
            for tok in set(tokens):
                self._df[tok] = self._df.get(tok, 0) + 1

        self._idf = {}
        for tok, df in self._df.items():
            self._idf[tok] = math.log((n - df + 0.5) / (df + 0.5) + 1)

    def score(self, query_tokens: list[str], doc_idx: int) -> float:
        tokens = self._doc_tokens[doc_idx]
        dl = len(tokens)
        tf_map: dict[str, int] = {}
        for t in tokens:
            tf_map[t] = tf_map.get(t, 0) + 1

        score = 0.0
        k1, b, avgdl = self.k1, self.b, self._avgdl
        for tok in query_tokens:
            if tok not in self._idf:
                continue
            tf = tf_map.get(tok, 0)
            idf = self._idf[tok]
            num = tf * (k1 + 1)
            den = tf + k1 * (1 - b + b * dl / max(avgdl, 1))
            score += idf * num / max(den, 1e-9)
        return score

    def search(self, query: str, top_k: int) -> list[tuple[int, float]]:
        q_tokens = _tokenize(query)
        if not q_tokens:
            return []
        scores = [(i, self.score(q_tokens, i)) for i in range(len(self.chunks))]
        scores = [(i, s) for i, s in scores if s > 0]
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


class DocumentRAGStore:
    """
    Almacen RAG de documentos basado en BM25.
    Sin llamadas de red, sin conflicto async/sync, sin dependencias pesadas.
    Cada documento se trocea y se indexa en RAM en milisegundos.
    Cada dios recupera sus fragmentos relevantes por puntuacion BM25.
    """

    def __init__(self, qdrant_store=None):
        # doc_id -> _BM25Index
        self._store: dict[str, _BM25Index] = {}
        self._available = True  # siempre disponible: no necesita dependencias externas
        logger.info("[RAG] DocumentRAGStore BM25 activo")

    def ingest(self, text: str) -> Optional[str]:
        try:
            doc_id = _doc_id_from_text(text)

            if doc_id in self._store:
                logger.info(f"[RAG] Documento {doc_id} ya en memoria -- reutilizando")
                return doc_id

            chunks = _split_chunks(text)
            logger.info(f"[RAG] Indexando {doc_id} con BM25 -- {len(chunks)} fragmentos")

            index = _BM25Index()
            index.build(chunks)
            self._store[doc_id] = index

            logger.info(f"[RAG] Indice BM25 construido para {doc_id} ({len(chunks)} fragmentos)")
            return doc_id
        except Exception as e:
            logger.warning(f"[RAG] Error en ingest: {e}")
            return None

    def retrieve_for_god(self, doc_id: str, domains: list,
                         user_query: str, top_k: int = TOP_K) -> str:
        if doc_id not in self._store:
            return ""
        try:
            index = self._store[doc_id]
            query = _domain_query(domains, user_query)
            results = index.search(query, top_k)

            if not results:
                return ""

            results.sort(key=lambda x: x[0])

            parts = []
            prev_idx = -99
            for idx, score in results:
                if idx > prev_idx + 1 and parts:
                    parts.append("\n[...]\n")
                parts.append(index.chunks[idx])
                prev_idx = idx

            assembled = "\n\n".join(parts)
            god_name = domains[0] if domains else "?"
            logger.info(f"[RAG] {doc_id} -- dios:{god_name} -- {len(results)} fragmentos (BM25)")
            return assembled

        except Exception as e:
            logger.warning(f"[RAG] Error en retrieve: {e}")
            return ""

    def evict(self, doc_id: str) -> None:
        self._store.pop(doc_id, None)

    @property
    def is_available(self) -> bool:
        return self._available
