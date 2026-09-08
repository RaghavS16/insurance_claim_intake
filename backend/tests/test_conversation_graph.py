"""Production-behavior tests for Phase 1 conversational intake."""
from src.agents.graph import build_conversation_graph


def _state(**overrides):
    state = {
        "claim_text": "",
        "extracted_data": {},
        "missing_fields": [],
        "field_status": {},
        "field_metadata": {},
        "conversation_history": [],
        "conversation_status": "collecting",
        "awaiting_confirmation": False,
        "confirmed": False,
        "ticket_id": "CLAIM-TEST001",
        "audit_log": [],
    }
    state.update(overrides)
    return state


def test_yesterday_is_not_asked_again():
    result = build_conversation_graph().invoke(_state(claim_text="I had a bike accident yesterday and damaged the front of my bike."))
    assert result["extracted_data"]["event_date"] == "2026-09-07"
    assert result["extracted_data"]["insurance_type"] == "motor"
    assert "event_date" not in result["missing_fields"]


def test_free_form_multi_field_narration_extracts_all_supported_facts():
    result = build_conversation_graph().invoke(_state(claim_text="Yesterday I had a bike accident in Bengaluru. Policy MOT-5521. The front of my bike was damaged and repair will cost around ₹20,000."))
    data = result["extracted_data"]
    assert data["event_date"] == "2026-09-07"
    assert data["insurance_type"] == "motor"
    assert data["policy_id"] == "MOT-5521"
    assert data["estimated_claim_amount"] == 20000.0
    assert "bike accident" in data["event_description"].lower()
    assert "event_date" not in result["missing_fields"]
    assert "policy_id" not in result["missing_fields"]
    assert "insurance_type" not in result["missing_fields"]
    assert "estimated_claim_amount" not in result["missing_fields"]


def test_unknown_filler_never_becomes_claim_data():
    result = build_conversation_graph().invoke(_state(claim_text="hello"))
    assert result["extracted_data"] == {}
    assert result["conversation_status"] == "collecting"


def test_all_fields_trigger_review_not_submission():
    result = build_conversation_graph().invoke(_state(
        claim_text="I had a bike accident yesterday in Bengaluru. Policy MOT-5521. Repair cost is ₹20,000.",
    ))
    assert result["missing_fields"] == []
    assert result["awaiting_confirmation"] is True
    assert result["confirmed"] is False
    assert result["conversation_status"] == "reviewing"


def test_confirmation_requires_explicit_affirmation():
    graph = build_conversation_graph()
    first = graph.invoke(_state(
        claim_text="I had a bike accident yesterday in Bengaluru. Policy MOT-5521. Repair cost is ₹20,000.",
    ))
    assert first["awaiting_confirmation"] is True
    second = graph.invoke({**first, "claim_text": "Yes, everything looks correct."})
    assert second["confirmed"] is True
    assert second["conversation_status"] == "pending_verification"
    assert second["awaiting_confirmation"] is False


def test_negative_confirmation_returns_to_collection():
    graph = build_conversation_graph()
    first = graph.invoke(_state(
        claim_text="I had a bike accident yesterday in Bengaluru. Policy MOT-5521. Repair cost is ₹20,000.",
    ))
    second = graph.invoke({**first, "claim_text": "No, the amount is wrong."})
    assert second["confirmed"] is False
    assert second["conversation_status"] == "collecting"


def test_correction_replaces_only_corrected_value():
    graph = build_conversation_graph()
    first = graph.invoke(_state(
        claim_text="I had a bike accident yesterday in Bengaluru. Policy MOT-5521. Repair cost is ₹20,000.",
    ))
    second = graph.invoke({**first, "claim_text": "Actually, the repair cost is ₹25,000."})
    assert second["extracted_data"]["estimated_claim_amount"] == 25000.0
    assert second["extracted_data"]["policy_id"] == "MOT-5521"


def test_thank_you_does_not_restart_or_pollute_collection():
    graph = build_conversation_graph()
    first = graph.invoke(_state(claim_text="I had a bike accident yesterday."))
    second = graph.invoke({**first, "claim_text": "Thank you."})
    assert second["extracted_data"] == first["extracted_data"]
    assert second["conversation_status"] == "collecting"
