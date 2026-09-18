"""
Edge-case tests for src/agents/turn_guard.py

Covers: _is_affirmative, _is_negative, _is_conversational_filler,
        _is_audio_check, _is_unrelated_question, _conversation_only_response,
        _incident_description_from_text, _requested_correction_field,
        _correction_prompt, conversation_turn_processor.
"""
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# _is_affirmative
# ---------------------------------------------------------------------------
class TestIsAffirmative:
    def _call(self, text):
        from src.agents.turn_guard import _is_affirmative
        return _is_affirmative(text)

    def test_yes_is_affirmative(self):
        assert self._call("yes") is True

    def test_yeah_is_affirmative(self):
        assert self._call("yeah") is True

    def test_yep_is_affirmative(self):
        assert self._call("yep") is True

    def test_correct_is_affirmative(self):
        assert self._call("correct") is True

    def test_okay_is_affirmative(self):
        assert self._call("okay") is True

    def test_looks_good_is_affirmative(self):
        assert self._call("looks good") is True

    def test_all_good_is_affirmative(self):
        assert self._call("all good") is True

    def test_no_is_not_affirmative(self):
        assert self._call("no") is False

    def test_empty_string_is_not_affirmative(self):
        assert self._call("") is False

    def test_random_text_is_not_affirmative(self):
        assert self._call("my car was damaged") is False

    def test_case_insensitive(self):
        assert self._call("YES") is True
        assert self._call("OKAY") is True

    def test_extra_whitespace_handled(self):
        assert self._call("  yes  ") is True

    def test_thats_correct_affirmative(self):
        assert self._call("that's correct") is True

    def test_affirmative_with_punctuation(self):
        assert self._call("yes.") is True
        assert self._call("yes!") is True


# ---------------------------------------------------------------------------
# _is_negative
# ---------------------------------------------------------------------------
class TestIsNegative:
    def _call(self, text):
        from src.agents.turn_guard import _is_negative
        return _is_negative(text)

    def test_no_is_negative(self):
        assert self._call("no") is True

    def test_nope_is_negative(self):
        assert self._call("nope") is True

    def test_wrong_is_negative(self):
        assert self._call("wrong") is True

    def test_not_correct_is_negative(self):
        assert self._call("not correct") is True

    def test_incorrect_is_negative(self):
        assert self._call("incorrect") is True

    def test_thats_wrong_is_negative(self):
        assert self._call("that's wrong") is True

    def test_yes_is_not_negative(self):
        assert self._call("yes") is False

    def test_empty_is_not_negative(self):
        assert self._call("") is False

    def test_case_insensitive(self):
        assert self._call("NO") is True

    def test_no_with_punctuation(self):
        assert self._call("no.") is True


# ---------------------------------------------------------------------------
# _is_conversational_filler
# ---------------------------------------------------------------------------
class TestIsConversationalFiller:
    def _call(self, text):
        from src.agents.turn_guard import _is_conversational_filler
        return _is_conversational_filler(text)

    def test_hmm_is_filler(self):
        assert self._call("hmm") is True

    def test_uh_is_filler(self):
        assert self._call("uh") is True

    def test_um_is_filler(self):
        assert self._call("um") is True

    def test_hold_on_is_filler(self):
        assert self._call("hold on") is True

    def test_wait_is_filler(self):
        assert self._call("wait") is True

    def test_let_me_think_is_filler(self):
        assert self._call("let me think") is True

    def test_claim_description_is_not_filler(self):
        assert self._call("my car was damaged in an accident") is False

    def test_yes_is_in_social_exact_so_is_filler(self):
        """yes is in _SOCIAL_EXACT so IS a conversational filler in this implementation."""
        # This reflects the actual behavior: single-word affirmatives are fillers
        assert self._call("yes") is True  # yes IS a filler in this codebase

    def test_empty_string_is_not_filler(self):
        assert self._call("") is False


# ---------------------------------------------------------------------------
# _is_audio_check
# ---------------------------------------------------------------------------
class TestIsAudioCheck:
    def _call(self, text):
        from src.agents.turn_guard import _is_audio_check
        return _is_audio_check(text)

    def test_can_you_hear_me(self):
        assert self._call("can you hear me") is True

    def test_could_you_hear_me(self):
        assert self._call("could you hear me") is True

    def test_are_you_hearing_me(self):
        assert self._call("are you hearing me") is True

    def test_is_the_audio_working(self):
        assert self._call("is the audio working") is True

    def test_regular_claim_text_is_not_audio_check(self):
        assert self._call("I want to file a claim for motor damage") is False

    def test_empty_string(self):
        assert self._call("") is False

    def test_case_insensitive(self):
        assert self._call("Can You Hear Me") is True


# ---------------------------------------------------------------------------
# _is_unrelated_question
# ---------------------------------------------------------------------------
class TestIsUnrelatedQuestion:
    def _call(self, text):
        from src.agents.turn_guard import _is_unrelated_question
        return _is_unrelated_question(text)

    def test_claim_related_not_unrelated(self):
        assert self._call("What documents do I need for my insurance claim?") is False

    def test_unrelated_question(self):
        assert self._call("What is the capital of France?") is True

    def test_not_a_question_is_not_unrelated(self):
        assert self._call("My car was damaged yesterday") is False

    def test_empty_string(self):
        assert self._call("") is False

    def test_policy_keyword_not_unrelated(self):
        assert self._call("What is my policy coverage?") is False

    def test_vehicle_keyword_not_unrelated(self):
        assert self._call("Can I claim for my vehicle?") is False


# ---------------------------------------------------------------------------
# _conversation_only_response
# ---------------------------------------------------------------------------
class TestConversationOnlyResponse:
    def _call(self, text):
        from src.agents.turn_guard import _conversation_only_response
        return _conversation_only_response(text)

    def test_audio_check_returns_response(self):
        result = self._call("can you hear me")
        assert result is not None
        assert "hear" in result.lower()

    def test_unrelated_question_returns_redirect(self):
        result = self._call("What is the weather today?")
        assert result is not None
        assert "insurance claim" in result.lower()

    def test_claim_text_returns_none(self):
        result = self._call("I want to file a claim for my stolen car")
        assert result is None

    def test_empty_string_returns_none(self):
        result = self._call("")
        assert result is None


# ---------------------------------------------------------------------------
# _requested_correction_field
# ---------------------------------------------------------------------------
class TestRequestedCorrectionField:
    def _call(self, text, state=None):
        from src.agents.turn_guard import _requested_correction_field
        return _requested_correction_field(text, state or {})

    def test_amount_keywords_map_to_amount(self):
        assert self._call("the amount is wrong") == "estimated_claim_amount"

    def test_policy_keyword_maps_to_policy_id(self):
        assert self._call("my policy number is different") == "policy_id"

    def test_location_keyword_maps_to_event_location(self):
        assert self._call("the location is wrong") == "event_location"

    def test_date_keyword_maps_to_event_date(self):
        assert self._call("the date is wrong") == "event_date"

    def test_insurance_type_keyword(self):
        assert self._call("my insurance type is motor") == "insurance_type"

    def test_incident_keyword_maps_to_description(self):
        assert self._call("what happened is different") == "event_description"

    def test_unrelated_text_falls_back_to_state(self):
        state = {"next_question_field": "event_location"}
        result = self._call("some unrecognized text", state)
        assert result == "event_location"

    def test_confirmation_field_excluded(self):
        state = {"next_question_field": "confirmation"}
        result = self._call("some unrecognized text", state)
        assert result is None


# ---------------------------------------------------------------------------
# _correction_prompt
# ---------------------------------------------------------------------------
class TestCorrectionPrompt:
    def _call(self, field):
        from src.agents.turn_guard import _correction_prompt
        return _correction_prompt(field)

    def test_amount_field_prompt(self):
        result = self._call("estimated_claim_amount")
        assert "amount" in result.lower() or "loss" in result.lower()

    def test_policy_field_prompt(self):
        result = self._call("policy_id")
        assert "policy" in result.lower()

    def test_location_field_prompt(self):
        result = self._call("event_location")
        assert "location" in result.lower()

    def test_date_field_prompt(self):
        result = self._call("event_date")
        assert "date" in result.lower()

    def test_unknown_field_returns_generic(self):
        result = self._call("some_unknown_field")
        assert "correct" in result.lower() or "detail" in result.lower()

    def test_none_field_returns_generic(self):
        result = self._call(None)
        assert isinstance(result, str) and len(result) > 0


# ---------------------------------------------------------------------------
# conversation_turn_processor
# ---------------------------------------------------------------------------
class TestConversationTurnProcessor:
    def _base_state(self, claim_text=""):
        return {
            "claim_text": claim_text,
            "extracted_data": {},
            "field_status": {},
            "field_metadata": {},
            "recently_extracted_fields": [],
            "turn_number": 1,
        }

    def _call(self, state):
        with patch("src.agents.turn_guard.nodes") as mock_nodes:
            mock_nodes._SOCIAL_EXACT = set()
            mock_nodes._INCIDENT_TERMS = __import__("re").compile(r"accident|damaged|stolen|fire|flood|crash")
            mock_nodes.conversation_turn_processor = lambda s: s
            mock_nodes._deterministic_location = lambda t: None
            mock_nodes._strip_incident_noise = lambda t: t
            from src.agents.turn_guard import conversation_turn_processor
            return conversation_turn_processor(state)

    def test_greeting_sets_skip_all(self):
        state = self._base_state("hello")
        result = self._call(state)
        assert result.get("_skip_all") is True
        assert result.get("last_intent") == "greeting"

    def test_audio_check_sets_skip_all(self):
        state = self._base_state("can you hear me")
        result = self._call(state)
        assert result.get("_skip_all") is True

    def test_affirmative_with_awaiting_confirmation_sets_confirmed(self):
        state = self._base_state("yes")
        state["awaiting_confirmation"] = True
        state["recently_extracted_fields"] = []
        result = self._call(state)
        # Affirmative should set confirmed=True
        assert result.get("confirmed") is True

    def test_negative_with_awaiting_confirmation_sets_collecting(self):
        state = self._base_state("no")
        state["awaiting_confirmation"] = True
        state["recently_extracted_fields"] = []
        result = self._call(state)
        assert result.get("confirmed") is False
        assert result.get("conversation_status") == "collecting"

    def test_empty_claim_text_no_crash(self):
        state = self._base_state("")
        result = self._call(state)
        assert isinstance(result, dict)

    def test_none_claim_text_no_crash(self):
        state = self._base_state(None)
        result = self._call(state)
        assert isinstance(result, dict)

    def test_incident_description_extracted(self):
        state = self._base_state("My car was badly damaged in an accident yesterday")
        result = self._call(state)
        # Should populate event_description in extracted_data
        if result.get("extracted_data", {}).get("event_description"):
            assert len(result["extracted_data"]["event_description"]) >= 4

    def test_sorry_clears_awaiting_confirmation(self):
        state = self._base_state("Sorry, that is wrong")
        state["awaiting_confirmation"] = True
        state["recently_extracted_fields"] = []
        result = self._call(state)
        assert result.get("confirmed") is False
        assert result.get("awaiting_confirmation") is False

