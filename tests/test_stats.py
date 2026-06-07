import os
os.environ.setdefault("OPENROUTER_API_KEY", "test")
os.environ.setdefault("ENLIL_DB", ":memory:")

import time
import sqlite3
import pytest
from enlil.reputation import ReputationStore
from enlil.gods.base import GodProfile


def make_god(name):
    g = GodProfile(name=name, model="test", role="test", domains=["security"])
    return g


class TestReputationHistory:
    def setup_method(self):
        self.conn = sqlite3.connect(":memory:")
        self.rep = ReputationStore(connection=self.conn)
        self.pantheon = {"Claude": make_god("Claude"), "Ninurta": make_god("Ninurta")}

    def test_history_empty_at_start(self):
        assert self.rep.history() == []

    def test_history_records_after_feedback(self):
        self.rep.record_feedback(["Claude"], ["security"], True, self.pantheon)
        hist = self.rep.history()
        assert len(hist) >= 1

    def test_history_entry_has_required_fields(self):
        self.rep.record_feedback(["Claude"], ["security"], True, self.pantheon)
        hist = self.rep.history()
        entry = hist[0]
        assert "god_name" in entry and "domain" in entry
        assert "score" in entry and "timestamp" in entry

    def test_history_score_is_float(self):
        self.rep.record_feedback(["Claude"], ["security"], True, self.pantheon)
        hist = self.rep.history()
        assert isinstance(hist[0]["score"], float)

    def test_history_limit_respected(self):
        for _ in range(10):
            self.rep.record_feedback(["Claude"], ["security"], True, self.pantheon)
        assert len(self.rep.history(limit=3)) <= 3

    def test_history_ordered_most_recent_first(self):
        for _ in range(3):
            self.rep.record_feedback(["Claude"], ["security"], True, self.pantheon)
            time.sleep(0.01)
        hist = self.rep.history()
        timestamps = [h["timestamp"] for h in hist]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_multiple_gods_tracked(self):
        self.rep.record_feedback(["Claude"], ["security"], True, self.pantheon)
        self.rep.record_feedback(["Ninurta"], ["security"], False, self.pantheon)
        hist = self.rep.history()
        gods = {h["god_name"] for h in hist}
        assert "Claude" in gods and "Ninurta" in gods


class TestStatsEndpoint:
    """Tests de estructura del endpoint /stats (sin servidor real)."""

    def test_stats_returns_required_keys(self):
        conn = sqlite3.connect(":memory:")
        rep = ReputationStore(connection=conn)

        result = {
            "reputation_history": rep.history(200),
            "token_trend": [],
            "latency_avg": {},
            "domain_distribution": {},
        }
        assert "reputation_history" in result
        assert "token_trend" in result
        assert "latency_avg" in result
        assert "domain_distribution" in result

    def test_token_trend_structure(self):
        from enlil.decrees.decree import Decree
        recent = [Decree(query="test", synthesis="resp", total_tokens=500, budget_tier="standard")]
        token_trend = [
            {"timestamp": d.timestamp, "tokens": d.total_tokens, "tier": d.budget_tier}
            for d in recent
        ]
        assert token_trend[0]["tokens"] == 500
        assert "timestamp" in token_trend[0]
        assert "tier" in token_trend[0]
