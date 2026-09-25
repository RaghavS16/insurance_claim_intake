"""Regression tests for natural baseline and claim-specific extraction."""

from src.agents.nodes import _deterministic_amount, _deterministic_location
from src.agents.dynamic_requirements import _deterministic_dynamic_extract, unresolved
from src.evidence.verifier import EvidenceAnalysis


def test_idv_and_deductible_are_not_claim_loss():
    text = "The IDV is ₹9,00,000 and the policy deductible is ₹12,000."
    assert _deterministic_amount(text) is None


def test_explicit_claim_amount_is_extracted():
    assert _deterministic_amount("I would like to claim 10000 rupees") == 10000


def test_scene_is_not_used_as_incident_location():
    assert _deterministic_location(
        "No police report was filed. Both parties settled the matter at the scene."
    ) is None


def test_dynamic_third_party_facts_are_mapped_to_active_requirements():
    requirements = [
        {"key": "other_vehicle_registration", "label": "Other vehicle registration", "question_hint": "What is the other vehicle registration number?"},
        {"key": "third_party_driver_name", "label": "Driver name", "question_hint": "What is the other driver's name?"},
        {"key": "third_party_driver_contact", "label": "Driver contact number", "question_hint": "What is the driver's contact number?"},
        {"key": "other_vehicle_make_model", "label": "Other vehicle make and model", "question_hint": "What is the make and model of the other vehicle?"},
    ]
    text = (
        "Yes, it was a silver Hyundai i20, registration number TN-58-BZ-4589. "
        "The driver was S. Karthik, and his contact number is +91 94432 10987."
    )
    values = _deterministic_dynamic_extract(text, requirements)
    assert values["other_vehicle_registration"] == "TN-58-BZ-4589"
    assert values["third_party_driver_name"] == "S. Karthik"
    assert values["third_party_driver_contact"] == "+919443210987"
    assert values["other_vehicle_make_model"] == "silver Hyundai i20"


def test_short_yes_satisfies_active_police_requirement():
    requirements = [
        {"key": "police_report_or_fir", "label": "Police report or FIR", "question_hint": "Do you have a copy of the police report or FIR filed for this accident?"},
    ]
    values = _deterministic_dynamic_extract("yes", requirements)
    assert values["police_report_or_fir"] is True


def test_short_no_satisfies_active_police_requirement():
    requirements = [
        {"key": "police_report_or_fir", "label": "Police report or FIR", "question_hint": "Do you have a copy of the police report or FIR filed for this accident?"},
    ]
    values = _deterministic_dynamic_extract("no", requirements)
    assert values["police_report_or_fir"] is False



def test_repair_cost_requirement_is_satisfied_by_baseline_estimated_claim_amount():
    state = {
        "extracted_data": {"estimated_claim_amount": 30000},
        "dynamic_requirements": [
            {
                "key": "estimated_repair_cost",
                "label": "Estimated repair cost",
                "question_hint": "What is the total estimated cost for repairing your bike?",
                "required": True,
            }
        ],
    }
    assert unresolved(state) == []


def test_evidence_analysis_uses_strict_object_schema_for_provider_structured_output():
    schema = EvidenceAnalysis.model_json_schema()

    def assert_strict_objects(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False
            for value in node.values():
                assert_strict_objects(value)
        elif isinstance(node, list):
            for value in node:
                assert_strict_objects(value)

    assert_strict_objects(schema)
