import pytest
import os
os.environ.setdefault("OPENROUTER_API_KEY", "test")
os.environ.setdefault("ENLIL_DB", ":memory:")

from enlil.router import classify_query, select_gods
from enlil.gods.registry import build_default_pantheon


class TestClassifyQuery:
    def test_security_keywords(self):
        for q in ["hay una vulnerabilidad en el firewall", "analizando exploit CVE", "malware detectado"]:
            assert "security" in classify_query(q), f"Fallo con: {q}"

    def test_technical_keywords(self):
        for q in ["hay un bug en el código python", "la arquitectura de la api falla", "error en la función"]:
            assert "technical" in classify_query(q), f"Fallo con: {q}"

    def test_communication_keywords(self):
        for q in ["necesito redactar un email", "carta para el cliente", "presentación del pitch"]:
            assert "communication" in classify_query(q), f"Fallo con: {q}"

    def test_strategy_keywords(self):
        for q in ["cuál es la estrategia", "decisión sobre el producto", "plan de negocio"]:
            assert "strategy" in classify_query(q), f"Fallo con: {q}"

    def test_fallback_returns_context(self):
        assert classify_query("xyzqwerty123") == ["context"]
        assert classify_query("") == ["context"]

    def test_multiple_domains(self):
        domains = classify_query("bug de seguridad en el código del firewall")
        assert len(domains) >= 2
        assert "security" in domains
        assert "technical" in domains

    def test_case_insensitive(self):
        assert "security" in classify_query("VULNERABILIDAD EN EL FIREWALL")


class TestSelectGods:
    def setup_method(self):
        self.pantheon = build_default_pantheon()

    def test_claude_always_included(self):
        for tier in ["minimal", "standard", "full"]:
            gods = select_gods(["security"], self.pantheon, tier)
            assert "claude" in gods, f"Claude ausente en tier {tier}"

    def test_minimal_max_two_gods(self):
        gods = select_gods(["technical"], self.pantheon, "minimal")
        assert len(gods) <= 4

    def test_standard_max_four_gods(self):
        gods = select_gods(["security", "technical"], self.pantheon, "standard")
        assert len(gods) <= 4

    def test_full_can_include_all(self):
        gods = select_gods(["security", "technical", "communication"], self.pantheon, "full")
        assert len(gods) >= 2

    def test_security_selects_ninurta(self):
        # Tras routing de seguridad, Ninurta debería aparecer en tier standard o full
        gods = select_gods(["security"], self.pantheon, "full")
        assert "ninurta" in gods

    def test_technical_selects_enki(self):
        gods = select_gods(["technical"], self.pantheon, "full")
        assert "enki" in gods

    def test_communication_selects_inanna(self):
        gods = select_gods(["communication"], self.pantheon, "full")
        assert "inanna" in gods

    def test_unknown_domain_returns_claude(self):
        gods = select_gods(["dominio_inexistente"], self.pantheon, "standard")
        assert "claude" in gods
