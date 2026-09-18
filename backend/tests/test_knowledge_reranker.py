"""
Edge-case tests for src/knowledge/reranker.py

Covers: rerank with various configurations.
"""
import pytest
from unittest.mock import MagicMock, patch


class TestRerank:
    def _docs(self, n=5):
        return [{"id": str(i), "text": f"document {i}", "score": 1.0 - (i * 0.1)} for i in range(n)]

    def test_empty_documents_returns_empty(self, monkeypatch):
        from src.knowledge.reranker import rerank
        from src.config import settings
        monkeypatch.setattr(settings, "RERANK_MODEL", "cross-encoder")
        assert rerank("query", [], top_n=5) == []

    def test_no_rerank_model_returns_top_n_slice(self, monkeypatch):
        from src.knowledge.reranker import rerank
        from src.config import settings
        monkeypatch.setattr(settings, "RERANK_MODEL", None)
        docs = self._docs(10)
        result = rerank("query", docs, top_n=3)
        assert result == docs[:3]

    def test_no_base_url_returns_top_n_slice(self, monkeypatch):
        from src.knowledge.reranker import rerank
        from src.config import settings
        monkeypatch.setattr(settings, "RERANK_MODEL", "cross-encoder")
        monkeypatch.setattr(settings, "EMBEDDING_BASE_URL", None)
        monkeypatch.setattr(settings, "CLOUD_LLM_BASE_URL", None)
        docs = self._docs(10)
        result = rerank("query", docs, top_n=4)
        assert result == docs[:4]

    def test_openrouter_base_url_returns_top_n_slice(self, monkeypatch):
        from src.knowledge.reranker import rerank
        from src.config import settings
        monkeypatch.setattr(settings, "RERANK_MODEL", "cross-encoder")
        monkeypatch.setattr(settings, "EMBEDDING_BASE_URL", "https://openrouter.ai/api/v1")
        docs = self._docs(10)
        result = rerank("query", docs, top_n=2)
        assert result == docs[:2]

    def test_no_api_key_returns_top_n_slice(self, monkeypatch):
        from src.knowledge.reranker import rerank
        from src.config import settings
        monkeypatch.setattr(settings, "RERANK_MODEL", "cross-encoder")
        monkeypatch.setattr(settings, "EMBEDDING_BASE_URL", "http://localhost:8080")
        monkeypatch.setattr(settings, "EMBEDDING_API_KEY", None)
        monkeypatch.setattr(settings, "CLOUD_LLM_API_KEY", None)
        docs = self._docs(5)
        result = rerank("query", docs, top_n=3)
        assert result == docs[:3]

    def test_successful_rerank_returns_scored_docs(self, monkeypatch):
        from src.knowledge.reranker import rerank
        from src.config import settings
        monkeypatch.setattr(settings, "RERANK_MODEL", "cross-encoder")
        monkeypatch.setattr(settings, "EMBEDDING_BASE_URL", "http://localhost:8080")
        monkeypatch.setattr(settings, "EMBEDDING_API_KEY", "test-key")
        monkeypatch.setattr(settings, "RERANK_TIMEOUT_SECONDS", 30)
        docs = self._docs(5)
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "results": [
                {"index": 2, "relevance_score": 0.95},
                {"index": 0, "relevance_score": 0.90},
                {"index": 1, "relevance_score": 0.85},
            ]
        }
        with patch("src.knowledge.reranker.requests.post", return_value=mock_response):
            result = rerank("query", docs, top_n=3)
        assert len(result) == 3
        assert result[0]["rerank_score"] == 0.95

    def test_rerank_api_failure_falls_back_to_top_n(self, monkeypatch):
        from src.knowledge.reranker import rerank
        from src.config import settings
        monkeypatch.setattr(settings, "RERANK_MODEL", "cross-encoder")
        monkeypatch.setattr(settings, "EMBEDDING_BASE_URL", "http://localhost:8080")
        monkeypatch.setattr(settings, "EMBEDDING_API_KEY", "test-key")
        monkeypatch.setattr(settings, "RERANK_TIMEOUT_SECONDS", 30)
        docs = self._docs(5)
        with patch("src.knowledge.reranker.requests.post", side_effect=Exception("Connection refused")):
            result = rerank("query", docs, top_n=3)
        assert result == docs[:3]

    def test_top_n_exceeds_docs_length(self, monkeypatch):
        from src.knowledge.reranker import rerank
        from src.config import settings
        monkeypatch.setattr(settings, "RERANK_MODEL", None)
        docs = self._docs(3)
        result = rerank("query", docs, top_n=10)
        assert len(result) == 3

    def test_top_n_zero_returns_empty(self, monkeypatch):
        from src.knowledge.reranker import rerank
        from src.config import settings
        monkeypatch.setattr(settings, "RERANK_MODEL", None)
        docs = self._docs(5)
        result = rerank("query", docs, top_n=0)
        assert result == []

    def test_rerank_index_out_of_bounds_skipped(self, monkeypatch):
        """If reranker returns an out-of-bounds index, it should be skipped gracefully."""
        from src.knowledge.reranker import rerank
        from src.config import settings
        monkeypatch.setattr(settings, "RERANK_MODEL", "cross-encoder")
        monkeypatch.setattr(settings, "EMBEDDING_BASE_URL", "http://localhost:8080")
        monkeypatch.setattr(settings, "EMBEDDING_API_KEY", "test-key")
        monkeypatch.setattr(settings, "RERANK_TIMEOUT_SECONDS", 30)
        docs = self._docs(3)
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "results": [
                {"index": 999, "relevance_score": 0.99},  # out of bounds
                {"index": 0, "relevance_score": 0.80},
            ]
        }
        with patch("src.knowledge.reranker.requests.post", return_value=mock_response):
            result = rerank("query", docs, top_n=2)
        # Only index 0 is valid; index 999 must be skipped
        assert all(r.get("id", "999") != "999" for r in result)

    def test_empty_results_from_reranker_falls_back(self, monkeypatch):
        from src.knowledge.reranker import rerank
        from src.config import settings
        monkeypatch.setattr(settings, "RERANK_MODEL", "cross-encoder")
        monkeypatch.setattr(settings, "EMBEDDING_BASE_URL", "http://localhost:8080")
        monkeypatch.setattr(settings, "EMBEDDING_API_KEY", "test-key")
        monkeypatch.setattr(settings, "RERANK_TIMEOUT_SECONDS", 30)
        docs = self._docs(5)
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"results": []}
        with patch("src.knowledge.reranker.requests.post", return_value=mock_response):
            result = rerank("query", docs, top_n=3)
        # Empty results -> fall back to original top_n
        assert result == docs[:3]
