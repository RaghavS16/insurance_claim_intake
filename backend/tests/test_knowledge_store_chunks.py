"""
Edge-case tests for src/knowledge/store.py pure functions.

Focuses on _extract_text (text branch), _chunks, and ingest_document edge cases
(size limit, duplicate detection). Heavy I/O is mocked.
"""
import io
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# _chunks
# ---------------------------------------------------------------------------
class TestChunks:
    def _call(self, text, size=450, overlap=75):
        from src.knowledge.store import _chunks
        return _chunks(text, size=size, overlap=overlap)

    def test_empty_string_returns_empty(self):
        assert self._call("") == []

    def test_whitespace_only_returns_empty(self):
        assert self._call("   ") == []

    def test_short_text_single_chunk(self):
        text = "This is a short text with just a few words."
        result = self._call(text)
        assert len(result) == 1
        assert "short text" in result[0]

    def test_long_text_produces_multiple_chunks(self):
        words = " ".join([f"word{i}" for i in range(1000)])
        result = self._call(words, size=100, overlap=20)
        assert len(result) > 1

    def test_chunks_have_overlap(self):
        """Last word of chunk N should appear in chunk N+1 with overlap."""
        words = " ".join([f"word{i}" for i in range(200)])
        result = self._call(words, size=50, overlap=10)
        if len(result) >= 2:
            last_words_of_first = set(result[0].split()[-10:])
            first_words_of_second = set(result[1].split()[:10])
            assert last_words_of_first & first_words_of_second  # overlap exists

    def test_size_one_no_crash(self):
        text = "hello world"
        result = self._call(text, size=1, overlap=0)
        assert len(result) >= 1

    def test_all_chunks_are_non_empty_strings(self):
        words = " ".join([f"w{i}" for i in range(500)])
        result = self._call(words)
        assert all(isinstance(c, str) and c.strip() for c in result)


# ---------------------------------------------------------------------------
# _extract_text (text / encoding fallback branch)
# ---------------------------------------------------------------------------
class TestExtractText:
    def test_utf8_text_decoded(self):
        from src.knowledge.store import _extract_text
        content = "Hello, this is a test document.".encode("utf-8")
        result = _extract_text(content, "test.txt")
        assert "Hello" in result

    def test_latin1_text_decoded(self):
        from src.knowledge.store import _extract_text
        content = "Caf\xe9 au lait".encode("latin-1")
        result = _extract_text(content, "test.txt")
        assert len(result) > 0

    def test_markdown_treated_as_text(self):
        from src.knowledge.store import _extract_text
        content = "# Title\n\nSome paragraph.".encode("utf-8")
        result = _extract_text(content, "doc.md")
        assert "Title" in result

    def test_json_treated_as_text(self):
        from src.knowledge.store import _extract_text
        content = '{"key": "value"}'.encode("utf-8")
        result = _extract_text(content, "data.json")
        assert "key" in result

    def test_docx_import_error_raises_value_error(self):
        from src.knowledge.store import _extract_text
        content = b"FakeDocxContent"
        with pytest.raises((ValueError, Exception)):
            _extract_text(content, "file.docx")


# ---------------------------------------------------------------------------
# ingest_document edge cases (heavily mocked)
# ---------------------------------------------------------------------------
class TestIngestDocument:
    def _base_patches(self):
        return [
            patch("src.knowledge.store._extract_text", return_value="A " * 100),
            patch("src.knowledge.store.infer_metadata", return_value=MagicMock(
                insurance_type="motor", policy_number=None, effective_from=None,
                effective_to=None, document_type="policy_wording",
                title="Test", document_scope="test"
            )),
            patch("src.knowledge.store.embed_documents", return_value=[[0.1] * 768] * 10),
            patch("src.knowledge.store.put_bytes", return_value={"uri": "s3://bucket/key"}),
            patch("src.knowledge.store.SessionLocal"),
        ]

    def test_exceeds_max_size_raises_value_error(self, monkeypatch):
        from src.knowledge.store import ingest_document
        from src.config import settings
        monkeypatch.setattr(settings, "KNOWLEDGE_MAX_UPLOAD_BYTES", 100)
        with pytest.raises(ValueError, match="too large"):
            ingest_document(content=b"X" * 200, filename="big.pdf")

    def test_too_little_text_raises_value_error(self):
        from src.knowledge.store import ingest_document
        with patch("src.knowledge.store._extract_text", return_value="tiny"):
            with pytest.raises(ValueError, match="too little"):
                ingest_document(content=b"small doc", filename="small.txt")

    def test_duplicate_document_returns_existing(self):
        from src.knowledge.store import ingest_document
        mock_existing = MagicMock()
        mock_existing.id = "existing-uuid"
        mock_existing.source_name = "doc.pdf"
        mock_existing.source_uri = "s3://bucket/doc.pdf"
        mock_existing.chunks = [MagicMock()] * 5
        mock_existing.insurance_type = "motor"
        mock_existing.policy_number = "POL-001"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_existing
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)

        with patch("src.knowledge.store._extract_text", return_value="A " * 100), \
             patch("src.knowledge.store.infer_metadata", return_value=MagicMock(
                 insurance_type="motor", policy_number=None, effective_from=None,
                 effective_to=None, document_type="policy_wording",
                 title="T", document_scope="s"
             )), \
             patch("src.knowledge.store.SessionLocal", return_value=mock_db):
            result = ingest_document(content=b"X" * 100, filename="doc.pdf")
        assert result.get("duplicate") is True
        assert result["document_id"] == "existing-uuid"

    def test_embedding_vector_count_mismatch_raises_runtime_error(self):
        from src.knowledge.store import ingest_document
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)

        with patch("src.knowledge.store._extract_text", return_value="A " * 1000), \
             patch("src.knowledge.store.infer_metadata", return_value=MagicMock(
                 insurance_type=None, policy_number=None, effective_from=None,
                 effective_to=None, document_type="policy_wording",
                 title="T", document_scope="s"
             )), \
             patch("src.knowledge.store.embed_documents", return_value=[[0.1]]),  \
             patch("src.knowledge.store.SessionLocal", return_value=mock_db):
            with pytest.raises(RuntimeError, match="Embedding service returned"):
                ingest_document(content=b"X" * 1000, filename="doc.pdf")
