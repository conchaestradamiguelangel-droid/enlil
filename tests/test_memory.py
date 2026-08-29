import os
os.environ.setdefault("OPENROUTER_API_KEY", "test")
os.environ.setdefault("ENLIL_DB", ":memory:")

from enlil.memory import MemoryStore
from enlil.decrees.decree import Decree, GodVoice


def make_decree(query: str, synthesis: str, domains: list[str] = None, client_id: str = "default") -> Decree:
    return Decree(
        query=query,
        domains=domains or ["technical"],
        gods_convened=["claude"],
        voices=[],
        synthesis=synthesis,
        total_tokens=100,
        budget_tier="minimal",
        client_id=client_id,
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
        result = self.mem.search("firewall bloquear", client_id="default")
        assert isinstance(result, str)

    def test_empty_db_returns_empty_string(self):
        result = self.mem.search("cualquier cosa", client_id="default")
        assert result == ""

    def test_no_matching_results_returns_empty(self):
        d = make_decree("trading NEXUS Bitcoin", "Estrategia de compra basada en RSI.")
        self.mem.store(d)
        result = self.mem.search("xyzqwerty123", client_id="default")
        assert result == ""

    def test_multiple_decrees_stored(self):
        for i in range(5):
            self.mem.store(make_decree(f"consulta numero {i} sobre seguridad firewall", f"Sintesis {i}"))
        result = self.mem.search("seguridad firewall", client_id="default")
        assert isinstance(result, str)

    def test_duplicate_ignored(self):
        d = make_decree("consulta unica", "sintesis unica")
        self.mem.store(d)
        self.mem.store(d)  # duplicado — no debe explotar
        result = self.mem.search("consulta", client_id="default")
        assert isinstance(result, str)

    def test_search_limit_respected(self):
        for i in range(10):
            self.mem.store(make_decree(f"seguridad firewall vulnerabilidad {i}", f"Sintesis {i}"))
        result = self.mem.search("firewall seguridad", limit=2, client_id="default")
        # Resultado tiene máximo 2 entradas (separadas por newline de "- Consulta:")
        if result:
            entries = result.count("- Consulta:")
            assert entries <= 2

    def test_never_raises_exception(self):
        # La memoria nunca debe romper el flujo principal
        for q in ["", "   ", "a" * 1000, "!@#$%^&*()"]:
            try:
                self.mem.search(q, client_id="default")
            except Exception as e:
                assert False, f"Excepcion con query '{q[:20]}': {e}"

    def test_sin_client_id_devuelve_vacio(self):
        """Fix P0 2026-08-29: sin client_id, fallar cerrado (nunca buscar)."""
        d = make_decree("consulta con marcador", "sintesis con marcador")
        self.mem.store(d)
        assert self.mem.search("marcador") == ""
        assert self.mem.search("marcador", client_id="") == ""
        assert self.mem.search("marcador", client_id=None) == ""

    def test_aislamiento_entre_clientes(self):
        """Fix P0 2026-08-29: A no recupera memoria de B ni memoria legacy."""
        self.mem.store(make_decree("secreto de B sobre fusiones", "sintesis B", client_id="cliente-b"))
        self.mem.store(make_decree("dato legacy sin dueno", "sintesis legacy"))  # client_id="default"
        result_a = self.mem.search("secreto fusiones", client_id="cliente-a")
        assert "secreto" not in result_a and result_a == ""
        result_a_legacy = self.mem.search("dato legacy dueno", client_id="cliente-a")
        assert result_a_legacy == ""
        result_b = self.mem.search("secreto fusiones", client_id="cliente-b")
        assert "secreto" in result_b
