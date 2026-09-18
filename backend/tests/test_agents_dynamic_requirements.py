"""
Edge-case tests for src/agents/dynamic_requirements.py

Covers: unresolved, missing_evidence, _deterministic_dynamic_extract,
        build_dynamic_context (partial), extract_answers (mocked LLM).
"""
import pytest
from unittest.mock import MagicMock, patch
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# unresolved
# ---------------------------------------------------------------------------
class TestUnresolved:
    def _call(self, state):
        from src.agents.dynamic_requirements import unresolved
        return unresolved(state)

    def test_empty_requirements_returns_empty(self):
        assert self._call({"dynamic_requirements": [], "extracted_data": {}}) == []

    def test_no_requirements_key_returns_empty(self):
        assert self._call({}) == []

    def test_fulfilled_requirement_excluded(self):
        reqs = [{"key": "vehicle_reg", "required": True, "evidence_type": None}]
        state = {"dynamic_requirements": reqs, "extracted_data": {"vehicle_reg": "MH02AB1234"}}
        assert self._call(state) == []

    def test_missing_requirement_included(self):
        reqs = [{"key": "vehicle_reg", "required": True, "evidence_type": None}]
        state = {"dynamic_requirements": reqs, "extracted_data": {}}
        result = self._call(state)
        assert len(result) == 1
        assert result[0]["key"] == "vehicle_reg"

    def test_optional_requirement_excluded(self):
        reqs = [{"key": "opt_field", "required": False, "evidence_type": None}]
        state = {"dynamic_requirements": reqs, "extracted_data": {}}
        assert self._call(state) == []

    def test_photo_evidence_type_excluded(self):
        reqs = [{"key": "damage_photo", "required": True, "evidence_type": "photo"}]
        state = {"dynamic_requirements": reqs, "extracted_data": {}}
        assert self._call(state) == []

    def test_unknown_value_treated_as_missing(self):
        reqs = [{"key": "vin", "required": True, "evidence_type": None}]
        state = {"dynamic_requirements": reqs, "extracted_data": {"vin": "UNKNOWN"}}
        result = self._call(state)
        assert len(result) == 1

    def test_empty_string_value_treated_as_missing(self):
        reqs = [{"key": "vin", "required": True, "evidence_type": None}]
        state = {"dynamic_requirements": reqs, "extracted_data": {"vin": ""}}
        result = self._call(state)
        assert len(result) == 1

    def test_none_value_treated_as_missing(self):
        reqs = [{"key": "vin", "required": True, "evidence_type": None}]
        state = {"dynamic_requirements": reqs, "extracted_data": {"vin": None}}
        result = self._call(state)
        assert len(result) == 1

    def test_no_key_in_requirement_excluded(self):
        reqs = [{"required": True, "evidence_type": None}]
        state = {"dynamic_requirements": reqs, "extracted_data": {}}
        assert self._call(state) == []

    def test_multiple_mixed_requirements(self):
        reqs = [
            {"key": "vehicle_reg", "required": True, "evidence_type": None},
            {"key": "driver_license", "required": True, "evidence_type": None},
            {"key": "damage_photo", "required": True, "evidence_type": "photo"},
        ]
        state = {
            "dynamic_requirements": reqs,
            "extracted_data": {"vehicle_reg": "TN09CB1234"},
        }
        result = self._call(state)
        assert len(result) == 1
        assert result[0]["key"] == "driver_license"


# ---------------------------------------------------------------------------
# missing_evidence
# ---------------------------------------------------------------------------
class TestMissingEvidence:
    def _call(self, state):
        from src.agents.dynamic_requirements import missing_evidence
        return missing_evidence(state)

    def test_empty_requirements_returns_empty(self):
        assert self._call({"dynamic_requirements": [], "evidence": []}) == []

    def test_no_evidence_uploaded_all_returned(self):
        reqs = [
            {"key": "damage_photo", "required": True, "evidence_type": "photo"},
            {"key": "repair_estimate", "required": True, "evidence_type": "document"},
        ]
        state = {"dynamic_requirements": reqs, "evidence": []}
        result = self._call(state)
        assert len(result) == 2

    def test_uploaded_evidence_key_excluded(self):
        reqs = [{"key": "damage_photo", "required": True, "evidence_type": "photo"}]
        state = {"dynamic_requirements": reqs, "evidence": [{"evidence_key": "damage_photo"}]}
        assert self._call(state) == []

    def test_optional_evidence_excluded(self):
        reqs = [{"key": "extra_photo", "required": False, "evidence_type": "photo"}]
        state = {"dynamic_requirements": reqs, "evidence": []}
        assert self._call(state) == []

    def test_no_evidence_type_excluded(self):
        reqs = [{"key": "driver_name", "required": True, "evidence_type": None}]
        state = {"dynamic_requirements": reqs, "evidence": []}
        assert self._call(state) == []

    def test_partially_uploaded_evidence(self):
        reqs = [
            {"key": "photo1", "required": True, "evidence_type": "photo"},
            {"key": "photo2", "required": True, "evidence_type": "photo"},
        ]
        state = {"dynamic_requirements": reqs, "evidence": [{"evidence_key": "photo1"}]}
        result = self._call(state)
        assert len(result) == 1
        assert result[0]["key"] == "photo2"


# ---------------------------------------------------------------------------
# _deterministic_dynamic_extract
# ---------------------------------------------------------------------------
class TestDeterministicDynamicExtract:
    def _call(self, text):
        from src.agents.dynamic_requirements import _deterministic_dynamic_extract
        return _deterministic_dynamic_extract(text)

    def test_extracts_indian_vehicle_plate(self):
        result = self._call("My vehicle registration number is MH02AB1234")
        assert "vehicle_registration_number" in result
        assert result["vehicle_registration_number"] == "MH02AB1234"

    def test_extracts_dash_separated_plate(self):
        result = self._call("The plate is TN-09-CB-1234")
        assert "vehicle_registration_number" in result

    def test_extracts_driver_license(self):
        result = self._call("My DL number is DL12345678")
        assert "driver_license_number" in result

    def test_extracts_license_keyword(self):
        result = self._call("license: DL-567890")
        assert "driver_license_number" in result

    def test_no_relevant_info_returns_empty(self):
        result = self._call("I had an accident on the highway")
        assert result == {}

    def test_empty_string_returns_empty(self):
        result = self._call("")
        assert result == {}

    def test_extracts_to_uppercase(self):
        result = self._call("reg: mh02ab1234")
        if "vehicle_registration_number" in result:
            assert result["vehicle_registration_number"] == result["vehicle_registration_number"].upper()


# ---------------------------------------------------------------------------
# extract_answers (LLM mocked)
# ---------------------------------------------------------------------------
class TestExtractAnswers:
    def _base_state(self, utterance="", requirements=None):
        return {
            "last_user_utterance": utterance,
            "dynamic_requirements": requirements or [],
            "extracted_data": {},
            "evidence": [],
        }

    def test_no_utterance_no_crash(self):
        from src.agents.dynamic_requirements import extract_answers
        state = self._base_state(utterance="")
        extract_answers(state)
        assert "dynamic_missing" in state

    def test_no_requirements_sets_empty_missing(self):
        from src.agents.dynamic_requirements import extract_answers
        state = self._base_state(utterance="some text")
        extract_answers(state)
        assert state.get("dynamic_missing") == []

    def test_deterministic_extraction_populates_extracted_data(self):
        from src.agents.dynamic_requirements import extract_answers
        state = self._base_state(utterance="My car plate is MH02AB1234")
        extract_answers(state)
        assert state["extracted_data"].get("vehicle_registration_number") == "MH02AB1234"

    def test_llm_called_when_requirements_unresolved(self):
        """LLM should be called to fill remaining required fields."""
        from src.agents import dynamic_requirements as dr_module
        reqs = [{"key": "claim_narrative", "required": True, "evidence_type": None}]
        state = self._base_state(utterance="Something happened", requirements=reqs)

        class FakePlan(BaseModel):
            values: dict = {"claim_narrative": "car accident"}

        mock_llm = MagicMock()
        fake_plan = FakePlan()
        mock_llm.with_structured_output.return_value.invoke.return_value = fake_plan

        original_get_llm = dr_module.get_configured_llm
        dr_module.get_configured_llm = lambda: mock_llm
        try:
            dr_module.extract_answers(state)
        finally:
            dr_module.get_configured_llm = original_get_llm

        assert state["extracted_data"].get("claim_narrative") == "car accident"

    def test_llm_failure_does_not_crash(self):
        from src.agents import dynamic_requirements as dr_module
        reqs = [{"key": "claim_narrative", "required": True, "evidence_type": None}]
        state = self._base_state(utterance="Something happened", requirements=reqs)
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value.invoke.side_effect = Exception("LLM timeout")

        original_get_llm = dr_module.get_configured_llm
        dr_module.get_configured_llm = lambda: mock_llm
        try:
            dr_module.extract_answers(state)
        finally:
            dr_module.get_configured_llm = original_get_llm

        assert "dynamic_extraction_error" in state

    def test_llm_not_overwrite_non_allowed_keys(self):
        """LLM must not inject keys outside allowed requirements."""
        from src.agents import dynamic_requirements as dr_module
        reqs = [{"key": "allowed_key", "required": True, "evidence_type": None}]
        state = self._base_state(utterance="Some text", requirements=reqs)

        class FakePlan(BaseModel):
            values: dict = {"allowed_key": "valid", "injected_key": "malicious"}

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value.invoke.return_value = FakePlan()

        original_get_llm = dr_module.get_configured_llm
        dr_module.get_configured_llm = lambda: mock_llm
        try:
            dr_module.extract_answers(state)
        finally:
            dr_module.get_configured_llm = original_get_llm

        assert "injected_key" not in state.get("extracted_data", {})
        assert state["extracted_data"].get("allowed_key") == "valid"


def test_rag_documents_without_requirement_plan_do_not_unlock_submission():
    from src.knowledge.retriever import KnowledgeRetriever
    with patch("src.knowledge.retriever.search", side_effect=[[{"id":"p1"}],[{"id":"g1"}]]),          patch("src.knowledge.retriever.rerank", side_effect=lambda q, items, top_n=5: items),          patch("src.knowledge.retriever.get_configured_llm", return_value=MagicMock()),          patch("src.knowledge.retriever.get_requirements_from_context", return_value=[]):
        result = KnowledgeRetriever().retrieve(insurance_type="motor", policy_number="POL-1409-XI", query="bike accident")
    assert result["available"] is False
    assert result["status"] == "REQUIREMENT_PLAN_UNAVAILABLE"


def test_response_planner_blocks_final_submission_without_rag_plan():
    from src.agents.graph import _response_planner
    result = _response_planner({
        "confirmed": True,
        "missing_fields": [],
        "extracted_data": {"insurance_type":"motor"},
        "dynamic_requirements": [],
        "dynamic_missing": [],
        "missing_evidence": [],
        "rag_status": "REQUIREMENT_PLAN_UNAVAILABLE",
    })
    assert result["conversation_status"] == "waiting_for_knowledge"
    assert "submit" not in result["next_question"].lower()
    assert "adjuster" not in result["next_question"].lower()


def test_response_planner_asks_dynamic_question_before_submission():
    from src.agents.graph import _response_planner
    result = _response_planner({
        "confirmed": True,
        "missing_fields": [],
        "extracted_data": {"insurance_type":"motor"},
        "dynamic_requirements": [{
            "key":"vehicle_registration_number",
            "label":"Vehicle registration number",
            "question_hint":"What is your bike's registration number?",
            "required": True,
            "evidence_type": None,
        }],
        "dynamic_missing": [{
            "key":"vehicle_registration_number",
            "label":"Vehicle registration number",
            "question_hint":"What is your bike's registration number?",
            "required": True,
            "evidence_type": None,
        }],
        "missing_evidence": [],
        "rag_status": "OK",
    })
    assert result["conversation_status"] == "collecting_dynamic"
    assert result["next_question"] == "What is your bike's registration number?"
