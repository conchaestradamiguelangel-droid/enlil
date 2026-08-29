"""
Memoria vectorial con Qdrant.
Usa embeddings de texto para búsqueda semántica real.
Fallback automático a MemoryStore (FTS) si Qdrant no está disponible.

Modos de operación (por prioridad):
  1. Servidor externo: QDRANT_URL apunta a un servidor Qdrant
  2. Embedded local:   QDRANT_PATH apunta a un directorio local
  3. Inactivo:         si no hay API key de embeddings disponible
"""
import os
import hashlib
import logging
from typing import Optional
from .decrees.decree import Decree

logger = logging.getLogger("enlil.qdrant")

QDRANT_URL        = os.environ.get("QDRANT_URL", "")
QDRANT_PATH       = os.environ.get("QDRANT_PATH", "")
QDRANT_COLLECTION = "enlil_decrees"
EMBEDDING_MODEL   = "text-embedding-3-small"


class QdrantMemoryStore:
    """
    Memoria vectorial real con búsqueda semántica.
    Se activa automáticamente cuando hay API key + Qdrant disponible.
    Sin clave o sin Qdrant: silencio total, sin errores.
    """

    def __init__(self, path: str = QDRANT_PATH, url: str = QDRANT_URL):
        self._available = False
        self._client = None
        self._embed_client = None
        self._mode = "inactive"
        self._try_init(url=url, path=path)

    def _try_init(self, url: str, path: str):
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams

            api_key = (
                os.environ.get("OPENROUTER_API_KEY") or
                os.environ.get("OPENAI_API_KEY", "")
            )
            if not api_key:
                logger.info("[QDRANT] Sin API key para embeddings — inactivo hasta que se configure OPENROUTER_API_KEY")
                return

            # Intentar conexión a servidor o embedded
            if url:
                client = QdrantClient(url=url, timeout=3)
                client.get_collections()  # prueba de conectividad
                self._mode = "server"
            elif path:
                os.makedirs(path, exist_ok=True)
                client = QdrantClient(path=path)
                self._mode = "embedded"
            else:
                logger.info("[QDRANT] Sin QDRANT_URL ni QDRANT_PATH configurados")
                return

            # Crear colección si no existe
            existing = [c.name for c in client.get_collections().collections]
            if QDRANT_COLLECTION not in existing:
                client.create_collection(
                    collection_name=QDRANT_COLLECTION,
                    vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
                )

            # Cliente de embeddings
            from openai import OpenAI
            base_url = "https://openrouter.ai/api/v1" if os.environ.get("OPENROUTER_API_KEY") else None
            embed_client = OpenAI(api_key=api_key, base_url=base_url)

            self._client = client
            self._embed_client = embed_client
            self._available = True
            logger.info(f"[QDRANT] Activo — modo={self._mode} colección={QDRANT_COLLECTION}")

        except Exception as e:
            logger.debug(f"[QDRANT] No disponible: {e}")
            self._available = False

    def _embed(self, text: str) -> Optional[list[float]]:
        try:
            resp = self._embed_client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=text[:2000],
            )
            return resp.data[0].embedding
        except Exception as e:
            logger.warning(f"[QDRANT] Error generando embedding: {e}")
            return None

    def store(self, decree: Decree) -> None:
        if not self._available:
            return
        try:
            from qdrant_client.models import PointStruct
            text = f"{decree.query} {decree.synthesis}"
            vector = self._embed(text)
            if not vector:
                return
            point_id = int(hashlib.md5(decree.id.encode()).hexdigest()[:8], 16)
            self._client.upsert(
                collection_name=QDRANT_COLLECTION,
                points=[PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "decree_id":  decree.id,
                        "query":      decree.query[:500],
                        "synthesis":  decree.synthesis[:500],
                        "domains":    decree.domains,
                        "gods":       decree.gods_convened,
                        # Aislamiento por cliente (fix P0 2026-08-29). Puntos
                        # antiguos sin este campo no llevan migración —
                        # Qdrant no exige recrear entradas para añadir un
                        # campo de payload nuevo, y un filtro por
                        # client_id="X" simplemente no matchea puntos que
                        # nunca tuvieron ese campo (quedan invisibles para
                        # cualquier búsqueda normal, igual que "legacy").
                        "client_id":  getattr(decree, "client_id", None) or "default",
                    },
                )],
            )
        except Exception as e:
            logger.warning(f"[QDRANT] Error almacenando decreto: {e}")

    def search(self, query: str, limit: int = 3, client_id: Optional[str] = None) -> str:
        """
        Búsqueda semántica aislada por client_id.

        Sin client_id (None/vacío) no se realiza ninguna búsqueda — se
        devuelve "" directamente. Fallar cerrado (sin memoria) es
        preferible a fallar abierto (memoria de otro cliente filtrada
        por accidente si algún caller nuevo olvida pasar client_id).
        """
        if not self._available or not client_id:
            return ""
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            vector = self._embed(query)
            if not vector:
                return ""
            results = self._client.query_points(
                collection_name=QDRANT_COLLECTION,
                query=vector,
                limit=limit,
                score_threshold=0.6,
                query_filter=Filter(
                    must=[FieldCondition(key="client_id", match=MatchValue(value=client_id))]
                ),
            ).points
            if not results:
                return ""
            parts = []
            for r in results:
                q = r.payload.get("query", "")[:100]
                s = r.payload.get("synthesis", "")[:200]
                parts.append(f"- Consulta: {q}\n  Síntesis: {s}")
            return "\n".join(parts)
        except Exception as e:
            logger.warning(f"[QDRANT] Error en búsqueda: {e}")
            return ""

    def count(self) -> int:
        if not self._available:
            return 0
        try:
            info = self._client.get_collection(QDRANT_COLLECTION)
            return info.points_count or 0
        except Exception:
            return 0

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def mode(self) -> str:
        return self._mode
