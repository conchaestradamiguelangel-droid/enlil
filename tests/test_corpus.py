import os
os.environ.setdefault("OPENROUTER_API_KEY", "test")
os.environ.setdefault("ENLIL_DB", ":memory:")

import pytest
from unittest.mock import MagicMock, patch
from enlil.corpus import CorpusStore, CORPUS_DATA, CORPUS_COLLECTION


class TestCorpusData:
    def test_corpus_has_100_entries(self):
        assert len(CORPUS_DATA) == 100

    def test_corpus_entries_have_required_fields(self):
        for entry in CORPUS_DATA:
            assert "id" in entry and "title" in entry and "deity" in entry
            assert "type" in entry and "text" in entry and "source" in entry

    def test_corpus_has_all_four_deities(self):
        deities = {e["deity"] for e in CORPUS_DATA}
        for deity in ["Enlil", "Enki", "Ninurta", "Inanna"]:
            assert deity in deities

    def test_corpus_ids_are_unique(self):
        ids = [e["id"] for e in CORPUS_DATA]
        assert len(ids) == len(set(ids))

    def test_corpus_types_are_valid(self):
        valid_types = {"hymn", "myth", "proverb", "prayer", "epic", "wisdom"}
        for entry in CORPUS_DATA:
            assert entry["type"] in valid_types, f"Invalid type: {entry['type']}"

    def test_corpus_collection_name(self):
        assert CORPUS_COLLECTION == "enlil_corpus"

    def test_corpus_deity_distribution(self):
        """Verifica que hay al menos 15 entradas por deidad principal."""
        from collections import Counter
        counts = Counter(e["deity"] for e in CORPUS_DATA)
        for deity in ["Enlil", "Enki", "Ninurta", "Inanna"]:
            assert counts[deity] >= 15, f"{deity} has only {counts[deity]} entries"


class TestCorpusStore:
    def _make_store(self, search_results=None):
        mock_client = MagicMock()
        mock_client.get_collections.return_value = MagicMock(collections=[])
        mock_client.query_points.return_value = MagicMock(
            points=search_results or []
        )
        mock_embed = MagicMock()
        mock_embed.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.1] * 1536)]
        )
        return CorpusStore(mock_client, mock_embed)

    def test_count_returns_zero_when_empty(self):
        store = self._make_store()
        store._client.get_collection.return_value = MagicMock(points_count=0)
        assert store.count() == 0

    def test_search_returns_empty_when_no_results(self):
        store = self._make_store(search_results=[])
        result = store.search("consulta test")
        assert result == ""

    def test_search_formats_result_correctly(self):
        mock_point = MagicMock()
        mock_point.payload = {
            "title": "Himno a Enlil",
            "deity": "Enlil",
            "text": "Enlil grande...",
            "source": "ETCSL 4.05.1",
        }
        store = self._make_store(search_results=[mock_point])
        result = store.search("enlil poder")
        assert "Himno a Enlil" in result
        assert "Enlil" in result

    def test_from_qdrant_store_returns_none_when_unavailable(self):
        mock_qdrant = MagicMock()
        mock_qdrant.is_available = False
        result = CorpusStore.from_qdrant_store(mock_qdrant)
        assert result is None

    def test_from_qdrant_store_creates_store_when_available(self):
        mock_qdrant = MagicMock()
        mock_qdrant.is_available = True
        mock_qdrant._client = MagicMock()
        mock_qdrant._client.get_collections.return_value = MagicMock(collections=[])
        mock_qdrant._embed_client = MagicMock()
        result = CorpusStore.from_qdrant_store(mock_qdrant)
        assert result is not None
        assert isinstance(result, CorpusStore)

    def test_search_returns_source_reference(self):
        mock_point = MagicMock()
        mock_point.payload = {
            "title": "Inanna's Descent",
            "deity": "Inanna",
            "text": "From the great above she opened her ear...",
            "source": "ETCSL 1.4.1",
        }
        store = self._make_store(search_results=[mock_point])
        result = store.search("underworld descent")
        assert "ETCSL 1.4.1" in result

    def test_count_returns_positive_when_has_points(self):
        store = self._make_store()
        store._client.get_collection.return_value = MagicMock(points_count=42)
        assert store.count() == 42
