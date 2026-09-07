import os
import pytest
from enlil.council import Council, EnlilDisabledError, _enlil_enabled


def test_absent_env_is_disabled(monkeypatch):
    monkeypatch.delenv('ENLIL_ENABLED', raising=False)
    assert _enlil_enabled() is False


@pytest.mark.parametrize('val', ['false', '0', 'off', 'no', 'garbage', ''])
def test_falsy_values_disabled(monkeypatch, val):
    monkeypatch.setenv('ENLIL_ENABLED', val)
    assert _enlil_enabled() is False


@pytest.mark.parametrize('val', ['true', '1', 'on', 'TRUE', 'On'])
def test_truthy_values_enabled(monkeypatch, val):
    monkeypatch.setenv('ENLIL_ENABLED', val)
    assert _enlil_enabled() is True


@pytest.mark.asyncio
async def test_consult_god_blocks_when_disabled(monkeypatch):
    monkeypatch.delenv('ENLIL_ENABLED', raising=False)
    council = Council.__new__(Council)
    with pytest.raises(EnlilDisabledError):
        await Council.consult_god(council, 'marduk', 'query de prueba')
