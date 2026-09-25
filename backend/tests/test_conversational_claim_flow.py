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


def test_fragmented_incident_story_is_rewritten_into_one_meaningful_description(monkeypatch):
    def fake_structured(_model, _prompt, schema):
        return schema(description="I developed a severe viral fever yesterday and received treatment at the hospital.")

    monkeypatch.setattr(nodes, "_invoke_structured", fake_structured)
    monkeypatch.setattr(nodes, "_get_llm", lambda: object())
    state = {
        "claim_text": "I have a severe viral fever on yesterday",
        "extracted_data": {},
        "conversation_history": [],
    }

    result = nodes.conversation_turn_processor(state)

    description = result["extracted_data"]["event_description"]
    assert description.startswith("I developed a severe viral fever")
    assert "treatment at the hospital" in description
    assert description != "I have a severe viral fever on"


def test_incident_description_can_be_built_from_multiple_claimant_turns(monkeypatch):
    prompts = []

    def fake_structured(_model, prompt, schema):
        prompts.append(prompt)
        return schema(description="I developed a severe viral fever yesterday and was treated at Chennai Government Hospital.")

    monkeypatch.setattr(nodes, "_invoke_structured", fake_structured)
    monkeypatch.setattr(nodes, "_get_llm", lambda: object())
    state = {
        "claim_text": "I have a severe viral fever on yesterday",
        "extracted_data": {},
        "conversation_history": [],
    }
    nodes.conversation_turn_processor(state)

    state["claim_text"] = "It happened at Chennai Government Hospital and I received treatment."
    nodes.conversation_turn_processor(state)

    assert len(prompts) >= 2
    assert "I have a severe viral fever on yesterday" in prompts[-1]
    assert "It happened at Chennai Government Hospital" in prompts[-1]
    assert "Chennai Government Hospital" in state["extracted_data"]["event_description"]


def test_rich_motor_turn_extracts_description_and_real_location_not_time_phrase():
    text = (
        "On September 18th around 7:45 in the evening, I was riding my Yamaha FZ-S "
        "northbound near the Anna Nagar Ring Road Junction here in Madurai. The signal "
        "was green when an oncoming car turned across my lane. I braked and swerved, "
        "but my bike clipped the car's passenger door, fell on its right side, and "
        "damaged the handlebar, fork, brake lever and exhaust shield."
    )
    changes = nodes._rule_changes(text, {"extracted_data": {}})
    values = {c.field: c.value for c in changes}

    assert values["event_date"] == "2026-09-18"
    assert values["event_location"] == "Anna Nagar Ring Road Junction here in Madurai"
    assert "the evening" not in values["event_location"].lower()
    assert "clipped" in values["event_description"].lower()
    assert "damaged" in values["event_description"].lower()


def test_meta_statement_does_not_overwrite_incident_description():
    state = {
        "claim_text": "i already told you what happened and my policy number was POL-1409-XI",
        "extracted_data": {
            "event_description": "My motorcycle clipped an oncoming car and fell on its right side.",
            "policy_id": None,
        },
        "conversation_history": [
            {"speaker": "user", "text": "My motorcycle clipped an oncoming car and fell on its right side."},
        ],
    }

    result = nodes.conversation_turn_processor(state)

    assert result["extracted_data"]["event_description"] == (
        "My motorcycle clipped an oncoming car and fell on its right side."
    )
    assert result["extracted_data"]["policy_id"] == "POL-1409-XI"
