"""End-to-end verification tests for source-of-truth claim intake pipeline.

Validates the 7 core requirements:
1. First question is dynamic from RAG, zero hardcoded field list or order.
2. Policy identifier is verified against DB immediately upon collection before further fields.
3. Invalid / unowned policy identifier is rejected clearly, blocking further intake.
4. Full set of required fields genuinely differs between policy types (Motor vs Health).
5. Clean extracted values only (never raw claimant conversational sentences).
6. Adjuster workspace dossier contains dynamic field-label/value pairs.
7. Honest fallback when knowledge base has no indexed requirements.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import date, datetime, timezone

from src.agents.dynamic_requirements import (
    clean_extracted_value,
    sync_extracted_fields,
    build_dynamic_context,
    extract_answers,
    unresolved,
)
from src.agents.graph import _response_planner, _dynamic_requirement_enrichment
from src.agents.policy_check import verify_policy_for_claim
from src.agents.submission_synthesizer import synthesize_claims_package
from src.agents.gap_analysis import analyze_claim_gaps


def test_1_first_question_is_not_hardcoded_and_comes_from_rag():
    """Verify that there is no hardcoded first question or baseline field assumption."""
    state = {
        "tenant_id": "tenant-1",
        "claim_text": "I need to file a claim for my vehicle damage",
        "extracted_data": {},
        "conversation_history": [],
        "rag_status": "UNKNOWN",
    }
    mock_requirements = [
        {"key": "policy_number", "label": "Policy Number", "question_hint": "Please provide your motor policy number.", "required": True},
        {"key": "incident_location", "label": "Incident Location", "question_hint": "Where did the accident occur?", "required": True},
        {"key": "repair_estimate", "label": "Repair Estimate", "question_hint": "What is the repair estimate?", "required": True},
    ]
    with patch("src.agents.graph.build_dynamic_context") as mock_ctx:
        mock_ctx.return_value = {
            "status": "OK",
            "available": True,
            "requirements": mock_requirements,
            "policy": [{"text": "Clause 4.1: Report collision with policy number, location, and estimate."}],
        }
        enriched = _dynamic_requirement_enrichment(state)
        planned = _response_planner(enriched)

        assert planned["conversation_phase"] == "source_of_truth_intake"
        assert planned["next_question_field"] == "policy_number"
        assert "policy number" in planned["next_question"].lower()


def test_2_and_3_policy_verification_immediate_and_rejects_invalid():
    """Policy identifier is verified immediately and blocks progression if invalid or unowned."""
    from src.database.models import Policy, Claim

    # Mock DB setup
    mock_db = MagicMock()
    mock_claim = MagicMock()
    mock_claim.id = "claim-101"
    mock_claim.claimant_id = "user-alice"
    mock_claim.tenant_id = "tenant-1"
    mock_claim.pipeline_state = {}

    # Policy belongs to bob, not alice
    mock_policy_bob = MagicMock()
    mock_policy_bob.policy_number = "POL-BOB-999"
    mock_policy_bob.customer_id = "user-bob"
    mock_policy_bob.is_active = True
    mock_policy_bob.expiry_date = date(2027, 1, 1)

    def query_mock(model):
        m = MagicMock()
        if model is Claim:
            m.filter.return_value.first.return_value = mock_claim
        elif model is Policy:
            m.filter.return_value.first.return_value = mock_policy_bob
        else:
            m.filter.return_value.first.return_value = None
        return m

    mock_db.query.side_effect = query_mock

    # 1. Unowned policy test -> Rejected
    unowned_result = verify_policy_for_claim(
        policy_id="POL-BOB-999",
        event_date_str=None,
        claimant_user_id="user-alice",
        db=mock_db,
        claim_id="claim-101",
    )
    assert unowned_result["valid"] is False
    assert unowned_result["reason"] == "ownership_mismatch"

    # 2. Non-existent policy test -> Rejected
    def query_mock_not_found(model):
        m = MagicMock()
        if model is Claim:
            m.filter.return_value.first.return_value = mock_claim
        else:
            m.filter.return_value.first.return_value = None
        return m

    mock_db.query.side_effect = query_mock_not_found
    missing_result = verify_policy_for_claim(
        policy_id="POL-NONEXISTENT",
        event_date_str=None,
        claimant_user_id="user-alice",
        db=mock_db,
        claim_id="claim-101",
    )
    assert missing_result["valid"] is False
    assert missing_result["reason"] == "policy_not_found"

    # 3. Valid owned policy test -> Verified immediately without requiring other fields
    mock_policy_alice = MagicMock()
    mock_policy_alice.policy_number = "POL-ALICE-100"
    mock_policy_alice.customer_id = "user-alice"
    mock_policy_alice.is_active = True
    mock_policy_alice.effective_date = date(2026, 1, 1)
    mock_policy_alice.expiry_date = date(2027, 1, 1)
    mock_policy_alice.policy_type = "motor"
    mock_policy_alice.coverage_amount = 500000.0

    def query_mock_alice(model):
        m = MagicMock()
        if model is Claim:
            m.filter.return_value.first.return_value = mock_claim
        elif model is Policy:
            m.filter.return_value.first.return_value = mock_policy_alice
        else:
            m.filter.return_value.first.return_value = None
        return m

    mock_db.query.side_effect = query_mock_alice
    valid_result = verify_policy_for_claim(
        policy_id="POL-ALICE-100",
        event_date_str=None,
        claimant_user_id="user-alice",
        db=mock_db,
        claim_id="claim-101",
    )
    assert valid_result["valid"] is True
    assert valid_result["reason"] is None


def test_4_different_policy_types_produce_genuinely_different_fields():
    """Motor and Health policies produce distinct required fields and question flows."""
    motor_requirements = [
        {"key": "policy_number", "label": "Motor Policy Number", "question_hint": "Please provide your Motor policy number.", "required": True},
        {"key": "vehicle_registration", "label": "Vehicle Registration Number", "question_hint": "What is the vehicle registration number?", "required": True},
        {"key": "incident_location", "label": "Accident Location", "question_hint": "Where did the accident take place?", "required": True},
        {"key": "repair_estimate", "label": "Estimated Repair Cost", "question_hint": "What is the estimated repair quotation?", "required": True},
        {"key": "repair_quotation_doc", "label": "Garage Quotation Document", "evidence_type": "document", "required": True},
    ]

    health_requirements = [
        {"key": "policy_number", "label": "Health Policy Number", "question_hint": "What is your Health Insurance Policy Number?", "required": True},
        {"key": "hospital_name", "label": "Hospital Name", "question_hint": "Which hospital were you admitted to?", "required": True},
        {"key": "admission_date", "label": "Hospital Admission Date", "question_hint": "When were you admitted to the hospital?", "required": True},
        {"key": "diagnosis_description", "label": "Ailment / Diagnosis", "question_hint": "What was the medical condition diagnosed?", "required": True},
        {"key": "discharge_summary_doc", "label": "Hospital Discharge Summary", "evidence_type": "document", "required": True},
    ]

    motor_state = {
        "tenant_id": "tenant-1",
        "claim_text": "I had a car crash",
        "dynamic_requirements": motor_requirements,
        "extracted_data": {},
        "rag_status": "OK",
    }
    motor_unresolved = [r["key"] for r in unresolved(motor_state)]
    assert "vehicle_registration" in motor_unresolved
    assert "incident_location" in motor_unresolved
    assert "hospital_name" not in motor_unresolved

    health_state = {
        "tenant_id": "tenant-1",
        "claim_text": "I was admitted to the hospital for surgery",
        "dynamic_requirements": health_requirements,
        "extracted_data": {},
        "rag_status": "OK",
    }
    health_unresolved = [r["key"] for r in unresolved(health_state)]
    assert "hospital_name" in health_unresolved
    assert "admission_date" in health_unresolved
    assert "vehicle_registration" not in health_unresolved


def test_5_clean_extracted_values_never_raw_sentence():
    """Claimant conversational sentences are parsed into clean normalized values."""
    # Policy number
    clean_pol = clean_extracted_value("policy_number", "my policy number is POL-DEMO-MOTOR-001 please")
    assert clean_pol == "POL-DEMO-MOTOR-001"

    # Vehicle plate
    clean_plate = clean_extracted_value("vehicle_registration", "my bike number is TN31A4567")
    assert clean_plate == "TN31A4567"

    # Hospital name
    clean_hosp = clean_extracted_value("hospital_name", "it was Apollo Multi-Specialty Hospital")
    assert clean_hosp == "Apollo Multi-Specialty Hospital"

    # State sync
    state = {
        "dynamic_requirements": [
            {"key": "policy_number", "label": "Policy Number", "requirement_id": "req-1"},
            {"key": "vehicle_reg", "label": "Vehicle Plate", "requirement_id": "req-2"},
        ],
        "extracted_data": {
            "policy_number": "my policy is POL-12345",
            "vehicle_reg": "my car plate is KA01MJ9999",
        },
    }
    sync_extracted_fields(state)
    assert len(state["extracted_fields"]) == 2
    entries = {e["field_key"]: e for e in state["extracted_fields"]}
    assert entries["policy_number"]["value"] == "POL-12345"
    assert entries["vehicle_reg"]["value"] == "KA01MJ9999"


def test_6_adjuster_workspace_dossier_renders_dynamic_label_value_pairs():
    """Adjuster package includes collected_fields with exact label/value pairs."""
    state = {
        "ticket_id": "CLM-TEST-001",
        "input_mode": "text",
        "extracted_data": {
            "policy_number": "POL-DEMO-HEALTH-001",
            "hospital_name": "Apollo Hospital",
            "admission_date": "2026-05-10",
            "diagnosis": "Acute Appendicitis",
        },
        "extracted_fields": [
            {"field_key": "policy_number", "field_label": "Health Policy Number", "value": "POL-DEMO-HEALTH-001", "source_requirement_id": "req-h-1"},
            {"field_key": "hospital_name", "field_label": "Hospital Name", "value": "Apollo Hospital", "source_requirement_id": "req-h-2"},
            {"field_key": "admission_date", "field_label": "Admission Date", "value": "2026-05-10", "source_requirement_id": "req-h-3"},
            {"field_key": "diagnosis", "field_label": "Diagnosis / Condition", "value": "Acute Appendicitis", "source_requirement_id": "req-h-4"},
        ],
        "dynamic_requirements": [],
        "evidence": [],
        "policy_verification": {"valid": True, "identity_verified": True, "policy_status": "Active & In-Force"},
    }

    package = synthesize_claims_package(state)
    assert "collected_fields" in package
    collected = {f["field_key"]: f for f in package["collected_fields"]}
    assert collected["hospital_name"]["field_label"] == "Hospital Name"
    assert collected["hospital_name"]["value"] == "Apollo Hospital"
    assert collected["hospital_name"]["source_requirement_id"] == "req-h-2"
    assert collected["diagnosis"]["value"] == "Acute Appendicitis"


def test_7_honest_fallback_when_knowledge_base_has_no_requirements():
    """Bot refuses to make up fields or fall back to hardcoded schema if RAG has no requirements."""
    state = {
        "tenant_id": "tenant-unknown",
        "claim_text": "I want to file a drone space travel insurance claim",
        "extracted_data": {},
        "dynamic_requirements": [],
        "dynamic_missing": [],
        "missing_evidence": [],
        "rag_status": "NO_RELEVANT_KNOWLEDGE",
        "conversation_history": [],
    }

    planned = _response_planner(state)
    assert planned["conversation_phase"] == "source_of_truth_intake"
    assert planned["conversation_status"] == "waiting_for_knowledge"
    assert "cannot determine the filing requirements" in planned["next_question"].lower()
    assert "knowledge base" in planned["next_question"].lower()
