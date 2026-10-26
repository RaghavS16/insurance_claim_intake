"""Comprehensive regression and verification tests for the IntelliClaim AI Chatbot and Adjuster AI Copilot upgrades."""
from pathlib import Path
from datetime import date
from src.knowledge.retriever import infer_insurance_type_from_query, rank_chunks_for_query
from src.knowledge.store import extract_docx_requirement_manifest
from src.agents.rag_chat import _heuristic_intent, _synthesize_structured_answer_from_chunks
from src.api.adjuster_routes import _run_deterministic_copilot_prechecks
from src.database.models import Claim, Policy


def test_insurance_type_inference_all_lines():
    """Verify that all 6 insurance lines are accurately inferred from user utterances."""
    assert infer_insurance_type_from_query("details require for apply new motor policy") == "motor"
    assert infer_insurance_type_from_query("ok explain filing motor policy") == "motor"
    assert infer_insurance_type_from_query("What is the waiting period for senior citizen health insurance?") in ("senior_health", "senior_citizen_health")
    assert infer_insurance_type_from_query("cashless hospital admission discharge summary") == "health"
    assert infer_insurance_type_from_query("Bharat Griha Raksha fire damage to contents") == "home"
    assert infer_insurance_type_from_query("lost baggage and delayed flight overseas claim") == "travel"
    assert infer_insurance_type_from_query("unauthorized UPI transaction 1930 NCRP complaint") == "cyber"


def test_sample_chat_turn_1_intent():
    """Verify Turn 1 utterance from sample-chat.md is correctly recognized as an informational question."""
    intent = _heuristic_intent("details require for apply new motor policy")
    assert intent.is_question is True
    assert intent.wants_policy_explanation is True


def test_sample_chat_turn_2_intent():
    """Verify Turn 2 utterance from sample-chat.md is correctly recognized as an informational question."""
    intent = _heuristic_intent("ok explain filing motor policy")
    assert intent.is_question is True
    assert intent.wants_policy_explanation is True


def test_section_intent_boosting():
    """Verify that application queries boost Section 5 and filing queries boost Section 6."""
    chunks = [
        {"section_number": "1.0", "text": "Quick facts and definitions of motor package policy.", "score": 0.80},
        {"section_number": "5.4", "text": "Documents required to apply: Proposal form, RC copy, KYC proofs.", "score": 0.60},
        {"section_number": "6.2", "text": "How to file a claim: 1. Notify insurer, 2. Submit estimate.", "score": 0.65},
    ]

    # Application query should rank Section 5.4 at the top
    app_ranked = rank_chunks_for_query("details require for apply new motor policy", chunks)
    assert app_ranked[0]["section_number"] == "5.4"

    # Filing query should rank Section 6.2 at the top
    file_ranked = rank_chunks_for_query("ok explain filing motor policy", chunks)
    assert file_ranked[0]["section_number"] == "6.2"


def test_structured_synthesizer_eliminates_chunk_0_dump():
    """Verify structured synthesis returns concise cited bullets rather than a raw verbatim Chunk 0 dump."""
    mock_sources = [
        {
            "source_name": "Motor_Policy_Wording.docx",
            "citation_label": "Motor_Policy_Wording.docx • Section 5.4",
            "text": """### 5.4 Documents Required to Apply
[Table — Section 5.4]
Category | Documents
• Identity Proof: PAN card, Aadhaar or Passport
• Vehicle Proof: Registration Certificate (RC) copy
• Previous Policy: Expiring policy renewal notice
""",
        }
    ]

    answer = _synthesize_structured_answer_from_chunks("details require for apply new motor policy", mock_sources)
    assert "To apply for this policy, the following documents and details are required" in answer
    assert "Identity Proof" in answer or "Registration Certificate" in answer
    assert "Sources: Motor_Policy_Wording.docx • Section 5.4" in answer
    assert not answer.startswith("Based on the indexed policy/guidance, MOTOR INSURANCE — INDIA")


def test_extract_docx_requirement_manifest():
    """Verify deterministic table parsing extracts Section 6 fields and evidence items from docrag DOCX."""
    docx_path = Path(__file__).resolve().parent.parent.parent / "docrag" / "Motor_Insurance_Policy_Wording.docx"
    if not docx_path.exists():
        docx_path = Path(__file__).resolve().parent.parent.parent / "database" / "docrag" / "Motor_Insurance_Policy_Wording.docx"

    if docx_path.exists():
        raw_bytes = docx_path.read_bytes()
        manifest = extract_docx_requirement_manifest(raw_bytes, docx_path.name, insurance_type="motor")
        assert len(manifest) >= 10

        keys = [item["key"] for item in manifest]
        assert "policy_id" in keys
        assert "event_date" in keys
        assert "event_location" in keys
        assert "event_description" in keys
        assert "estimated_claim_amount" in keys

        evidence_items = [item for item in manifest if item.get("evidence_type") == "document"]
        assert len(evidence_items) >= 4
        ev_keys = [item["key"] for item in evidence_items]
        assert any("driving_licence" in k or "rc_copy" in k or "repair_estimate" in k for k in ev_keys)


def test_copilot_deterministic_4phase_precheck():
    """Verify Adjuster Copilot 4-phase adjudication engine computes fraud score, IRDAI SLAs, and strict precedence recommendation."""
    mock_claim = Claim(
        id="claim-test-001",
        ticket_id="CLM-TEST-001",
        insurance_type="motor",
        claim_date=date(2026, 9, 20),
        event_date=date(2026, 9, 10),  # 10 days reporting gap -> triggers delayed intimation flag
        estimated_claim_amount=45000.0,
        event_description="Vehicle collision with minor bumper damage on highway.",
    )
    mock_policy = Policy(
        id="pol-test-001",
        policy_number="POL-DEMO-MOTOR-001",
        policy_type="motor",
        coverage_amount=1000000.0,
        deductible=10000.0,
        effective_date=date(2026, 9, 1),  # within 10 days of inception -> early claim timing anomaly
        expiry_date=date(2027, 9, 1),
        is_active=True,
    )

    state = {
        "extracted_data": {
            "policy_id": "POL-DEMO-MOTOR-001",
            "insurance_type": "motor",
            "event_date": "2026-09-10",
        }
    }
    evidence_rows = [
        {"filename": "rc_copy.pdf", "category": "rc_copy", "verification_confidence": 0.95}
    ]
    missing_evidence = [
        {"key": "driving_licence", "label": "Driving Licence"},
        {"key": "police_fir", "label": "Police FIR"},
    ]
    source_rows = [
        {"chunk_id": "chunk-101", "citation_label": "Motor_Policy_Wording.docx • Section 6.3", "source_name": "Motor_Policy_Wording.docx"}
    ]

    report = _run_deterministic_copilot_prechecks(
        mock_claim, state, mock_policy, evidence_rows, source_rows, missing_evidence
    )

    assert report["decision_recommendation"] == "REQUEST_EVIDENCE"
    assert report["fraud_score"] >= 0.40  # early claim + delayed intimation + missing FIR
    assert len(report["risk_flags"]) >= 2
    assert any("Early-claim timing anomaly" in f for f in report["risk_flags"])
    assert any("Delayed intimation" in f for f in report["risk_flags"])
    assert len(report["regulatory_considerations"]) >= 3
    assert any("Surveyor Allocation: Within 24 hours" in s for s in report["regulatory_considerations"])
    assert len(report["citations"]) == 1
    assert report["citations"][0]["source_id"] == "chunk-101"

    # Also test high fraud score escalation
    high_risk_claim = Claim(
        id="claim-test-002",
        ticket_id="CLM-TEST-002",
        insurance_type="motor",
        claim_date=date(2026, 9, 20),
        event_date=date(2026, 9, 10),
        estimated_claim_amount=950000.0,
        event_description="Vehicle theft staged outside commercial complex.",
    )
    high_risk_report = _run_deterministic_copilot_prechecks(
        high_risk_claim, state, mock_policy, evidence_rows, source_rows, missing_evidence
    )
    assert high_risk_report["fraud_score"] >= 0.70
    assert high_risk_report["decision_recommendation"] == "ESCALATE"

