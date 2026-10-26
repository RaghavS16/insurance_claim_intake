"""Unit and integration tests for production enhancements:
- EmbeddingService (`embed`, `embed_documents`, FastEmbed fallback)
- Policy requirement manifest compilation & zero-latency unconditional resolution
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.knowledge.embeddings import EmbeddingService, embed, embed_documents
from src.knowledge.policy_compiler import compile_policy_requirements, resolve_requirement_manifest


def test_embed_and_embed_documents_export_compatibility(monkeypatch):
    """Ensure both `embed` and `embed_documents` are importable and delegate to EmbeddingService."""
    monkeypatch.setattr(
        EmbeddingService,
        "_embed_fastembed",
        lambda self, texts, model_name=None: [[0.25] * 768 for _ in texts],
    )
    from src.config import settings
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "fastembed")

    vecs1 = embed(["motor collision clause"])
    vecs2 = embed_documents(["health hospitalization clause"])
    assert len(vecs1) == 1 and len(vecs1[0]) == 768
    assert len(vecs2) == 1 and len(vecs2[0]) == 768


def test_embedding_service_falls_back_to_fastembed_when_ollama_unreachable(monkeypatch):
    """When primary Ollama endpoint is unreachable, EmbeddingService falls back to FastEmbed."""
    import requests
    from src.config import settings

    svc = EmbeddingService()
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    monkeypatch.setattr(settings, "GOOGLE_API_KEY", None)
    monkeypatch.setattr(
        svc,
        "_embed_openai_compatible",
        MagicMock(side_effect=requests.exceptions.ConnectionError("Connection refused")),
    )
    monkeypatch.setattr(
        svc,
        "_embed_fastembed",
        lambda texts, model_name=None: [[0.5] * 768 for _ in texts],
    )

    result = svc.embed(["test fallback chunk"])
    assert len(result) == 1
    assert len(result[0]) == 768


def test_unconditional_manifest_resolves_without_llm_call():
    """Unconditional requirement manifests resolve in 0ms without invoking the LLM."""
    manifest = [
        {
            "key": "policy_number",
            "label": "Policy Number",
            "question_hint": "Please provide your policy number.",
            "required": True,
            "evidence_type": None,
            "condition": None,
        },
        {
            "key": "incident_date",
            "label": "Incident Date",
            "question_hint": "When did the incident occur?",
            "required": True,
            "evidence_type": None,
            "condition": None,
        },
    ]
    with patch("src.knowledge.policy_compiler.get_configured_llm") as mock_llm:
        resolved = resolve_requirement_manifest(
            manifest=manifest,
            insurance_type="motor",
            claim_facts={"policy_id": "POL-DEMO-MOTOR-001"},
        )
        mock_llm.assert_not_called()

    assert len(resolved) == 2
    assert resolved[0]["canonical_role"] == "policy_id"
    assert resolved[1]["canonical_role"] == "event_date"


def test_compile_policy_requirements_accepts_legacy_policy_chunks_kwarg():
    """Verify compile_policy_requirements accepts both `chunks` and `policy_chunks` kwargs."""
    res = compile_policy_requirements(
        document_id="doc-1",
        insurance_type="motor",
        policy_chunks=[],
        policy_number="POL-1",
    )
    assert res == []
