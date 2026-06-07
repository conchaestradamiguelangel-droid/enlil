import os
os.environ.setdefault("OPENROUTER_API_KEY", "test")
os.environ.setdefault("ENLIL_DB", ":memory:")

from enlil.gods.registry import build_default_pantheon
from enlil.reputation import ReputationStore


class TestReputationStore:
    def setup_method(self):
        self.pantheon = build_default_pantheon()
        self.store = ReputationStore(":memory:")

    def test_initial_reputation_neutral(self):
        for god in self.pantheon.values():
            for domain in god.domains:
                assert god.get_reputation(domain) == 0.5

    def test_positive_feedback_increases_score(self):
        before = self.pantheon["ninurta"].get_reputation("security")
        self.store.record_feedback(["ninurta"], ["security"], useful=True, pantheon=self.pantheon)
        assert self.pantheon["ninurta"].get_reputation("security") > before

    def test_negative_feedback_decreases_score(self):
        # Primero subir el score
        for _ in range(5):
            self.store.record_feedback(["enki"], ["technical"], useful=True, pantheon=self.pantheon)
        high = self.pantheon["enki"].get_reputation("technical")
        self.store.record_feedback(["enki"], ["technical"], useful=False, pantheon=self.pantheon)
        assert self.pantheon["enki"].get_reputation("technical") < high

    def test_score_stays_bounded(self):
        for _ in range(50):
            self.store.record_feedback(["claude"], ["context"], useful=True, pantheon=self.pantheon)
        score = self.pantheon["claude"].get_reputation("context")
        assert 0.0 <= score <= 1.0

    def test_multiple_gods_updated(self):
        self.store.record_feedback(
            ["claude", "ninurta"], ["security"], useful=True, pantheon=self.pantheon
        )
        assert self.pantheon["claude"].get_reputation("security") != 0.5 or \
               self.pantheon["ninurta"].get_reputation("security") != 0.5

    def test_unknown_god_ignored(self):
        # No debe lanzar excepción
        self.store.record_feedback(["dios_inexistente"], ["security"], useful=True, pantheon=self.pantheon)

    def test_snapshot_structure(self):
        self.store.record_feedback(["enki"], ["technical"], useful=True, pantheon=self.pantheon)
        snap = self.store.snapshot()
        assert "enki" in snap
        assert "technical" in snap["enki"]
        assert "score" in snap["enki"]["technical"]
        assert "evaluations" in snap["enki"]["technical"]

    def test_evaluations_counter_increments(self):
        self.store.record_feedback(["ninurta"], ["security"], useful=True, pantheon=self.pantheon)
        self.store.record_feedback(["ninurta"], ["security"], useful=False, pantheon=self.pantheon)
        snap = self.store.snapshot()
        assert snap["ninurta"]["security"]["evaluations"] == 2

    def test_load_into_restores_scores(self):
        import tempfile, os
        db = tempfile.mktemp(suffix=".db")
        try:
            p1 = build_default_pantheon()
            s1 = ReputationStore(db)
            s1.record_feedback(["enki"], ["technical"], useful=True, pantheon=p1)
            saved_score = p1["enki"].get_reputation("technical")

            p2 = build_default_pantheon()
            s2 = ReputationStore(db)
            s2.load_into(p2)
            assert p2["enki"].get_reputation("technical") == saved_score
        finally:
            try: os.remove(db)
            except: pass
