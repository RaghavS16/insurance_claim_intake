from datetime import date

from src.agents import nodes
from src.agents.graph import _dynamic_requirement_enrichment


def test_natural_health_claim_baseline_extracts_partial_date_and_location():
    text = (
        "i have a severe viral fever on past one week, so i admitted in "
        "Guindy Govt hospital on 17 sept, medical expenses on around 15000 rupees "
        "so i like to claim my health insurance. my policy number is POL-1042-JX."
    )
    changes = nodes._rule_changes(text, {"extracted_data": {}})
    values = {c.field: c.value for c in changes}

    assert values["event_date"] == "2026-09-17"
    assert values["event_location"] == "Guindy Govt hospital"
    assert values["estimated_claim_amount"] == 15000.0
    assert values["insurance_type"] == "health"
    assert values["policy_id"] == "POL-1042-JX"


def test_health_narrative_counts_as_incident_description():
    text = "I had a severe viral fever and was admitted to the hospital for treatment."
    description = nodes._incident_description_from_text(text, {})
    assert description
    assert "fever" in description.lower()


def test_claim_rag_waits_for_baseline_confirmation():
    state = {
        "confirmed": False,
        "extracted_data": {"insurance_type": "health"},
        "dynamic_requirements": [],
    }
    result = _dynamic_requirement_enrichment(state)
    assert result["rag_status"] == "WAITING_FOR_BASELINE_CONFIRMATION"
    assert result["dynamic_missing"] == []
    assert result["missing_evidence"] == []
