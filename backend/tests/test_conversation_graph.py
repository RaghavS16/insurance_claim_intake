"""
Tests for the Review 1 conversation graph: conversation_turn_processor,
next_question_generator, document_request_generator, intake_completion_marker,
and the full conversation graph routing.

Covers the cases described in §13.2 of REVIEW1_VOICE_IMPLEMENTATION.md:
  - normal turn  (field gets extracted, next question is phrased)
  - correction turn (locked field is unlocked for re-extraction)
  - don't-know turn (field marked UNKNOWN_SENTINEL, not re-asked)
  - repeat turn (existing next_question re-emitted, extraction skipped)
  - missing-documents turn (document_request_generator fires)
  - intake-complete turn (all fields+docs present, intake_completion_marker fires)

These tests exercise the nodes in isolation where possible (no LLM call needed)
and only invoke the full graph for end-to-end routing checks.
"""
import pytest

from src.agents.nodes import (
    conversation_turn_processor,
    next_question_generator,
    document_request_generator,
    intake_completion_marker,
    UNKNOWN_SENTINEL,
    _detect_utterance_intent,
    FIELD_PROMPTS,
)
from src.agents.graph import build_conversation_graph


# ---------------------------------------------------------------------------
# _detect_utterance_intent (pure function, no side effects)
# ---------------------------------------------------------------------------

class TestDetectUtteranceIntent:
    def test_normal(self):
        assert _detect_utterance_intent("My policy is XYZ123") == "normal"

    def test_repeat(self):
        assert _detect_utterance_intent("Could you repeat that?") == "repeat"
        assert _detect_utterance_intent("Say that again please") == "repeat"
        assert _detect_utterance_intent("come again?") == "repeat"

    def test_correction(self):
        assert _detect_utterance_intent("Actually, it was 50000") == "correction"
        assert _detect_utterance_intent("sorry, i meant the 15th") == "correction"
        assert _detect_utterance_intent("scratch that, I said that wrong") == "correction"

    def test_dont_know(self):
        assert _detect_utterance_intent("I don't know") == "dont_know"
        assert _detect_utterance_intent("not sure about that") == "dont_know"
        assert _detect_utterance_intent("I'll check") == "dont_know"

    def test_defer(self):
        assert _detect_utterance_intent("later") == "defer"
        assert _detect_utterance_intent("not right now") == "defer"
        assert _detect_utterance_intent("I'll provide it later") == "defer"


# ---------------------------------------------------------------------------
# conversation_turn_processor
# ---------------------------------------------------------------------------

def _base_state(**overrides) -> dict:
    """Return a minimal ClaimState dict for testing."""
    state = {
        "claim_text": "",
        "extracted_data": {},
        "next_question": "What is your policy number?",
        "next_question_field": "policy_id",
        "audit_log": [],
    }
    state.update(overrides)
    return state


class TestConversationTurnProcessor:
    def test_normal_sets_skip_false(self):
        state = _base_state(claim_text="My policy is XYZ123")
        result = conversation_turn_processor(state)
        assert result["_skip_extraction"] is False
        assert result["last_user_utterance"] == "My policy is XYZ123"

    def test_repeat_sets_skip_true(self):
        state = _base_state(claim_text="repeat that please")
        result = conversation_turn_processor(state)
        assert result["_skip_extraction"] is True
        assert result["conversation_status"] == "in_progress"

    def test_dont_know_marks_field_unknown(self):
        state = _base_state(
            claim_text="I don't know",
            next_question_field="policy_id",
        )
        result = conversation_turn_processor(state)
        assert result["extracted_data"]["policy_id"] == UNKNOWN_SENTINEL
        assert "policy_id" in result["unknown_fields"]
        assert result["_skip_extraction"] is True

    def test_defer_marks_field_unknown(self):
        state = _base_state(
            claim_text="not right now",
            next_question_field="claimed_amount",
        )
        result = conversation_turn_processor(state)
        assert result["extracted_data"]["claimed_amount"] == UNKNOWN_SENTINEL
        assert "claimed_amount" in result["unknown_fields"]

    def test_correction_unlocks_field(self):
        state = _base_state(
            claim_text="actually, I meant 75000",
            next_question_field="claimed_amount",
            extracted_data={"claimed_amount": 50000.0},  # previously locked value
        )
        result = conversation_turn_processor(state)
        # Field should be nulled out (unlocked), _skip_extraction=False so
        # claim_extractor will get to re-extract with the corrected text.
        assert result["extracted_data"]["claimed_amount"] is None
        assert result["_skip_extraction"] is False

    def test_dont_know_no_target_field_falls_through_normal(self):
        """If there's no target field, don't-know should be treated as normal."""
        state = _base_state(
            claim_text="I don't know",
            next_question_field=None,  # no field being asked
        )
        result = conversation_turn_processor(state)
        # Should fall through to normal since target_field is falsy
        assert result["_skip_extraction"] is False


# ---------------------------------------------------------------------------
# next_question_generator
# ---------------------------------------------------------------------------

class TestNextQuestionGenerator:
    def test_picks_first_missing_field(self):
        state = _base_state(
            missing_fields=["policy_id", "incident_date", "claim_type"],
            _skip_extraction=False,
        )
        result = next_question_generator(state)
        assert result["next_question_field"] == "policy_id"
        assert result["next_question"] == FIELD_PROMPTS["policy_id"]
        assert result["conversation_status"] == "in_progress"

    def test_no_missing_fields_clears_question(self):
        state = _base_state(missing_fields=[], _skip_extraction=False)
        result = next_question_generator(state)
        assert result["next_question"] == ""
        assert result["next_question_field"] == ""

    def test_repeat_keeps_existing_question(self):
        existing_q = "What is your policy number?"
        state = _base_state(
            _skip_extraction=True,
            next_question=existing_q,
            next_question_field="policy_id",
            missing_fields=["policy_id"],
        )
        result = next_question_generator(state)
        assert result["next_question"] == existing_q
        assert result["next_question_field"] == "policy_id"


# ---------------------------------------------------------------------------
# document_request_generator
# ---------------------------------------------------------------------------

class TestDocumentRequestGenerator:
    def test_requests_missing_documents(self):
        state = _base_state(
            missing_documents=["damage_photo", "repair_estimate"],
        )
        result = document_request_generator(state)
        assert result["awaiting_document_request"] is True
        assert result["conversation_status"] == "awaiting_documents"
        assert "photos of the damage" in result["next_question"]
        assert "repair cost estimate" in result["next_question"]

    def test_no_missing_docs_marks_complete(self):
        state = _base_state(missing_documents=[])
        result = document_request_generator(state)
        assert result["awaiting_document_request"] is False
        assert result["conversation_status"] == "intake_complete"


# ---------------------------------------------------------------------------
# intake_completion_marker
# ---------------------------------------------------------------------------

class TestIntakeCompletionMarker:
    def test_sets_status_and_message(self):
        state = _base_state(ticket_id="CLAIM-ABCD1234")
        result = intake_completion_marker(state)
        assert result["conversation_status"] == "intake_complete"
        assert "CLAIM-ABCD1234" in result["next_question"]
        assert "Thank you" in result["next_question"]


# ---------------------------------------------------------------------------
# Graph routing (end-to-end, no LLM — uses mocked claim_extractor via state)
# ---------------------------------------------------------------------------

class TestConversationGraphRouting:
    """
    These tests bypass the LLM by pre-populating extracted_data so
    claim_extractor's field-locking logic keeps existing values and the
    LLM call doesn't change them.  We then verify that the graph routes
    to the correct terminal node.
    """

    def _all_fields(self) -> dict:
        """Return extracted_data with all required fields filled."""
        return {
            "policy_id": "XYZ123",
            "incident_date": "2025-06-15",
            "claim_type": "business",
            "damage_description": "Office flooded",
            "claimed_amount": 30000.0,
        }

    def test_repeat_turn_skips_extraction(self):
        """'repeat that' should keep the same next_question."""
        graph = build_conversation_graph()
        state = {
            "claim_text": "say that again",
            "extracted_data": {},
            "missing_fields": ["policy_id"],
            "next_question": "What is your policy number?",
            "next_question_field": "policy_id",
            "audit_log": [],
        }
        result = graph.invoke(state)
        assert result["next_question"] == "What is your policy number?"

    def test_intake_complete_turn_for_business_claim(self):
        """business claim needs no documents → should reach intake_completion_marker."""
        graph = build_conversation_graph()
        state = {
            "claim_text": "confirm everything",
            "extracted_data": self._all_fields(),
            "missing_fields": [],
            "next_question": "",
            "audit_log": [],
            "ticket_id": "CLAIM-TEST0001",
            # All fields pre-filled, claim_extractor will field-lock them
        }
        result = graph.invoke(state)
        assert result.get("conversation_status") == "intake_complete"
        assert "CLAIM-TEST0001" in result.get("next_question", "")

    def test_missing_fields_turn_produces_question(self):
        """If fields are missing, should route to next_question_generator."""
        graph = build_conversation_graph()
        state = {
            "claim_text": "hello",
            "extracted_data": {
                "policy_id": "XYZ123",
                "incident_date": "2025-06-15",
                "claim_type": "business",
                "damage_description": "Water damage",
                # claimed_amount missing
            },
            "missing_fields": ["claimed_amount"],
            "next_question": "",
            "audit_log": [],
        }
        result = graph.invoke(state)
        # next_question should target claimed_amount (first missing field)
        assert result.get("next_question_field") == "claimed_amount"
        assert result.get("next_question") != ""

    def test_dont_know_skips_extraction_and_moves_to_next(self):
        """don't know + field currently being asked → mark UNKNOWN, ask next field."""
        graph = build_conversation_graph()
        state = {
            "claim_text": "I don't know",
            "extracted_data": {
                "policy_id": "XYZ123",
                "incident_date": "2025-06-15",
                "claim_type": "auto",
                "damage_description": "Collision",
            },
            "missing_fields": ["claimed_amount"],
            "next_question_field": "claimed_amount",
            "next_question": "What amount are you claiming?",
            "audit_log": [],
        }
        result = graph.invoke(state)
        # claimed_amount should be UNKNOWN_SENTINEL
        assert result["extracted_data"].get("claimed_amount") == UNKNOWN_SENTINEL
        assert "claimed_amount" in result.get("unknown_fields", [])
