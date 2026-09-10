from src.agents.turn_guard import conversation_turn_processor
from src.agents import graph


def _state(text, **extra):
    state = {
        "claim_text": text,
        "extracted_data": {},
        "conversation_history": [],
        "field_status": {},
        "field_metadata": {},
        "awaiting_confirmation": False,
        "confirmed": False,
    }
    state.update(extra)
    return state


def test_audio_question_gets_audio_answer_not_policy_question():
    result = conversation_turn_processor(_state("Can you hear me right?"))
    assert result["message"] == "Yes, I can hear you clearly. Go ahead."
    assert result["_skip_all"] is True
    assert result["extracted_data"] == {}


def test_unrelated_question_does_not_advance_missing_claim_field():
    result = conversation_turn_processor(_state("Why did he ask Koshy to be?"))
    assert result["_skip_all"] is True
    assert "policy number" not in result["message"].lower()
    assert result["extracted_data"] == {}


def test_natural_claim_prompt_groups_missing_baseline_fields():
    state = _state("I had a bike accident yesterday in Chennai and repair cost is 12000.")
    state["extracted_data"] = {
        "event_description": "I had a bike accident",
        "event_date": "2026-09-09",
        "event_location": "Chennai",
        "estimated_claim_amount": 12000,
        "insurance_type": "motor",
    }
    state["missing_fields"] = ["policy_id"]
    result = graph._response_planner(state)
    assert result["next_question_field"] == "policy_id"
    assert "policy number" in result["message"].lower()
    assert "what is your policy number?" not in result["message"].lower()


def test_confirmation_is_natural_and_grounded():
    state = _state("", extracted_data={
        "insurance_type": "motor",
        "event_description": "My bike was damaged in an accident",
        "event_date": "2026-09-09",
        "event_location": "Chennai",
        "estimated_claim_amount": 12000,
        "policy_id": "POL-1409-XI",
    }, awaiting_confirmation=True)
    result = graph._response_planner(state)
    assert result["message"].startswith("Got it. I’ve captured your motor claim:")
    assert "POL-1409-XI" in result["message"]
    assert "Does that look right?" in result["message"]
