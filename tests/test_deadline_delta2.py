"""Corrección delta-2 post-auditoría Codex sobre 3d53209:
1) apertura de synthesize_stream (chat.completions.create(stream=True))
   protegida por el mismo asyncio.timeout que el consumo, no solo la
   iteración;
2) deadline es keyword-only obligatorio en las 6 funciones afectadas,
   sin default None y sin depender de `assert` (que desaparece con
   `python -O`)."""
import asyncio
import inspect
import os
import time
import uuid
import tempfile
import json

os.environ.setdefault("OPENROUTER_API_KEY", "sk-or-test")

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from enlil.council import Council
from enlil.gods.base import GodProfile, GodResponse


def _make_council():
    pantheon = {"MOCK_GOD": GodProfile(name="MOCK_GOD", model="test-model", role="mock", domains=["consulta"])}
    council = Council(pantheon=pantheon)
    council._anthropic_client = None
    return council


def _voice():
    return GodResponse(
        god_name="MOCK_GOD", model="m", content="voz", tokens_used=10,
        latency_ms=1.0, voice_status="complete", finish_reason="stop",
    )


# ── 1. Apertura de synthesize_stream protegida por el deadline real ─────

class TestAperturaDeStreamProtegidaPorDeadline:
    def test_proveedor_lento_al_abrir_no_sobrevive_al_deadline(self):
        """remaining ~= 50ms, el 'proveedor' tarda ~150ms en devolver el
        stream -- ENLIL debe cortar dentro del deadline, no clasificar
        'complete', y la apertura lenta no debe completar nunca (prueba
        de que no queda una tarea/stream huérfano corriendo en segundo
        plano, análoga a test_wait_for_externo_cancela...)."""
        council = _make_council()
        opened = {"value": False}

        async def slow_create(**kwargs):
            await asyncio.sleep(0.15)
            opened["value"] = True   # solo se alcanzaría si NO se canceló a tiempo
            stream_mock = MagicMock()
            return stream_mock

        council._client = MagicMock()
        council._client.chat.completions.create = AsyncMock(side_effect=slow_create)

        deadline = time.monotonic() + 0.05
        t0 = time.monotonic()

        async def collect():
            items = []
            async for item in council.synthesize_stream([_voice()], "q", deadline=deadline):
                items.append(item)
            return items

        items = asyncio.run(collect())
        elapsed = time.monotonic() - t0

        assert opened["value"] is False, (
            "la apertura del stream debió cancelarse de verdad -- si esto "
            "es True, la llamada lenta terminó igualmente en segundo plano"
        )
        # Cortó cerca del deadline (~50ms), no cerca de los 150ms que
        # tardaría el proveedor en abrir si no estuviera protegido.
        assert elapsed < 0.12, f"tardó {elapsed:.3f}s -- debería haber cortado sobre los ~50ms del deadline"

        assert len(items) == 1  # cero chunks de texto, solo el SynthesisAttempt terminal
        terminal = items[0]
        assert terminal.state != "complete"
        assert terminal.state == "timeout"
        assert terminal.content == ""

    def test_no_se_persiste_ni_firma_contenido_tras_timeout_de_apertura(self):
        """Round-trip HTTP real: el mismo escenario, verificando que el
        decreto persistido/firmado no contiene ni un carácter de una
        síntesis que nunca llegó a abrirse."""
        _test_db = os.path.join(tempfile.gettempdir(), f"enlil_delta2_open_{uuid.uuid4().hex}.db")
        try:
            import enlil.auth as auth_module
            from enlil.auth import init_auth_tables, create_client
            from enlil.orchestrator import Orchestrator

            auth_module.DB_PATH = _test_db
            init_auth_tables()
            client_info = create_client(name="Delta2 Open Test", email=f"d2-{uuid.uuid4().hex}@test.invalid")

            async def _fake_convene_stream(*args, **kwargs):
                yield _voice()

            async def slow_create(**kwargs):
                await asyncio.sleep(0.15)
                return MagicMock()

            with patch("openai.AsyncOpenAI"):
                from fastapi.testclient import TestClient
                import api as api_module
                with TestClient(api_module.app) as c:
                    orch = Orchestrator(db_path=_test_db)
                    api_module.enlil = orch
                    with patch.object(orch.council, "convene_stream", new=_fake_convene_stream), \
                         patch("enlil.orchestrator._total_budget_seconds", return_value=0.05):
                        orch.council._anthropic_client = None
                        orch.council._client = MagicMock()
                        orch.council._client.chat.completions.create = AsyncMock(side_effect=slow_create)
                        r = c.post(
                            "/query/stream",
                            json={"query": "consulta de prueba suficientemente larga para tier full quizas"},
                            headers={"X-Api-Key": client_info["api_key"]},
                        )
            assert r.status_code == 200
            events = []
            for line in r.text.splitlines():
                if line.startswith("data: "):
                    events.append(json.loads(line[len("data: "):]))
            syn_tokens = [e for e in events if e["type"] == "synthesis_token"]
            assert syn_tokens == [], "no debe haberse emitido ningún token -- la apertura nunca terminó a tiempo"
            done = [e for e in events if e["type"] == "done"][0]
            decree = orch.store.get(done["decree_id"])
            assert decree.synthesis == ""
            assert decree.status == "failed"
            if decree.pq_signature:
                from enlil.quantum import verify_decree
                assert verify_decree(
                    decree.id, decree.query, decree.synthesis, decree.timestamp, decree.pq_signature,
                    payload_version=decree.signature_payload_version, status=decree.status,
                ) is True
        finally:
            try:
                os.remove(_test_db)
                for ext in ("-wal", "-shm"):
                    if os.path.exists(_test_db + ext):
                        os.remove(_test_db + ext)
            except OSError:
                pass


# ── 2. deadline keyword-only obligatorio -- firmas, no asserts ──────────

def _no_deadline_kwarg_raises_typeerror(coro_factory):
    with pytest.raises(TypeError):
        coro_factory()


class TestDeadlineEsObligatorioEnLaFirma:
    """Estas pruebas comprueban el CONTRATO (la firma de la función) --
    llamar sin `deadline` debe fallar en el momento de construir la
    llamada, con TypeError de Python, no depender de un assert en
    runtime (que desaparecería con `python -O`)."""

    def test_consult_god_with_retry_exige_deadline(self):
        council = _make_council()
        with pytest.raises(TypeError):
            council._consult_god_with_retry("MOCK_GOD", "q", "")  # sin deadline

    def test_convene_exige_deadline(self):
        council = _make_council()
        with pytest.raises(TypeError):
            council.convene(["MOCK_GOD"], "q")  # sin deadline

    def test_synthesize_exige_deadline(self):
        council = _make_council()
        with pytest.raises(TypeError):
            council.synthesize([_voice()], "q")  # sin deadline

    def test_convene_stream_exige_deadline(self):
        council = _make_council()
        with pytest.raises(TypeError):
            council.convene_stream(["MOCK_GOD"], "q")  # sin deadline

    def test_synthesize_stream_exige_deadline(self):
        council = _make_council()
        with pytest.raises(TypeError):
            council.synthesize_stream([_voice()], "q")  # sin deadline

    def test_peer_review_stream_exige_deadline(self):
        council = _make_council()
        with pytest.raises(TypeError):
            council.peer_review_stream([_voice()], "q")  # sin deadline

    @pytest.mark.parametrize("method_name", [
        "_consult_god_with_retry", "convene", "synthesize",
        "convene_stream", "synthesize_stream", "peer_review_stream",
    ])
    def test_deadline_es_keyword_only_sin_default_en_la_firma(self, method_name):
        """Verificación directa de la firma con inspect -- no hay
        `= None` en ningún sitio, y el parámetro es KEYWORD_ONLY."""
        method = getattr(Council, method_name)
        sig = inspect.signature(method)
        param = sig.parameters["deadline"]
        assert param.default is inspect.Parameter.empty, (
            f"{method_name}.deadline todavía tiene un valor por defecto: {param.default!r}"
        )
        assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
            f"{method_name}.deadline debería ser keyword-only, es {param.kind}"
        )

    def test_ningun_assert_deadline_is_not_none_en_council(self):
        """Verificación anti-regresión literal: el patrón `assert
        deadline is not None` (que desaparece con python -O) no debe
        aparecer en ningún sitio del fichero."""
        import enlil.council as council_module
        source = inspect.getsource(council_module)
        assert "assert deadline is not None" not in source
