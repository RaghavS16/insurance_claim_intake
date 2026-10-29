"""
Tests for DOCX section chunking, document checklist ranking, offline bullet extraction,
and resilient LLM failover.
"""
from __future__ import annotations

import os
import pytest
from unittest.mock import MagicMock, patch
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# 1. Structure-Aware Chunks & Bullet Preservation
# ---------------------------------------------------------------------------
def test_structure_aware_chunks_docx_headings_and_newlines():
    from src.knowledge.store import _structure_aware_chunks

    sample_doc = """
### Section 6.6 Settlement Timelines
All claims shall be settled within 30 days of receipt of all documents.
Interest at 2% above bank rate applies for delay.

### 6.7 Claim Intake Form — Fields to Capture
• Date of incident
• Place of incident
• Description of damage

### 6.8 Mandatory Documents Checklist
• Duly completed and signed claim form
• Registration Certificate (RC) of the vehicle
• Driving licence of person driving
• Police First Information Report (FIR) in case of theft or third-party injury
• Repair estimate from authorized garage
"""
    chunks = _structure_aware_chunks(sample_doc)

    assert len(chunks) == 3
    # Check section provenance
    assert "6.6" in str(chunks[0].get("section_number"))
    assert "6.7" in str(chunks[1].get("section_number"))
    assert "6.8" in str(chunks[2].get("section_number"))

    # Verify bullet newlines are preserved rather than flattened into a single space
    chunk_68 = chunks[2]["text"]
    assert "\n• Duly completed" in chunk_68
    assert "\n• Registration Certificate (RC)" in chunk_68
    assert "\n• Repair estimate" in chunk_68


def test_structure_aware_chunks_long_section_line_boundary_overlap():
    from src.knowledge.store import _structure_aware_chunks

    # Construct a section with 50 bullet lines, each ~10 words -> ~500 words
    bullet_lines = [f"• Document requirement line item number {i} for verification and claim processing" for i in range(50)]
    text = "### Section 6.3 Required Documents\n" + "\n".join(bullet_lines)

    chunks = _structure_aware_chunks(text)
    assert len(chunks) > 1

    # Verify no line is chopped in half: each chunk must start and end with complete lines
    for c in chunks:
        lines = c["text"].splitlines()
        for ln in lines:
            assert ln.startswith("###") or ln.startswith("•")


# ---------------------------------------------------------------------------
# 2. Document Checklist Ranking Over Intake Form Fields
# ---------------------------------------------------------------------------
def test_rank_chunks_for_document_checklist_query():
    from src.knowledge.retriever import rank_chunks_for_query

    chunks = [
        {
            "id": "c_grievance",
            "section_number": "sources / ombudsman",
            "text": "Bima Bharosa grievance redressal and Insurance Ombudsman contacts.",
            "score": 0.90,
        },
        {
            "id": "c_intake_fields",
            "section_number": "6.7",
            "text": "Claim intake form — fields to capture: incident date, incident location, vehicle speed.",
            "score": 0.88,
        },
        {
            "id": "c_checklist",
            "section_number": "6.8",
            "text": "Mandatory documents checklist:\n• Duly completed claim form\n• Registration Certificate (RC)\n• Driving licence",
            "score": 0.70,
        },
    ]

    # Query asking about required documents / checklist
    ranked = rank_chunks_for_query("what documents are required to file a claim checklist", chunks)
    ids = [c["id"] for c in ranked]

    # Section 6.8 checklist must rank #1 over Section 6.7 intake fields
    assert ids[0] == "c_checklist"
    # Ombudsman/grievance must be penalized to last position
    assert ids[-1] == "c_grievance"


def test_rank_chunks_for_apply_query():
    from src.knowledge.retriever import rank_chunks_for_query

    chunks = [
        {
            "id": "c_claim",
            "section_number": "6.1",
            "text": "6.1 How to file a claim step by step",
            "score": 0.85,
        },
        {
            "id": "c_apply",
            "section_number": "5.4 documents required",
            "text": "5. How to apply: identity proof, address proof, vehicle RC",
            "score": 0.70,
        },
    ]

    ranked = rank_chunks_for_query("how to apply for a new policy and kyc documents", chunks)
    assert ranked[0]["id"] == "c_apply"


# ---------------------------------------------------------------------------
# 3. RAG Chat: Offline Bullet Extraction & Query Expansion
# ---------------------------------------------------------------------------
def test_synthesize_structured_answer_from_requirements_manifest():
    from src.agents.rag_chat import _synthesize_structured_answer_from_chunks

    reqs = [
        {"evidence_type": "document", "label": "Vehicle RC", "condition": "All claims", "note": "Self-attested copy"},
        {"evidence_type": "document", "label": "Driving Licence", "condition": "Own Damage", "note": "Valid at incident time"},
        {"evidence_type": "data", "label": "Incident Time"},
    ]
    sources = [{"text": "Sample text", "citation_label": "Policy Wording • Section 6.8"}]

    answer = _synthesize_structured_answer_from_chunks("what documents do I need to submit?", sources, requirements=reqs)
    assert "Vehicle RC (Mandatory for all claims) — Self-attested copy" in answer
    assert "Driving Licence (Own Damage) — Valid at incident time" in answer
    assert "Incident Time" not in answer  # Non-document evidence excluded
    assert "Sources: Policy Wording • Section 6.8" in answer


def test_synthesize_structured_answer_bullet_extraction_across_top_sources():
    from src.agents.rag_chat import _synthesize_structured_answer_from_chunks

    sources = [
        {
            "source_name": "Motor Policy Wording",
            "citation_label": "Section 6.8 Checklist",
            "text": "### 6.8 Checklist\n• Document / evidence: Duly completed and signed claim form • Document / evidence: Registration Certificate (RC)",
        },
        {
            "source_name": "Motor Policy Wording",
            "citation_label": "Section 6.3 Documents",
            "text": "• Driving licence of driver at time of accident\n• Repair estimate from network garage",
        },
    ]

    answer = _synthesize_structured_answer_from_chunks("what papers or documents are required?", sources)
    assert "• Duly completed and signed claim form" in answer
    assert "• Registration Certificate (RC)" in answer
    assert "• Driving licence of driver" in answer
    assert "• Repair estimate from network garage" in answer
    assert "Document / evidence:" not in answer  # Cleaned prefix


# ---------------------------------------------------------------------------
# 4. LLM Factory: Key Rotation Fallback Aliases & All-Exception Failover
# ---------------------------------------------------------------------------
def test_rotate_key_plural_fallback_aliases():
    from src.agents.llm_factory import _rotate_key

    # Test Groq plural alias fallback
    with patch.dict(os.environ, {"GROQ_API_KEYS": "gsk_key1, gsk_key2"}, clear=False):
        k1 = _rotate_key("groq", "<YOUR_GROQ_KEY>")
        assert k1 in ("gsk_key1", "gsk_key2")

    # Test Gemini plural alias fallback
    with patch.dict(os.environ, {"GEMINI_API_KEYS": "gemini_key1"}, clear=False):
        k_gem = _rotate_key("gemini", "")
        assert k_gem == "gemini_key1"

    # Test HF plural alias fallback
    with patch.dict(os.environ, {"HF_TOKENS": "hf_token1"}, clear=False):
        k_hf = _rotate_key("hf", "<REPLACE>")
        assert k_hf == "hf_token1"


class _DummyResponse:
    def __init__(self, content: str):
        self.content = content


class _DummySchema(BaseModel):
    summary: str


def test_resilient_chat_model_fails_over_across_candidate_exceptions():
    from src.agents.llm_factory import ResilientChatModel

    # Primary model throws HTTP 400 (e.g. invalid argument or deprecated model)
    mock_primary = MagicMock()
    mock_primary.invoke.side_effect = RuntimeError("400 Bad Request: model not found")
    mock_primary.openai_api_base = "https://api.groq.com/openai/v1"
    mock_primary.openai_api_key = "test_key_primary"
    mock_primary.model = "llama-3-deprecated"

    # Secondary candidate model succeeds
    mock_secondary = MagicMock()
    mock_secondary.invoke.return_value = _DummyResponse("Secondary success")
    mock_secondary.openai_api_base = "https://router.huggingface.co/v1"
    mock_secondary.openai_api_key = "test_key_sec"
    mock_secondary.model = "openai/gpt-oss-20b:groq"

    resilient = ResilientChatModel(
        primary=mock_primary,
        candidate_builders=[lambda: mock_secondary],
    )

    result = resilient.invoke("Test prompt")
    assert result.content == "Secondary success"
    assert mock_primary.invoke.called
    assert mock_secondary.invoke.called


def test_resilient_structured_fails_over_across_candidate_exceptions():
    from src.agents.llm_factory import structured_output, ResilientChatModel

    mock_primary = MagicMock()
    # Throws 401 Unauthorized or validation failure
    mock_primary.invoke.side_effect = RuntimeError("401 Unauthorized: Invalid API key")
    mock_primary.openai_api_base = "https://api.groq.com/openai/v1"
    mock_primary.openai_api_key = "bad_key"
    mock_primary.model = "llama-3.3-70b-versatile"

    mock_secondary = MagicMock()
    mock_secondary.invoke.return_value = _DummyResponse('{"summary": "Structured success"}')
    mock_secondary.openai_api_base = "https://router.huggingface.co/v1"
    mock_secondary.openai_api_key = "good_key"
    mock_secondary.model = "openai/gpt-oss-20b:groq"

    resilient = ResilientChatModel(
        primary=mock_primary,
        candidate_builders=[lambda: mock_secondary],
    )

    runner = structured_output(resilient, _DummySchema)
    res = runner.invoke("Summarize claim")
    assert isinstance(res, _DummySchema)
    assert res.summary == "Structured success"

