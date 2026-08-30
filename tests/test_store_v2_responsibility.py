"""TEST 01B — DecreeStore.save() nunca asigna/corrige V2, solo exige y
rechaza; Orchestrator es quien decide (ENLIL_TEST01B_AUDITORIA_DISENO_V4.md §8).
Y round-trip real de synthesis_attempts/accounting (V6 §2.4)."""
import pytest

from enlil.decrees.store import DecreeStore
from enlil.decrees.decree import Decree, GodVoice
from enlil.reliability import SynthesisAttempt


def _decree(**overrides):
    defaults = dict(
        query="q", domains=["technical"], gods_convened=["claude"],
        voices=[GodVoice("claude", "claude-sonnet", "respuesta", 10, 50.0)],
        synthesis="s", total_tokens=10, budget_tier="standard",
    )
    defaults.update(overrides)
    return Decree(**defaults)


class TestSaveExigeNuncaAsigna:
    def test_save_rechaza_version_none(self):
        store = DecreeStore(db_path=":memory:")
        d = _decree(status="complete", signature_payload_version=None)
        with pytest.raises(ValueError):
            store.save(d)

    def test_save_rechaza_version_1_en_decreto_nuevo(self):
        store = DecreeStore(db_path=":memory:")
        d = _decree(status="complete", signature_payload_version=1)
        with pytest.raises(ValueError):
            store.save(d)

    def test_save_rechaza_status_invalido(self):
        store = DecreeStore(db_path=":memory:")
        d = _decree(status="bogus", signature_payload_version=2)
        with pytest.raises(ValueError):
            store.save(d)

    def test_save_rechaza_status_none(self):
        store = DecreeStore(db_path=":memory:")
        d = _decree(status=None, signature_payload_version=2)
        with pytest.raises(ValueError):
            store.save(d)

    def test_save_acepta_version_2_y_status_valido(self):
        store = DecreeStore(db_path=":memory:")
        d = _decree(status="complete", signature_payload_version=2)
        store.save(d)  # no debe lanzar
        assert d.pq_signature is not None or not __import__("enlil.quantum", fromlist=["is_available"]).is_available()

    def test_save_fallido_no_deja_fila_a_medias(self):
        """Si save() rechaza, no debe quedar ninguna fila insertada."""
        store = DecreeStore(db_path=":memory:")
        d = _decree(status="complete", signature_payload_version=None)
        with pytest.raises(ValueError):
            store.save(d)
        assert store.count() == 0


class TestRoundTripSynthesisAttempts:
    def test_roundtrip_con_cierre_y_reapertura_real(self, tmp_path):
        db_path = str(tmp_path / "roundtrip.db")
        sa1 = SynthesisAttempt(
            attempt_number=1, content="parcial", state="truncated",
            requested_model="claude-opus-5", finish_reason="length",
            total_tokens=100, usage_state="known", max_tokens_budget=6000, latency_ms=500.0,
        )
        sa2 = SynthesisAttempt(
            attempt_number=2, content="completo al fin", state="complete",
            requested_model="claude-opus-5", finish_reason="stop",
            total_tokens=200, usage_state="known", max_tokens_budget=9000, latency_ms=600.0,
        )
        d = _decree(
            synthesis="completo al fin",
            status="partial", signature_payload_version=2,
            accounting_state="known", known_token_subtotal=300, observed_total_tokens=300,
            synthesis_attempts=[sa1, sa2],
        )
        store = DecreeStore(db_path=db_path)
        store.save(d)
        store._connection.close()

        store2 = DecreeStore(db_path=db_path)
        loaded = store2.get(d.id)
        assert loaded is not None
        assert loaded.status == "partial"
        assert loaded.accounting_state == "known"
        assert loaded.known_token_subtotal == 300
        assert loaded.observed_total_tokens == 300
        assert loaded.synthesis_attempts is not None
        assert len(loaded.synthesis_attempts) == 2
        assert loaded.synthesis_attempts[0] == sa1
        assert loaded.synthesis_attempts[1] == sa2

    def test_historico_con_columnas_nuevas_null_no_revienta(self, tmp_path):
        db_path = str(tmp_path / "legacy.db")
        store = DecreeStore(db_path=db_path)
        store._connection.execute(
            "INSERT INTO decrees (id, timestamp, query, domains, gods_convened, voices, synthesis, "
            "total_tokens, budget_tier) VALUES ('legacy1', 0, 'q', '[]', '[]', '[]', 's', 0, 'standard')"
        )
        store._connection.commit()
        loaded = store.get("legacy1")
        assert loaded is not None
        assert loaded.status is None
        assert loaded.accounting_state is None
        assert loaded.known_token_subtotal is None
        assert loaded.observed_total_tokens is None
        assert loaded.synthesis_attempts is None
        assert loaded.signature_payload_version is None
