"""Behavioral tests for natural claim intake."""
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


def test_free_form_multi_field_narration_extracts_all_supported_facts():
    result = build_conversation_graph().invoke(_state(
        claim_text="Yesterday I had a bike accident in Bengaluru. Policy MOT-5521. The front of my bike was damaged and repair will cost around ₹20,000."
    ))
    data = result["extracted_data"]
    assert data["event_date"] == "2026-09-07"
    assert data["insurance_type"] == "motor"
    assert data["policy_id"] == "MOT-5521"
    assert data["estimated_claim_amount"] == 20000.0
    assert "bike accident" in data["event_description"].lower()
    assert "MOT-5521" not in data["event_description"]


def test_social_turn_never_becomes_event_description():
    first = build_conversation_graph().invoke(_state(claim_text="I had a bike accident yesterday."))
    second = build_conversation_graph().invoke({**first, "claim_text": "Thank you."})
    assert second["extracted_data"] == first["extracted_data"]
    assert second["conversation_status"] == first["conversation_status"]
    assert "thank" not in second["extracted_data"].get("event_description", "").lower()


def test_greeting_is_conversational_and_does_not_add_data():
    result = build_conversation_graph().invoke(_state(claim_text="Hello"))
    assert result["extracted_data"] == {}
    assert result["last_intent"] == "greeting"
    assert "claim" not in result["extracted_data"]


def test_process_question_without_polluting_claim():
    state = _state(claim_text="What documents will I need later?")
    result = build_conversation_graph().invoke(state)
    assert result["extracted_data"] == {}
    assert result["last_intent"] == "question"


def test_all_baseline_fields_trigger_review_not_submission():
    result = build_conversation_graph().invoke(_state(
        claim_text="I had a bike accident yesterday in Bengaluru. Policy MOT-5521. Repair cost is ₹20,000."
    ))
    assert result["missing_fields"] == []
    assert result["awaiting_confirmation"] is True
    assert result["confirmed"] is False
    assert result["conversation_status"] == "reviewing"


def test_confirmation_requires_explicit_affirmation():
    graph = build_conversation_graph()
    first = graph.invoke(_state(
        claim_text="I had a bike accident yesterday in Bengaluru. Policy MOT-5521. Repair cost is ₹20,000."
    ))
    second = graph.invoke({**first, "claim_text": "Yes, everything looks correct."})
    assert second["confirmed"] is True
    assert second["conversation_status"] == "pending_verification"
    assert second["awaiting_confirmation"] is False


def test_negative_confirmation_returns_to_collection():
    graph = build_conversation_graph()
    first = graph.invoke(_state(
        claim_text="I had a bike accident yesterday in Bengaluru. Policy MOT-5521. Repair cost is ₹20,000."
    ))
    second = graph.invoke({**first, "claim_text": "No, the amount is wrong."})
    assert second["confirmed"] is False
    assert second["conversation_status"] == "collecting"


def test_correction_replaces_only_corrected_value():
    graph = build_conversation_graph()
    first = graph.invoke(_state(
        claim_text="I had a bike accident yesterday in Bengaluru. Policy MOT-5521. Repair cost is ₹20,000."
    ))
    second = graph.invoke({**first, "claim_text": "Actually, the repair cost is ₹25,000."})
    assert second["extracted_data"]["estimated_claim_amount"] == 25000.0
    assert second["extracted_data"]["policy_id"] == "MOT-5521"


def test_facts_already_extracted_are_not_reasked():
    graph = build_conversation_graph()
    first = graph.invoke(_state(claim_text="I had a bike accident yesterday."))
    second = graph.invoke({**first, "claim_text": "It happened in Bengaluru and the repair is around ₹20,000."})
    assert second["extracted_data"]["event_date"] == "2026-09-07"
    assert second["extracted_data"]["event_location"] == "Bengaluru"
    assert second["extracted_data"]["estimated_claim_amount"] == 20000.0
    assert "event_date" not in second["missing_fields"]
