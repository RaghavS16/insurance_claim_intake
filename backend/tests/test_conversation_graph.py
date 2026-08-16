"""
Automated unit and conversational integration tests for Review 1:
Natural Voice Insurance Claim Conversation.

Covers:
- Strict 6 insurance types inference: Health, Senior Health, Home, Travel, Motor, Cyber
- Elimination of outdated categories (auto, business)
- Complete free-form multi-field narration
- Quality gate rejecting "you", "yeah", "hello", "okay", and noise from becoming claim data / policy_id
- Follow-up asking ONLY for missing fields
- Conversational confirmation summary and intake completion
"""
import pytest

from src.agents.nodes import (
    conversation_turn_processor,
    claim_extractor,
    mandatory_field_checker,
    next_question_generator,
    _detect_utterance_intent,
    _is_meaningful_claim_utterance,
    _infer_insurance_type,
    _rule_based_fallback_extraction,
    INITIAL_PROMPT,
    CLAIM_TYPE_DISPLAY,
)
from src.agents.graph import build_conversation_graph


def _base_state(**overrides) -> dict:
    state = {
        "claim_text": "",
        "extracted_data": {},
        "missing_fields": ["policy_id", "incident_date", "claim_type", "damage_description", "claimed_amount"],
        "field_status": {},
        "next_question": INITIAL_PROMPT,
        "next_question_field": "",
        "conversation_status": "collecting",
        "awaiting_confirmation": False,
        "confirmed": False,
        "audit_log": [],
        "ticket_id": "CLAIM-TEST001",
    }
    state.update(overrides)
    return state


class TestSixInsuranceTypesInference:
    """Validate strict inference of ONLY the 6 supported insurance types."""

    def test_infer_motor(self):
        assert _infer_insurance_type("My car was hit from behind.") == "motor"
        assert _infer_insurance_type("There was a collision and my bumper got dented.") == "motor"
        assert _infer_insurance_type("I met with an accident on my bike yesterday.") == "motor"

    def test_infer_travel(self):
        assert _infer_insurance_type("I lost my luggage while travelling.") == "travel"
        assert _infer_insurance_type("My flight was delayed and baggage was missing.") == "travel"

    def test_infer_home(self):
        assert _infer_insurance_type("My house was damaged by a fire.") == "home"
        assert _infer_insurance_type("There is a water leak in my apartment roof.") == "home"

    def test_infer_health(self):
        assert _infer_insurance_type("I was hospitalized.") == "health"
        assert _infer_insurance_type("I had an emergency surgery at the clinic.") == "health"

    def test_infer_senior_health(self):
        assert _infer_insurance_type("My father needs hospitalization.") == "senior_health"
        assert _infer_insurance_type("My elderly mother was admitted to ICU.") == "senior_health"
        assert _infer_insurance_type("Claim for my grandmother's medical treatment.") == "senior_health"

    def test_infer_cyber(self):
        assert _infer_insurance_type("My computer was hacked.") == "cyber"
        assert _infer_insurance_type("We suffered a ransomware attack on our server.") == "cyber"


class TestInputQualityGate:
    """Validate that noise, greetings, and filler words NEVER become claim data."""

    def test_empty_string_rejected(self):
        assert not _is_meaningful_claim_utterance("")
        assert not _is_meaningful_claim_utterance("   ")

    def test_single_filler_words_rejected(self):
        assert not _is_meaningful_claim_utterance("you")
        assert not _is_meaningful_claim_utterance("YOU")
        assert not _is_meaningful_claim_utterance("yeah")
        assert not _is_meaningful_claim_utterance("okay")
        assert not _is_meaningful_claim_utterance("uh")
        assert not _is_meaningful_claim_utterance("um")

    def test_greetings_rejected(self):
        assert not _is_meaningful_claim_utterance("hello")
        assert not _is_meaningful_claim_utterance("hi")
        assert not _is_meaningful_claim_utterance("hey")

    def test_meaningful_claim_utterances_accepted(self):
        assert _is_meaningful_claim_utterance("My car was hit from behind yesterday")
        assert _is_meaningful_claim_utterance("ABC12345")
        assert _is_meaningful_claim_utterance("50000 rupees")
        assert _is_meaningful_claim_utterance("I lost my luggage while travelling")


class TestIntentDetection:
    def test_affirmation_intents(self):
        assert _detect_utterance_intent("yes") == "affirmation"
        assert _detect_utterance_intent("looks good") == "affirmation"
        assert _detect_utterance_intent("everything is correct") == "affirmation"
        assert _detect_utterance_intent("confirm") == "affirmation"

    def test_rejection_intents(self):
        assert _detect_utterance_intent("no") == "rejection"
        assert _detect_utterance_intent("that's wrong") == "rejection"
        assert _detect_utterance_intent("incorrect") == "rejection"

    def test_repeat_intents(self):
        assert _detect_utterance_intent("Could you repeat that?") == "repeat"
        assert _detect_utterance_intent("Say that again please") == "repeat"
        assert _detect_utterance_intent("what?") == "repeat"

    def test_correction_intents(self):
        assert _detect_utterance_intent("Actually, it was 50000") == "correction"
        assert _detect_utterance_intent("sorry, i meant the 15th") == "correction"
        assert _detect_utterance_intent("make the amount 60,000") == "correction"

    def test_dont_know_and_defer_intents(self):
        assert _detect_utterance_intent("I don't know") == "dont_know"
        assert _detect_utterance_intent("not sure") == "dont_know"
        assert _detect_utterance_intent("I'll provide it later") == "defer"


class TestReview1Conversations:
    # 1. Transcript = "you" -> must NEVER store policy_id = "YOU"
    def test_you_never_stored_as_policy(self):
        graph = build_conversation_graph()
        state = _base_state(claim_text="you")
        result = graph.invoke(state)
        assert result["extracted_data"].get("policy_id") != "YOU"
        assert result["extracted_data"].get("policy_id") is None
        assert "policy_id" in result["missing_fields"]

    # 2. Transcript = "hello" -> friendly prompt, no fake data
    def test_hello_produces_no_fake_claim_data(self):
        graph = build_conversation_graph()
        state = _base_state(claim_text="hello")
        result = graph.invoke(state)
        assert result["extracted_data"] == {}
        assert "tell me what happened" in result["next_question"].lower()

    # 3. Free-form narrative with all 5 fields -> Motor insurance
    def test_motor_claim_free_form_narrative_all_fields(self):
        graph = build_conversation_graph()
        narrative = (
            "Yesterday I was driving my car when another vehicle hit me from behind. "
            "My front bumper was damaged. My policy number is ABC12345 and I think "
            "the damage will cost around 50,000 rupees."
        )
        state = _base_state(claim_text=narrative)
        result = graph.invoke(state)
        extracted = result["extracted_data"]
        assert extracted["policy_id"] == "ABC12345"
        assert extracted["claim_type"] == "motor"
        assert extracted["incident_date"] is not None
        assert extracted["damage_description"] is not None
        assert extracted["claimed_amount"] == 50000.0
        assert result["missing_fields"] == []
        assert result["conversation_status"] == "confirming"
        assert "Motor" in result["next_question"]
        assert "ABC12345" in result["next_question"]
        assert "Does everything look correct?" in result["next_question"]

    # 4. Free-form narrative -> Travel insurance
    def test_travel_claim_free_form(self):
        graph = build_conversation_graph()
        narrative = "I lost my luggage while travelling yesterday. Policy TRV9912. The lost baggage is worth 35000 rupees."
        state = _base_state(claim_text=narrative)
        result = graph.invoke(state)
        extracted = result["extracted_data"]
        assert extracted["claim_type"] == "travel"
        assert extracted["policy_id"] == "TRV9912"
        assert extracted["claimed_amount"] == 35000.0
        assert result["conversation_status"] == "confirming"
        assert "Travel" in result["next_question"]

    # 5. Free-form narrative -> Senior Health insurance
    def test_senior_health_claim_free_form(self):
        graph = build_conversation_graph()
        narrative = "My father needs hospitalization for knee surgery on 2026-08-10. Policy SNR881. Total estimated bill is 150000 rupees."
        state = _base_state(claim_text=narrative)
        result = graph.invoke(state)
        extracted = result["extracted_data"]
        assert extracted["claim_type"] == "senior_health"
        assert extracted["policy_id"] == "SNR881"
        assert extracted["claimed_amount"] == 150000.0
        assert result["conversation_status"] == "confirming"
        assert "Senior Health" in result["next_question"]

    # 6. Free-form narrative -> Cyber insurance
    def test_cyber_claim_free_form(self):
        graph = build_conversation_graph()
        narrative = "My computer was hacked on 2026-08-12 and files encrypted by ransomware. Policy CYB404. Loss is 80000 rupees."
        state = _base_state(claim_text=narrative)
        result = graph.invoke(state)
        extracted = result["extracted_data"]
        assert extracted["claim_type"] == "cyber"
        assert extracted["policy_id"] == "CYB404"
        assert extracted["claimed_amount"] == 80000.0
        assert result["conversation_status"] == "confirming"
        assert "Cyber" in result["next_question"]

    # 7. Partial narrative -> Asks ONLY for missing fields without robotic questionnaire
    def test_partial_narrative_asks_only_missing(self):
        graph = build_conversation_graph()
        narrative = "Yesterday my house was damaged by a fire in the kitchen."
        state = _base_state(claim_text=narrative)
        result = graph.invoke(state)
        extracted = result["extracted_data"]
        assert extracted["claim_type"] == "home"
        assert extracted["incident_date"] is not None
        assert "policy_id" in result["missing_fields"]
        assert "claimed_amount" in result["missing_fields"]
        assert result["next_question_field"] == "policy_id"
        # Does not ask if it's auto/business or when it happened again
        assert "auto, home, or business" not in result["next_question"].lower()
        assert "policy" in result["next_question"].lower()

    # 8. User corrects value during confirmation
    def test_user_corrects_value_during_confirmation(self):
        graph = build_conversation_graph()
        state = _base_state(
            claim_text="Actually, make the amount 60,000.",
            conversation_status="confirming",
            awaiting_confirmation=True,
            extracted_data={
                "policy_id": "ABC12345",
                "incident_date": "2026-08-15",
                "claim_type": "motor",
                "damage_description": "Front bumper damaged",
                "claimed_amount": 50000.0,
            },
            field_status={
                "policy_id": "provided",
                "incident_date": "provided",
                "claim_type": "provided",
                "damage_description": "provided",
                "claimed_amount": "provided",
            },
        )
        result = graph.invoke(state)
        assert result["extracted_data"]["claimed_amount"] == 60000.0
        assert result["conversation_status"] == "confirming"
        assert "60,000" in result["next_question"]

    # 9. User confirms -> Review 1 stops and seals intake
    def test_user_confirms_completes_review_1(self):
        graph = build_conversation_graph()
        state = _base_state(
            claim_text="Yes, everything looks correct.",
            conversation_status="confirming",
            awaiting_confirmation=True,
            extracted_data={
                "policy_id": "ABC12345",
                "incident_date": "2026-08-15",
                "claim_type": "motor",
                "damage_description": "Front bumper damaged",
                "claimed_amount": 60000.0,
            },
            field_status={
                "policy_id": "provided",
                "incident_date": "provided",
                "claim_type": "provided",
                "damage_description": "provided",
                "claimed_amount": "provided",
            },
        )
        result = graph.invoke(state)
        assert result["conversation_status"] == "intake_complete"
        assert result["confirmed"] is True
        assert "CLAIM-TEST001" in result["next_question"]
        assert "complete" in result["next_question"].lower()
