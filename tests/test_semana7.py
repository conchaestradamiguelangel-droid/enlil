"""Tests ENLIL Semana 7 — Criptografía Post-Cuántica en Decretos."""
import pytest
import time
from unittest.mock import patch, MagicMock
from enlil.decrees.decree import Decree, GodVoice
from enlil.decrees.store import DecreeStore
from enlil.quantum import sign_decree, verify_decree, is_available, public_key_b64


# --- Tests quantum.py ---

def test_quantum_is_available_returns_bool():
    result = is_available()
    assert isinstance(result, bool)


def test_sign_decree_returns_string():
    sig = sign_decree("test-id", "query test", "synthesis test", 1234567890.0)
    assert isinstance(sig, str)


def test_sign_decree_nonempty_when_pq_available():
    if not is_available():
        pytest.skip("oqs no disponible en este entorno")
    sig = sign_decree("test-id", "query", "synthesis", 1234567890.0)
    assert len(sig) > 0


def test_verify_decree_valid_signature():
    if not is_available():
        pytest.skip("oqs no disponible en este entorno")
    sig = sign_decree("abc", "mi consulta", "mi síntesis", 9999.0)
    assert verify_decree("abc", "mi consulta", "mi síntesis", 9999.0, sig) is True


def test_verify_decree_invalid_signature():
    if not is_available():
        pytest.skip("oqs no disponible en este entorno")
    assert verify_decree("abc", "query", "synthesis", 9999.0, "firma_falsa_xxx") is False


def test_verify_decree_tampered_synthesis():
    if not is_available():
        pytest.skip("oqs no disponible en este entorno")
    sig = sign_decree("abc", "query", "synthesis original", 9999.0)
    assert verify_decree("abc", "query", "synthesis MANIPULADO", 9999.0, sig) is False


def test_verify_decree_empty_signature_returns_false():
    assert verify_decree("abc", "query", "synthesis", 9999.0, "") is False


def test_public_key_b64_returns_string():
    result = public_key_b64()
    assert isinstance(result, str)


def test_public_key_nonempty_when_pq_available():
    if not is_available():
        pytest.skip("oqs no disponible en este entorno")
    assert len(public_key_b64()) > 0


# --- Tests store.py con firma PQ ---

def _make_decree(query="consulta test", synthesis="síntesis test") -> Decree:
    return Decree(
        query=query,
        synthesis=synthesis,
        domains=["technical"],
        gods_convened=["claude"],
        voices=[GodVoice("claude", "claude-sonnet-4-6", "respuesta", 100, 500.0)],
        total_tokens=100,
        budget_tier="standard",
    )


def test_store_save_adds_pq_signature():
    store = DecreeStore(db_path=":memory:")
    decree = _make_decree()
    store.save(decree)
    retrieved = store.get(decree.id)
    assert retrieved is not None
    if is_available():
        assert retrieved.pq_signature is not None
        assert len(retrieved.pq_signature) > 0


def test_store_verify_valid_decree():
    if not is_available():
        pytest.skip("oqs no disponible en este entorno")
    store = DecreeStore(db_path=":memory:")
    decree = _make_decree()
    store.save(decree)
    result = store.verify(decree.id)
    assert result["valid"] is True
    assert result["algorithm"] == "ML-DSA-87"


def test_store_verify_nonexistent_decree():
    store = DecreeStore(db_path=":memory:")
    result = store.verify("id-inexistente")
    assert result["valid"] is False
    assert "no encontrado" in result["reason"]


def test_store_verify_decree_without_signature():
    store = DecreeStore(db_path=":memory:")
    decree = _make_decree()
    with patch("enlil.decrees.store.sign_decree", return_value=""):
        store.save(decree)
    result = store.verify(decree.id)
    assert result["valid"] is False


def test_decree_pq_signature_field_exists():
    d = Decree()
    assert hasattr(d, "pq_signature")
    assert d.pq_signature is None


def test_store_recent_includes_pq_signature():
    if not is_available():
        pytest.skip("oqs no disponible en este entorno")
    store = DecreeStore(db_path=":memory:")
    store.save(_make_decree("q1", "s1"))
    store.save(_make_decree("q2", "s2"))
    recents = store.recent(limit=2)
    assert all(d.pq_signature is not None for d in recents)


def test_different_decrees_have_different_signatures():
    if not is_available():
        pytest.skip("oqs no disponible en este entorno")
    store = DecreeStore(db_path=":memory:")
    d1 = _make_decree("query uno", "synthesis uno")
    d2 = _make_decree("query dos", "synthesis dos")
    store.save(d1)
    store.save(d2)
    r1 = store.get(d1.id)
    r2 = store.get(d2.id)
    assert r1.pq_signature != r2.pq_signature
