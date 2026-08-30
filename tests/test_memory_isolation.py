"""
ENLIL — Aislamiento de memoria semantica entre clientes (P0, 2026-08-29)
==========================================================================
Codex encontro que enlil/orchestrator.py recuperaba memoria previa
(Qdrant y fallback SQLite) sin filtrar por client_id -- el sistema
podia inyectar fragmentos de la consulta/sintesis de un cliente B en
el contexto que recibe un cliente A semanticamente similar, sin que A
conociera ningun UUID.

Este fichero demuestra, con un marcador unico por ejecucion:
  1-5. B guarda y recupera lo suyo; A nunca ve el marcador de B ni
       memoria legacy/default; B tampoco ve memoria de A.
  6.   Qdrant respeta el aislamiento (cliente Qdrant simulado que SI
       aplica el filtro, como el motor real).
  7.   El fallback SQLite cumple exactamente la misma politica.
  8.   Una fila sin client_id poblado (legacy real) no se entrega.
  9.   El propietario legitimo sigue funcionando con normalidad.
  10.  (bonus) El marcador de B no llega ni siquiera al *contexto* que
       reciben los dioses/LLM -- la fuga esta cerrada en el pipeline
       completo, no solo en la superficie de la API.

No usa datos reales ni llama a ningun modelo real (council.convene /
council.synthesize se mockean siempre). No usa ENLIL_DB de produccion.
"""
import os
import random
import string
import asyncio

os.environ.setdefault("OPENROUTER_API_KEY", "test")
os.environ.setdefault("ENLIL_DB", ":memory:")

from unittest.mock import MagicMock, AsyncMock, patch

from enlil.memory import MemoryStore
from enlil.memory_qdrant import QdrantMemoryStore
from enlil.decrees.decree import Decree
from enlil.gods.base import GodResponse

# Puramente alfabético a propósito: MemoryStore._sanitize() (FTS5) solo
# conserva palabras que pasan w.isalpha() — un marcador con dígitos o
# guiones bajos (p.ej. un UUID hex) nunca sobreviviría al saneado y el
# test de "B recupera lo suyo" fallaría por eso, no por aislamiento.
SECRET_MARKER_B = "SECRETMARKERB" + "".join(random.choices(string.ascii_uppercase, k=12))


def _decree(query: str, synthesis: str, client_id: str = "default") -> Decree:
    return Decree(
        query=query, domains=["technical"], gods_convened=["claude"],
        voices=[], synthesis=synthesis, total_tokens=10,
        budget_tier="minimal", client_id=client_id,
    )


def _mock_god_response(content: str = "respuesta mock") -> GodResponse:
    return GodResponse(god_name="claude", model="mock/model", content=content, tokens_used=10, latency_ms=50.0)


# ─────────────────────────────────────────────
# Tests 1-5, 7, 8, 9 — fallback SQLite (MemoryStore)
# ─────────────────────────────────────────────

class TestAislamientoMemoriaSQLite:
    """Fallback SQLite (enlil/memory.py) — misma política que Qdrant."""

    def setup_method(self):
        self.mem = MemoryStore(":memory:")

    def test_1y2_b_guarda_y_recupera_su_propio_marcador(self):
        self.mem.store(_decree(f"fusion confidencial {SECRET_MARKER_B}", f"analisis {SECRET_MARKER_B}", client_id="cliente-b"))
        result = self.mem.search(SECRET_MARKER_B, client_id="cliente-b")
        assert SECRET_MARKER_B in result

    def test_3_a_no_recupera_marcador_de_b(self):
        self.mem.store(_decree(f"fusion confidencial {SECRET_MARKER_B}", f"analisis {SECRET_MARKER_B}", client_id="cliente-b"))
        result = self.mem.search(SECRET_MARKER_B, client_id="cliente-a")
        assert SECRET_MARKER_B not in result
        assert result == ""

    def test_4_a_no_recupera_memoria_legacy_default(self):
        self.mem.store(_decree("dato legacy huerfano sin dueno", "sintesis legacy huerfana"))  # client_id="default"
        result = self.mem.search("dato legacy huerfano dueno", client_id="cliente-a")
        assert result == ""

    def test_5_b_no_recupera_memoria_de_a(self):
        self.mem.store(_decree("secreto de A sobre litigio pendiente", "sintesis confidencial A", client_id="cliente-a"))
        result = self.mem.search("secreto litigio pendiente", client_id="cliente-b")
        assert result == ""

    def test_7_fallback_sqlite_cumple_la_misma_politica_sin_client_id(self):
        """Sin client_id, ninguna búsqueda se realiza — igual que Qdrant."""
        self.mem.store(_decree(f"consulta con {SECRET_MARKER_B}", "sintesis"))
        assert self.mem.search(SECRET_MARKER_B) == ""
        assert self.mem.search(SECRET_MARKER_B, client_id="") == ""
        assert self.mem.search(SECRET_MARKER_B, client_id=None) == ""

    def test_8_fila_sin_client_id_poblado_no_se_entrega(self):
        """Simula una fila legacy real anterior a la migración (columna sin poblar por store())."""
        self.mem._conn.execute(
            "INSERT INTO memory_entries (decree_id, timestamp, query, synthesis, domains, gods) VALUES (?,?,?,?,?,?)",
            ("legacy-real-1", 0.0, "query legacy nunca migrada", "sintesis legacy nunca migrada", "technical", "claude"),
        )
        self.mem._conn.commit()
        result = self.mem.search("query legacy nunca migrada", client_id="cliente-a")
        assert result == ""

    def test_9_propietario_legitimo_sigue_funcionando(self):
        self.mem.store(_decree("consulta normal de B sobre contratos", "respuesta normal sobre contratos", client_id="cliente-b"))
        result = self.mem.search("consulta normal contratos", client_id="cliente-b")
        assert "respuesta normal" in result


# ─────────────────────────────────────────────
# Test 6 — Qdrant (cliente simulado que SÍ aplica el filtro, como el motor real)
# ─────────────────────────────────────────────

class _FakeMatchValue:
    def __init__(self, value):
        self.value = value


class _FakeFieldCondition:
    def __init__(self, key, match):
        self.key = key
        self.match = match


class _FakeFilter:
    def __init__(self, must):
        self.must = must


class _FakePoint:
    def __init__(self, payload):
        self.payload = payload


def _build_mock_qdrant_store(all_points):
    """
    QdrantMemoryStore 'activo' con un cliente simulado cuyo
    query_points() SÍ respeta query_filter (filtra all_points por
    payload["client_id"], como el motor real) — así el test verifica
    que NUESTRO código construye y pasa el filtro correcto, no solo
    que "algo" se llamó.
    """
    def _fake_query_points(collection_name, query, limit, score_threshold, query_filter=None):
        pts = all_points
        if query_filter is not None:
            for cond in query_filter.must:
                pts = [p for p in pts if p.payload.get(cond.key) == cond.match.value]
        return MagicMock(points=pts[:limit])

    mock_client = MagicMock()
    mock_client.get_collections.return_value = MagicMock(collections=[])
    mock_client.query_points.side_effect = _fake_query_points

    mock_qdrant_module = MagicMock()
    mock_qdrant_module.QdrantClient.return_value = mock_client

    mock_models_module = MagicMock()
    mock_models_module.Filter = _FakeFilter
    mock_models_module.FieldCondition = _FakeFieldCondition
    mock_models_module.MatchValue = _FakeMatchValue

    mock_embed_client = MagicMock()
    mock_embed_client.embeddings.create.return_value = MagicMock(data=[MagicMock(embedding=[0.1] * 1536)])

    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test"}):
        with patch.dict("sys.modules", {"qdrant_client": mock_qdrant_module, "qdrant_client.models": mock_models_module}):
            with patch("openai.OpenAI", return_value=mock_embed_client):
                suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
                store = QdrantMemoryStore(path="/tmp/test_qdrant_isolation_" + suffix)

    assert store.is_available is True
    return store


class TestAislamientoMemoriaQdrant:
    def test_6_qdrant_filtra_por_client_id(self):
        # Nota sobre el mock: _fake_query_points simula el filtro real de
        # Qdrant por payload, pero no simula relevancia semántica — por
        # eso este caso solo incluye puntos de B y legacy, para que un
        # resultado vacío para A demuestre aislamiento y no una simple
        # ausencia de coincidencia semántica casual.
        points = [
            _FakePoint({"query": f"fusion {SECRET_MARKER_B}", "synthesis": f"analisis {SECRET_MARKER_B}", "client_id": "cliente-b"}),
            _FakePoint({"query": "consulta legacy", "synthesis": "sintesis legacy", "client_id": "default"}),
        ]
        store = _build_mock_qdrant_store(points)

        result_a = store.search(SECRET_MARKER_B, client_id="cliente-a")
        assert SECRET_MARKER_B not in result_a
        assert result_a == ""

        result_b = store.search(SECRET_MARKER_B, client_id="cliente-b")
        assert SECRET_MARKER_B in result_b

        result_a_legacy = store.search("consulta legacy", client_id="cliente-a")
        assert result_a_legacy == ""

    def test_6b_qdrant_cliente_a_si_recupera_lo_suyo(self):
        """Con un punto propio en la colección, A sigue funcionando con normalidad."""
        points = [
            _FakePoint({"query": "consulta de A", "synthesis": "respuesta A", "client_id": "cliente-a"}),
            _FakePoint({"query": f"fusion {SECRET_MARKER_B}", "synthesis": f"analisis {SECRET_MARKER_B}", "client_id": "cliente-b"}),
        ]
        store = _build_mock_qdrant_store(points)
        result_a = store.search("consulta de A", client_id="cliente-a")
        assert "respuesta A" in result_a
        assert SECRET_MARKER_B not in result_a

    def test_qdrant_sin_client_id_no_busca(self):
        points = [_FakePoint({"query": "x", "synthesis": "y", "client_id": "cliente-a"})]
        store = _build_mock_qdrant_store(points)
        assert store.search("x") == ""
        assert store.search("x", client_id="") == ""


# ─────────────────────────────────────────────
# Test 10 (bonus) — el marcador no llega ni al contexto del Consejo/LLM
# ─────────────────────────────────────────────

class TestFugaCerradaEnPipelineCompleto:
    """
    No basta con que la API no devuelva el fragmento — hay que probar
    que el marcador de B ni siquiera entra en el `context` que se
    envía a los dioses/LLM al construir la respuesta de A.
    """

    def test_marcador_de_b_no_llega_al_contexto_del_consejo(self):
        with patch("openai.AsyncOpenAI"):
            from enlil.orchestrator import Orchestrator
            orch = Orchestrator(db_path=":memory:")

        # B genera un decreto real con el marcador, vía el flujo
        # completo orch.query() (no un store() directo) para que quede
        # exactamente como quedaría en producción.
        with patch.object(orch.council, "convene", new=AsyncMock(return_value=[_mock_god_response(f"respuesta B {SECRET_MARKER_B}")])), \
             patch.object(orch.council, "synthesize", new=AsyncMock(return_value=(f"sintesis confidencial de B {SECRET_MARKER_B}", []))):
            asyncio.run(orch.query(f"analisis de fusion empresarial {SECRET_MARKER_B}", client_id="cliente-b"))

        # A hace una consulta semánticamente equivalente. Capturamos el
        # `context` real que orchestrator.query() pasa a council.convene.
        captured = {}

        async def _capturing_convene(god_names, text, context, **kwargs):
            captured["context"] = context
            return [_mock_god_response("respuesta A")]

        with patch.object(orch.council, "convene", new=_capturing_convene), \
             patch.object(orch.council, "synthesize", new=AsyncMock(return_value=("sintesis de A", []))):
            asyncio.run(orch.query("analisis de fusion empresarial", client_id="cliente-a"))

        assert SECRET_MARKER_B not in captured["context"], (
            "el marcador de B llegó al contexto que reciben los dioses/LLM — "
            "fuga real en el pipeline, no solo en la respuesta de la API"
        )
