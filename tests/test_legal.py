import os
os.environ.setdefault("OPENROUTER_API_KEY", "test")
os.environ.setdefault("ENLIL_DB", ":memory:")

import pytest
from enlil.verticals.legal import (
    LegalDocument, LegalDecreeContext, parse_legal_request,
    build_legal_query, LEGAL_GOD_OVERRIDES, _VALID_DOC_TYPES
)


class TestLegalDocument:
    def test_parse_minimal_payload(self):
        doc = parse_legal_request({"text": "Este es el contrato."})
        assert doc.text == "Este es el contrato."
        assert doc.doc_type == "otro"
        assert doc.jurisdiction == "España"

    def test_parse_valid_doc_types(self):
        for dt in _VALID_DOC_TYPES:
            doc = parse_legal_request({"type": dt, "text": "texto"})
            assert doc.doc_type == dt

    def test_parse_invalid_type_defaults_to_otro(self):
        doc = parse_legal_request({"type": "xyz_invalid", "text": "texto"})
        assert doc.doc_type == "otro"

    def test_parse_empty_text_raises(self):
        with pytest.raises(ValueError):
            parse_legal_request({"text": ""})

    def test_parse_missing_text_raises(self):
        with pytest.raises(ValueError):
            parse_legal_request({})

    def test_parse_parties_list(self):
        doc = parse_legal_request({"text": "doc", "parties": ["Empresa A", "Empresa B"]})
        assert "Empresa A" in doc.parties

    def test_parse_jurisdiction(self):
        doc = parse_legal_request({"text": "doc", "jurisdiction": "México"})
        assert doc.jurisdiction == "México"

    def test_parse_text_truncated_at_5000(self):
        long_text = "x" * 6000
        doc = parse_legal_request({"text": long_text})
        assert len(doc.text) == 5000

    def test_parse_invalid_parties_type_ignored(self):
        doc = parse_legal_request({"text": "doc", "parties": "no es lista"})
        assert doc.parties == []


class TestLegalDecreeContext:
    def setup_method(self):
        self.doc = LegalDocument(
            doc_type="contrato", text="Texto del contrato.",
            jurisdiction="España", parties=["Parte A", "Parte B"]
        )
        self.ctx = LegalDecreeContext(document=self.doc)

    def test_to_query_includes_doc_type(self):
        assert "contrato" in self.ctx.to_query()

    def test_to_query_includes_jurisdiction(self):
        assert "España" in self.ctx.to_query()

    def test_to_query_includes_parties(self):
        q = self.ctx.to_query()
        assert "Parte A" in q

    def test_to_query_includes_text_truncated(self):
        assert "Texto del contrato." in self.ctx.to_query()

    def test_to_context_mentions_jurisdiction(self):
        assert "España" in self.ctx.to_context()

    def test_to_context_mentions_legal_mission(self):
        c = self.ctx.to_context()
        assert "legal" in c.lower() or "riesgo" in c.lower() or "cláusula" in c.lower()


class TestLegalBuildQuery:
    def test_build_legal_query_returns_tuple(self):
        doc = LegalDocument(doc_type="nda", text="Confidencialidad total.")
        result = build_legal_query(doc)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_build_legal_query_non_empty(self):
        doc = LegalDocument(doc_type="acuerdo", text="Acuerdo de colaboración.")
        query, context = build_legal_query(doc)
        assert query.strip()
        assert context.strip()


class TestLegalGodOverrides:
    def test_overrides_cover_key_gods(self):
        for god in ["claude", "enki", "inanna"]:
            assert god in LEGAL_GOD_OVERRIDES

    def test_overrides_have_system_extra(self):
        for god, config in LEGAL_GOD_OVERRIDES.items():
            assert "system_extra" in config
            assert isinstance(config["system_extra"], str)
