from types import SimpleNamespace

from src.agents import graph, nodes
from src.agents.turn_guard import conversation_turn_processor


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


class _FakeResponseLLM:
    def __init__(self, response: str):
        self.response = response

    def invoke(self, _prompt: str):
        return SimpleNamespace(content=self.response)


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


def test_conversational_planner_uses_model_wording_without_reasking_known_fields(monkeypatch):
    state = _state(
        "The bike was damaged yesterday in Chennai and it will cost about 12000 to repair.",
        extracted_data={
            "event_description": "The bike was damaged",
            "event_date": "2026-09-09",
            "event_location": "Chennai",
            "estimated_claim_amount": 12000,
            "insurance_type": "motor",
        },
        missing_fields=["policy_id"],
        last_user_utterance="The bike was damaged yesterday in Chennai and it will cost about 12000 to repair.",
        last_intent="claim_detail",
        conversation_status="collecting",
    )
    monkeypatch.setattr(nodes, "_get_llm", lambda: _FakeResponseLLM("Thanks, I have the incident details. What policy number should I use for this claim?"))
    result = graph._response_planner(state)
    assert result["next_question_field"] == "policy_id"
    assert "policy number" in result["message"].lower()
    assert "date" not in result["message"].lower()
    assert "location" not in result["message"].lower()
    assert "repair" not in result["message"].lower()


def test_confirmation_is_natural_and_grounded():
    state = _state(
        "",
        extracted_data={
            "insurance_type": "motor",
            "event_description": "My bike was damaged in an accident",
            "event_date": "2026-09-09",
            "event_location": "Chennai",
            "estimated_claim_amount": 12000,
            "policy_id": "POL-1409-XI",
        },
        awaiting_confirmation=True,
    )
    result = graph._response_planner(state)
    assert result["message"].startswith("I have your motor claim for My bike was damaged in an accident")
    assert "POL-1409-XI" in result["message"]
    assert "Is everything correct?" in result["message"]
