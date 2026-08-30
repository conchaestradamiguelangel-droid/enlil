"""Corrección post-auditoría Codex sobre 6486a31 -- tool_calls/function_call
deben detectarse en TODOS los adaptadores reales (voz normal, retry,
síntesis normal, síntesis streaming), no solo en classify_attempt()
aislado. Ninguna de estas combinaciones puede clasificar 'complete'."""
import asyncio
import os
import time
import pytest
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("OPENROUTER_API_KEY", "sk-or-test")

from enlil.council import Council
from enlil.gods.base import GodProfile, GodResponse


def _make_council():
    pantheon = {"MOCK_GOD": GodProfile(name="MOCK_GOD", model="test-model", role="mock", domains=["consulta"])}
    council = Council(pantheon=pantheon)
    council._anthropic_client = None
    return council


def _resp_with_function_call(content="texto con preambulo", finish_reason="stop"):
    """Adaptador legacy: campo message.function_call poblado, finish_reason
    puede seguir siendo 'stop' según el proveedor -- justo el caso que
    faltaba cubrir."""
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    resp.choices[0].message.refusal = None
    resp.choices[0].message.tool_calls = None
    resp.choices[0].message.function_call = MagicMock(name="alguna_funcion", arguments="{}")
    resp.choices[0].finish_reason = finish_reason
    resp.usage = MagicMock()
    resp.usage.total_tokens = 20
    resp.usage.prompt_tokens = 10
    resp.usage.completion_tokens = 10
    resp.usage.completion_tokens_details = None
    resp.model = "test-model"
    resp.id = "gen-fc"
    return resp


def _resp_with_tool_calls(content="texto", finish_reason="tool_calls"):
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    resp.choices[0].message.refusal = None
    resp.choices[0].message.tool_calls = [MagicMock()]
    resp.choices[0].message.function_call = None
    resp.choices[0].finish_reason = finish_reason
    resp.usage = MagicMock()
    resp.usage.total_tokens = 20
    resp.usage.prompt_tokens = 10
    resp.usage.completion_tokens = 10
    resp.usage.completion_tokens_details = None
    resp.model = "test-model"
    resp.id = "gen-tc"
    return resp


class TestVozNormalYRetry:
    def test_voz_con_texto_mas_function_call_y_stop_no_es_complete(self):
        council = _make_council()
        council._client = MagicMock()
        council._client.chat.completions.create = AsyncMock(return_value=_resp_with_function_call())

        deadline = time.monotonic() + 300.0
        result = asyncio.run(council._consult_god_with_retry(
            "MOCK_GOD", "query", "", max_tokens=100, deadline=deadline,
        ))
        assert result.voice_status != "complete"
        assert result.voice_status == "error"

    def test_voz_con_texto_mas_tool_calls(self):
        council = _make_council()
        council._client = MagicMock()
        council._client.chat.completions.create = AsyncMock(return_value=_resp_with_tool_calls())

        deadline = time.monotonic() + 300.0
        result = asyncio.run(council._consult_god_with_retry(
            "MOCK_GOD", "query", "", max_tokens=100, deadline=deadline,
        ))
        assert result.voice_status != "complete"
        assert result.voice_status == "error"

    def test_retry_tambien_detecta_tool_call(self):
        """El intento 1 sale 'empty'+length (retry-elegible), el intento 2
        (el retry) trae un tool_call -- debe seguir sin ser 'complete'."""
        council = _make_council()
        calls = []

        async def fake_create(**kwargs):
            calls.append(1)
            if len(calls) == 1:
                r = MagicMock()
                r.choices = [MagicMock()]
                r.choices[0].message.content = ""
                r.choices[0].message.refusal = None
                r.choices[0].message.tool_calls = None
                r.choices[0].message.function_call = None
                r.choices[0].finish_reason = "length"
                r.usage = MagicMock(total_tokens=10, prompt_tokens=5, completion_tokens=5, completion_tokens_details=None)
                r.model = "test-model"
                r.id = "g1"
                return r
            return _resp_with_tool_calls()

        council._client = MagicMock()
        council._client.chat.completions.create = AsyncMock(side_effect=fake_create)
        deadline = time.monotonic() + 300.0
        result = asyncio.run(council._consult_god_with_retry(
            "MOCK_GOD", "query", "", max_tokens=100, deadline=deadline,
        ))
        assert len(calls) == 2
        assert result.retry_count == 1
        assert result.voice_status != "complete"


class TestSintesisNormalYStreaming:
    def test_sintesis_no_streaming_con_tool_call_no_es_complete(self):
        council = _make_council()
        council._client = MagicMock()
        council._client.chat.completions.create = AsyncMock(return_value=_resp_with_tool_calls())

        voice = GodResponse(god_name="MOCK_GOD", model="m", content="voz", tokens_used=10,
                             latency_ms=1.0, voice_status="complete", finish_reason="stop")
        deadline = time.monotonic() + 300.0
        content, attempts = asyncio.run(council.synthesize([voice], "q", deadline=deadline))
        assert attempts[0].state != "complete"

    def test_sintesis_streaming_tool_call_en_finish_reason_final(self):
        council = _make_council()

        async def fake_stream():
            chunk1 = MagicMock()
            chunk1.id = "s1"
            chunk1.model = "claude-opus-5"
            chunk1.usage = None
            chunk1.choices = [MagicMock()]
            chunk1.choices[0].delta = MagicMock(content="parte de texto", tool_calls=None, function_call=None)
            chunk1.choices[0].finish_reason = None
            yield chunk1

            chunk2 = MagicMock()
            chunk2.id = "s1"
            chunk2.model = "claude-opus-5"
            chunk2.usage = None
            chunk2.choices = [MagicMock()]
            chunk2.choices[0].delta = MagicMock(content=None, tool_calls=[MagicMock()], function_call=None)
            chunk2.choices[0].finish_reason = "tool_calls"
            yield chunk2

        council._client = MagicMock()
        council._client.chat.completions.create = AsyncMock(return_value=fake_stream())

        voice = GodResponse(god_name="MOCK_GOD", model="m", content="voz", tokens_used=10,
                             latency_ms=1.0, voice_status="complete", finish_reason="stop")
        deadline = time.monotonic() + 300.0

        async def collect():
            items = []
            async for item in council.synthesize_stream([voice], "q", deadline=deadline):
                items.append(item)
            return items

        items = asyncio.run(collect())
        terminal = items[-1]
        assert terminal.state != "complete"
        assert terminal.content == "parte de texto"   # lo emitido == lo persistido, aunque termine en error
