import os
os.environ.setdefault("OPENROUTER_API_KEY", "test")
os.environ.setdefault("ENLIL_DB", ":memory:")

from enlil.memory import MemoryStore
from enlil.decrees.decree import Decree, GodVoice


def make_decree(query: str, synthesis: str, domains: list[str] = None) -> Decree:
    return Decree(
        query=query,
        domains=domains or ["technical"],
        gods_convened=["claude"],
        voices=[],
        synthesis=synthesis,
        total_tokens=100,
        budget_tier="minimal",
    )


class TestMemoryStore:
    def setup_method(self):
        self.mem = MemoryStore(":memory:")

    def test_store_and_search_basic(self):
        d = make_decree(
            "como configurar el firewall para bloquear ataques",
            "Usar reglas de ingress estrictas y activar rate limiting."
        )
        self.mem.store(d)
        result = self.mem.search("firewall bloquear")
        assert isinstance(result, str)

    def test_empty_db_returns_empty_string(self):
        result = self.mem.search("cualquier cosa")
        assert result == ""

    def test_no_matching_results_returns_empty(self):
        d = make_decree("trading NEXUS Bitcoin", "Estrategia de compra basada en RSI.")
        self.mem.store(d)
        result = self.mem.search("xyzqwerty123")
        assert result == ""

    def test_multiple_decrees_stored(self):
        for i in range(5):
            self.mem.store(make_decree(f"consulta numero {i} sobre seguridad firewall", f"Sintesis {i}"))
        result = self.mem.search("seguridad firewall")
        assert isinstance(result, str)

    def test_duplicate_ignored(self):
        d = make_decree("consulta unica", "sintesis unica")
        self.mem.store(d)
        self.mem.store(d)  # duplicado — no debe explotar
        result = self.mem.search("consulta")
        assert isinstance(result, str)

    def test_search_limit_respected(self):
        for i in range(10):
            self.mem.store(make_decree(f"seguridad firewall vulnerabilidad {i}", f"Sintesis {i}"))
        result = self.mem.search("firewall seguridad", limit=2)
        # Resultado tiene máximo 2 entradas (separadas por newline de "- Consulta:")
        if result:
            entries = result.count("- Consulta:")
            assert entries <= 2

    def test_never_raises_exception(self):
        # La memoria nunca debe romper el flujo principal
        for q in ["", "   ", "a" * 1000, "!@#$%^&*()"]:
            try:
                self.mem.search(q)
            except Exception as e:
                assert False, f"Excepcion con query '{q[:20]}': {e}"
