"""
Automated unit and conversational integration tests for Phase 1:
Voice-First Insurance Claim Intake.

Covers:
- Strict 6 insurance types inference: Health, Senior Health, Home, Travel, Motor, Cyber
- Elimination of outdated categories (auto, business)
- Complete free-form multi-field narration
- Quality gate rejecting "you", "yeah", "hello", "okay", and noise from becoming claim data
- Follow-up asking ONLY for missing fields
- Conversational confirmation summary and intake completion
- Bike accident smoke test scenario
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
        assert _infer_insurance_type("I had a bike accident yesterday and the front of my bike was damaged.") == "motor"

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
        assert _detect_utterance_intent("I don't know") == "defer"
        assert _detect_utterance_intent("not sure") == "defer"
        assert _detect_utterance_intent("I'll provide it later") == "defer"


class TestPhase1Conversations:
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

        data = result["extracted_data"]
        assert data["claim_type"] == "motor"
        assert data["policy_id"] == "ABC12345"
        assert data["claimed_amount"] == 50000.0
        assert data["incident_date"] is not None
        assert "bumper" in data["damage_description"].lower()
        assert result["missing_fields"] == []
        assert result["awaiting_confirmation"] is True
        assert "does everything look correct" in result["next_question"].lower()

    # 4. Free-form travel claim
    def test_travel_claim_free_form(self):
        graph = build_conversation_graph()
        narrative = "I lost my luggage while travelling yesterday. Policy TRV-3301. Estimated loss is 25000 rupees."
        state = _base_state(claim_text=narrative)
        result = graph.invoke(state)

        data = result["extracted_data"]
        assert data["claim_type"] == "travel"
        assert data["policy_id"] == "TRV-3301"
        assert data["claimed_amount"] == 25000.0
        assert result["missing_fields"] == []

    # 5. Free-form senior health claim
    def test_senior_health_claim_free_form(self):
        graph = build_conversation_graph()
        narrative = "My elderly father was admitted to hospital yesterday. Policy SNR-9912. The hospital bill is 80000 rupees for surgery."
        state = _base_state(claim_text=narrative)
        result = graph.invoke(state)

        data = result["extracted_data"]
        assert data["claim_type"] == "senior_health"
        assert data["policy_id"] == "SNR-9912"
        assert data["claimed_amount"] == 80000.0

    # 6. Free-form cyber claim
    def test_cyber_claim_free_form(self):
        graph = build_conversation_graph()
        narrative = "Our office server was hacked yesterday in a ransomware attack. Policy CYB-8820. Estimated recovery cost is 150000 rupees."
        state = _base_state(claim_text=narrative)
        result = graph.invoke(state)

        data = result["extracted_data"]
        assert data["claim_type"] == "cyber"
        assert data["policy_id"] == "CYB-8820"
        assert data["claimed_amount"] == 150000.0

    # 7. Partial narrative: asks only for missing fields
    def test_partial_narrative_asks_only_missing(self):
        graph = build_conversation_graph()
        narrative = "I met with a bike accident yesterday and damaged my front wheel. Policy MOT-5521."
        state = _base_state(claim_text=narrative)
        result = graph.invoke(state)

        data = result["extracted_data"]
        assert data["claim_type"] == "motor"
        assert data["policy_id"] == "MOT-5521"
        assert "claimed_amount" in result["missing_fields"]
        assert "policy_id" not in result["missing_fields"]
        assert "incident_date" not in result["missing_fields"]
        assert "estimate" in result["next_question"].lower() or "cost" in result["next_question"].lower() or "loss" in result["next_question"].lower()

    # 8. User correction during confirmation
    def test_user_corrects_value_during_confirmation(self):
        graph = build_conversation_graph()
        state = _base_state(
            extracted_data={
                "claim_type": "motor",
                "policy_id": "ABC12345",
                "incident_date": "2025-07-15",
                "damage_description": "Car bumper dented",
                "claimed_amount": 50000.0,
            },
            missing_fields=[],
            awaiting_confirmation=True,
            claim_text="Actually, make the amount 65000 rupees",
        )
        result = graph.invoke(state)
        assert result["extracted_data"]["claimed_amount"] == 65000.0
        assert result["awaiting_confirmation"] is True

    # 9. User confirms claim details -> intake complete
    def test_user_confirms_completes_phase_1(self):
        graph = build_conversation_graph()
        state = _base_state(
            extracted_data={
                "claim_type": "motor",
                "policy_id": "ABC12345",
                "incident_date": "2025-07-15",
                "damage_description": "Car bumper dented",
                "claimed_amount": 50000.0,
            },
            missing_fields=[],
            awaiting_confirmation=True,
            claim_text="Yes, that is correct",
        )
        result = graph.invoke(state)
        assert result["confirmed"] is True
        assert result["conversation_status"] == "claimant_confirmed"
        assert "confirmed" in result["next_question"].lower()

    # 10. Smoke test scenario: "I had a bike accident yesterday and the front of my bike was damaged."
    def test_smoke_test_bike_accident_flow(self):
        graph = build_conversation_graph()

        # Step 1: Initial user utterance
        turn1_state = _base_state(claim_text="I had a bike accident yesterday and the front of my bike was damaged.")
        res1 = graph.invoke(turn1_state)

        assert res1["extracted_data"]["claim_type"] == "motor"
        assert res1["extracted_data"]["incident_date"] is not None
        assert "bike" in res1["extracted_data"]["damage_description"].lower()
        assert "policy_id" in res1["missing_fields"]
        assert "claimed_amount" in res1["missing_fields"]
        assert res1["awaiting_confirmation"] is False

        # Step 2: Claimant provides policy number
        turn2_state = {**res1, "claim_text": "My policy number is MOT-5521"}
        res2 = graph.invoke(turn2_state)

        assert res2["extracted_data"]["policy_id"] == "MOT-5521"
        assert "claimed_amount" in res2["missing_fields"]
        assert "policy_id" not in res2["missing_fields"]

        # Step 3: Claimant provides estimated loss amount
        turn3_state = {**res2, "claim_text": "The estimated repair cost is 15000 rupees"}
        res3 = graph.invoke(turn3_state)

        assert res3["extracted_data"]["claimed_amount"] == 15000.0
        assert res3["missing_fields"] == []
        assert res3["awaiting_confirmation"] is True
        assert "does everything look correct" in res3["next_question"].lower()

        # Step 4: Claimant confirms
        turn4_state = {**res3, "claim_text": "Yes, everything looks good."}
        res4 = graph.invoke(turn4_state)

        assert res4["confirmed"] is True
        assert res4["conversation_status"] == "claimant_confirmed"
        assert "confirmed" in res4["next_question"].lower()

    # 11. Test thank you after completion bug fix
    def test_thank_you_after_completion_short_circuits(self):
        graph = build_conversation_graph()
        
        # Test claimant_confirmed status
        state1 = _base_state(
            conversation_status="claimant_confirmed",
            extracted_data={
                "claim_type": "motor",
                "policy_id": "ABC12345",
                "incident_date": "2025-07-15",
                "damage_description": "Car bumper dented",
                "claimed_amount": 50000.0,
            },
            missing_fields=[],
            awaiting_confirmation=False,
            confirmed=True,
            claim_text="thank you",
        )
        res1 = graph.invoke(state1)
        assert res1["conversation_status"] == "claimant_confirmed"
        assert "welcome" in res1["next_question"].lower()
        # Ensure we didn't re-emit summary
        assert "policy id" not in res1["next_question"].lower()
        assert "insurance type" not in res1["next_question"].lower()

        # Test completed status
        state2 = _base_state(
            conversation_status="completed",
            extracted_data={
                "claim_type": "motor",
                "policy_id": "ABC12345",
                "incident_date": "2025-07-15",
                "damage_description": "Car bumper dented",
                "claimed_amount": 50000.0,
            },
            missing_fields=[],
            awaiting_confirmation=False,
            confirmed=True,
            claim_text="bye",
        )
        res2 = graph.invoke(state2)
        assert res2["conversation_status"] == "completed"
        assert "goodbye" in res2["next_question"].lower()

    # 12. Correction utterance after confirmation
    def test_correction_after_confirmation_does_not_regress_status(self):
        graph = build_conversation_graph()
        state = _base_state(
            conversation_status="claimant_confirmed",
            extracted_data={
                "claim_type": "motor",
                "policy_id": "ABC12345",
                "incident_date": "2025-07-15",
                "damage_description": "Car bumper dented",
                "claimed_amount": 50000.0,
            },
            missing_fields=[],
            awaiting_confirmation=False,
            confirmed=True,
            claim_text="Actually, make the amount 60000 rupees",
        )
        result = graph.invoke(state)
        # It should update the field but not regress to collecting
        assert result["extracted_data"]["claimed_amount"] == 60000.0
        assert result["conversation_status"] in ("claimant_confirmed", "confirming", "completed")
        # Ensure it doesn't drop to collecting
        assert result["conversation_status"] != "collecting"

    # 13. Test LLM fallback
    def test_llm_offline_fallback_produces_non_empty_message(self):
        graph = build_conversation_graph()
        state = _base_state(
            claim_text="I had a bike accident yesterday.",
        )
        # Even though LLM raises ConnectionError via mock, fallback string should be returned
        result = graph.invoke(state)
        assert result["next_question"]
        assert len(result["next_question"]) > 5
        assert result["message"]
        assert len(result["message"]) > 5

