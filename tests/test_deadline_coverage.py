"""Corrección post-auditoría Codex sobre 6486a31 -- el deadline global no
cubría realmente todas las llamadas externas (Lector, primer intento de
voz, primer intento de síntesis, apertura de synthesize_stream, peer
review). Ninguna llamada externa puede sobrevivir al deadline global."""
import asyncio
import os
import time
import pytest
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("OPENROUTER_API_KEY", "sk-or-test")

from enlil.council import Council
from enlil.gods.base import GodProfile


def _make_council(names=("MOCK_GOD",)):
    pantheon = {n: GodProfile(name=n, model="test-model", role="mock", domains=["consulta"]) for n in names}
    council = Council(pantheon=pantheon)
    council._anthropic_client = None
    return council


def _resp(content="ok", finish_reason="stop"):
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    resp.choices[0].message.refusal = None
    resp.choices[0].message.tool_calls = None
    resp.choices[0].message.function_call = None
    resp.choices[0].finish_reason = finish_reason
    resp.usage = MagicMock()
    resp.usage.total_tokens = 10
    resp.usage.prompt_tokens = 5
    resp.usage.completion_tokens = 5
    resp.usage.completion_tokens_details = None
    resp.model = "test-model"
    resp.id = "gen-1"
    return resp


_EXPIRED = -1.0  # deadline ya pasado, cualquier `deadline=time.monotonic()+_EXPIRED` queda en el pasado


class TestDeadlineExpiraAntesDelPrimerIntentoDeVoz:
    def test_sin_margen_no_se_llama_a_la_api(self):
        council = _make_council()
        council._client = MagicMock()
        council._client.chat.completions.create = AsyncMock(return_value=_resp())

        deadline = time.monotonic() + _EXPIRED
        result = asyncio.run(council._consult_god_with_retry(
            "MOCK_GOD", "query", "", max_tokens=100, deadline=deadline,
        ))
        council._client.chat.completions.create.assert_not_called()
        assert result.voice_status == "timeout"


class TestDeadlineExpiraDuranteLector:
    def test_lector_no_llama_a_la_api_sin_margen(self):
        council = _make_council()
        council._client = MagicMock()
        council._client.chat.completions.create = AsyncMock(return_value=_resp())

        deadline = time.monotonic() + _EXPIRED
        digest = asyncio.run(council._lector_digest("texto largo" * 100, "query", deadline))
        council._client.chat.completions.create.assert_not_called()
        assert digest == ""

    def test_convene_con_documento_grande_y_deadline_agotado_no_llama_lector(self):
        """El Lector se activa dentro de convene() para docs grandes --
        si el deadline ya expiró, ni siquiera debe intentarlo."""
        council = _make_council()
        council._client = MagicMock()
        council._client.chat.completions.create = AsyncMock(return_value=_resp())

        from enlil.council import LECTOR_THRESHOLD
        big_doc = "x" * (LECTOR_THRESHOLD + 1000)
        deadline = time.monotonic() + _EXPIRED
        results = asyncio.run(council.convene(["MOCK_GOD"], "query", big_doc, deadline=deadline))
        # Ni el Lector ni la voz deben haber llamado a la API real.
        council._client.chat.completions.create.assert_not_called()
        assert results[0].voice_status == "timeout"


class TestDeadlineExpiraAntesDeSintesis:
    def test_synthesize_no_streaming_no_llama_a_la_api(self):
        council = _make_council()
        council._client = MagicMock()
        council._client.chat.completions.create = AsyncMock(return_value=_resp())

        from enlil.gods.base import GodResponse
        voice = GodResponse(god_name="MOCK_GOD", model="m", content="voz", tokens_used=10,
                             latency_ms=1.0, voice_status="complete", finish_reason="stop")
        deadline = time.monotonic() + _EXPIRED
        content, attempts = asyncio.run(council.synthesize([voice], "q", deadline=deadline))
        council._client.chat.completions.create.assert_not_called()
        assert attempts[0].state == "timeout"

    def test_synthesize_stream_no_abre_el_stream(self):
        council = _make_council()
        council._client = MagicMock()
        council._client.chat.completions.create = AsyncMock()

        from enlil.gods.base import GodResponse

        async def collect():
            voice = GodResponse(god_name="MOCK_GOD", model="m", content="voz", tokens_used=10,
                                 latency_ms=1.0, voice_status="complete", finish_reason="stop")
            deadline = time.monotonic() + _EXPIRED
            items = []
            async for item in council.synthesize_stream([voice], "q", deadline=deadline):
                items.append(item)
            return items

        items = asyncio.run(collect())
        council._client.chat.completions.create.assert_not_called()
        assert len(items) == 1  # solo el SynthesisAttempt terminal, CERO chunks de texto
        assert items[0].state == "timeout"


class TestDeadlineExpiraDurantePeerReview:
    def test_peer_review_no_llama_si_no_hay_margen(self):
        council = _make_council()
        council._client = MagicMock()
        council._client.chat.completions.create = AsyncMock(return_value=_resp())

        from enlil.gods.base import GodResponse

        async def collect():
            responses = [GodResponse(god_name="MOCK_GOD", model="m", content="voz", tokens_used=10, latency_ms=1.0)]
            deadline = time.monotonic() + _EXPIRED
            items = []
            async for item in council.peer_review_stream(responses, "query", deadline=deadline):
                items.append(item)
            return items

        items = asyncio.run(collect())
        council._client.chat.completions.create.assert_not_called()
        assert len(items) == 1
        assert items[0].content == ""

    def test_peer_review_deadline_es_obligatorio(self):
        """V3-corrección #2: ya no existe el camino deadline=None."""
        import inspect
        sig = inspect.signature(council_cls_deadline_param())
        assert sig.parameters["deadline"].default is inspect.Parameter.empty


def council_cls_deadline_param():
    from enlil.council import Council
    return Council.peer_review_stream
