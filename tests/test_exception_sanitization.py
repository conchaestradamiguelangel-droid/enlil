"""TEST 01B — ninguna excepción Python cruda llega al JSON persistido
(ENLIL_TEST01B_AUDITORIA_DISENO_V4.md §6)."""
import asyncio
import json
import os
import time
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("OPENROUTER_API_KEY", "sk-or-test")

from enlil.council import Council
from enlil.gods.base import GodProfile
from enlil.decrees.store import DecreeStore
from enlil.decrees.decree import Decree, GodVoice


def _make_council():
    pantheon = {"MOCK_GOD": GodProfile(name="MOCK_GOD", model="test-model", role="mock", domains=["consulta"])}
    council = Council(pantheon=pantheon)
    council._anthropic_client = None
    return council


def test_attempt_result_nunca_contiene_baseexception():
    council = _make_council()

    class FakeProviderError(Exception):
        def __init__(self):
            super().__init__("mensaje interno del proveedor con detalle sensible xyz123")

    async def fake_create(**kwargs):
        raise FakeProviderError()

    council._client = MagicMock()
    council._client.chat.completions.create = AsyncMock(side_effect=fake_create)

    deadline = time.monotonic() + 300.0
    result = asyncio.run(council._consult_god_with_retry(
        "MOCK_GOD", "query", "", max_tokens=100, deadline=deadline,
    ))
    assert result.voice_status == "error"
    for attempt in result.attempts:
        assert attempt.exception_type == "FakeProviderError"
        assert not isinstance(attempt.exception_type, BaseException)
        # nunca se guarda el mensaje crudo de la excepción
        import dataclasses
        for field in dataclasses.fields(attempt):
            value = getattr(attempt, field.name)
            assert not isinstance(value, BaseException)


def test_save_no_falla_serializando_attempts_con_excepcion(tmp_path):
    """Antes de TEST 01B, un BaseException crudo en cualquier campo
    haría fallar json.dumps() con TypeError -- este test demuestra que
    ya no puede ocurrir."""
    council = _make_council()

    async def fake_create(**kwargs):
        raise ValueError("fallo simulado con datos sensibles: sk-or-abc123")

    council._client = MagicMock()
    council._client.chat.completions.create = AsyncMock(side_effect=fake_create)

    deadline = time.monotonic() + 300.0
    resp = asyncio.run(council._consult_god_with_retry(
        "MOCK_GOD", "query", "", max_tokens=100, deadline=deadline,
    ))

    voice = GodVoice(
        god_name=resp.god_name, model=resp.model, content=resp.content,
        tokens_used=resp.tokens_used, latency_ms=resp.latency_ms, dissent=resp.dissent,
        voice_status=resp.voice_status, finish_reason=resp.finish_reason,
        retry_count=resp.retry_count, returned_model=resp.returned_model,
        reasoning_tokens=resp.reasoning_tokens, usage_state=resp.usage_state,
        attempts=resp.attempts,
    )
    decree = Decree(
        query="q", domains=["technical"], gods_convened=["MOCK_GOD"],
        voices=[voice], synthesis="s", total_tokens=0, budget_tier="standard",
        status="failed", signature_payload_version=2,
    )
    db_path = str(tmp_path / "sanitize.db")
    store = DecreeStore(db_path=db_path)
    store.save(decree)  # no debe lanzar TypeError de serialización

    loaded = store.get(decree.id)
    assert loaded.voices[0].attempts[0].exception_type == "ValueError"
    # el mensaje crudo ("sk-or-abc123") no aparece en absoluto en ningún
    # campo persistido -- nunca se copió, no hay nada que sanear a posteriori.
    dumped = json.dumps([asdict(a) for a in loaded.voices[0].attempts])
    assert "sk-or-abc123" not in dumped
