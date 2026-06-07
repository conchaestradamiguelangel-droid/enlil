import os
os.environ.setdefault("OPENROUTER_API_KEY", "test")
os.environ.setdefault("ENLIL_DB", ":memory:")

import time
import pytest
from enlil.decrees.decree import Decree, GodVoice
from enlil.decrees.store import DecreeStore


def make_decree(**kwargs) -> Decree:
    defaults = dict(
        query="consulta de prueba",
        domains=["technical"],
        gods_convened=["claude", "enki"],
        voices=[
            GodVoice("claude", "claude-sonnet", "respuesta contexto", 100, 200.0),
            GodVoice("enki", "gpt-4o", "respuesta tecnica", 120, 250.0),
        ],
        synthesis="Sintesis del Consejo.",
        total_tokens=220,
        budget_tier="standard",
    )
    defaults.update(kwargs)
    return Decree(**defaults)


class TestDecree:
    def test_unique_ids(self):
        d1, d2 = make_decree(), make_decree()
        assert d1.id != d2.id

    def test_no_dissent_default(self):
        d = make_decree()
        assert not d.has_dissent()
        assert d.dissenting_gods() == []

    def test_dissent_detected(self):
        d = make_decree(voices=[
            GodVoice("claude", "m", "ok", 100, 200.0),
            GodVoice("enki", "m", "ok", 100, 200.0, dissent="No estoy de acuerdo"),
        ])
        assert d.has_dissent()
        assert "enki" in d.dissenting_gods()

    def test_multiple_dissenters(self):
        d = make_decree(voices=[
            GodVoice("claude", "m", "ok", 100, 200.0, dissent="Disiento"),
            GodVoice("enki", "m", "ok", 100, 200.0, dissent="Tambien disiento"),
        ])
        assert len(d.dissenting_gods()) == 2

    def test_genealogy_parent(self):
        parent = make_decree()
        child = make_decree(parent_decree_id=parent.id)
        assert child.parent_decree_id == parent.id

    def test_timestamp_auto(self):
        before = time.time()
        d = make_decree()
        after = time.time()
        assert before <= d.timestamp <= after


class TestDecreeStore:
    def setup_method(self):
        self.store = DecreeStore(":memory:")

    def test_save_and_get(self):
        d = make_decree()
        self.store.save(d)
        r = self.store.get(d.id)
        assert r is not None
        assert r.id == d.id
        assert r.query == d.query
        assert r.synthesis == d.synthesis

    def test_get_nonexistent_returns_none(self):
        assert self.store.get("id-que-no-existe") is None

    def test_recent_order(self):
        d1 = make_decree(query="primera")
        time.sleep(0.01)
        d2 = make_decree(query="segunda")
        self.store.save(d1)
        self.store.save(d2)
        recent = self.store.recent(10)
        assert recent[0].query == "segunda"

    def test_recent_limit_respected(self):
        for i in range(10):
            self.store.save(make_decree(query=f"q{i}"))
        assert len(self.store.recent(5)) == 5

    def test_dissent_persists(self):
        d = make_decree(voices=[
            GodVoice("claude", "m", "ok", 100, 200.0),
            GodVoice("enki", "m", "ok", 100, 200.0, dissent="Disiento"),
        ])
        self.store.save(d)
        r = self.store.get(d.id)
        assert r.has_dissent()
        assert "enki" in r.dissenting_gods()

    def test_domains_persist(self):
        d = make_decree(domains=["security", "technical"])
        self.store.save(d)
        r = self.store.get(d.id)
        assert set(r.domains) == {"security", "technical"}

    def test_genealogy_persists(self):
        parent = make_decree()
        child = make_decree(parent_decree_id=parent.id)
        self.store.save(parent)
        self.store.save(child)
        r = self.store.get(child.id)
        assert r.parent_decree_id == parent.id

    def test_all_voices_persist(self):
        d = make_decree()
        self.store.save(d)
        r = self.store.get(d.id)
        assert len(r.voices) == len(d.voices)
        assert r.voices[0].god_name == "claude"
        assert r.voices[1].god_name == "enki"
