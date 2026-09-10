from datetime import date, timedelta

from src.agents import nodes


def test_scalar_is_not_overwritten_without_replace():
    state = {"extracted_data": {"estimated_claim_amount": 20000}, "field_metadata": {}, "field_status": {}}
    change = nodes.FieldChange(field="estimated_claim_amount", operation="set", value=30000, confidence=0.99, evidence="30000")
    assert nodes._merge_change(state, change, 2) is False
    assert state["extracted_data"]["estimated_claim_amount"] == 20000


def test_scalar_correction_replaces_value():
    state = {"extracted_data": {"estimated_claim_amount": 20000}, "field_metadata": {}, "field_status": {}}
    change = nodes.FieldChange(field="estimated_claim_amount", operation="replace", value=30000, confidence=0.99, evidence="the amount is 30000")
    assert nodes._merge_change(state, change, 3) is True
    assert state["extracted_data"]["estimated_claim_amount"] == 30000


def test_description_append_preserves_existing_text():
    state = {"extracted_data": {"event_description": "Bike fell on the road."}, "field_metadata": {}, "field_status": {}}
    change = nodes.FieldChange(field="event_description", operation="append", value="The front wheel was damaged.", confidence=0.95, evidence="front wheel damaged")
    assert nodes._merge_change(state, change, 4) is True
    assert "front wheel" in state["extracted_data"]["event_description"]


def test_invalid_insurance_type_is_rejected():
    state = {"extracted_data": {}, "field_metadata": {}, "field_status": {}}
    change = nodes.FieldChange(field="insurance_type", operation="set", value="business", confidence=0.99, evidence="business")
    assert nodes._validate_change(change, state) is None


def test_yesterday_is_deterministically_extracted():
    changes = nodes._rule_changes("I had a bike accident yesterday.", {"extracted_data": {}})
    dates = [c.value for c in changes if c.field == "event_date"]
    assert dates == [(date.today() - timedelta(days=1)).isoformat()]


def test_amount_ignores_date_and_extracts_repair_cost():
    changes = nodes._rule_changes("The accident was on 2026-09-07 and repair cost is ₹50,000.", {"extracted_data": {}})
    amounts = [c.value for c in changes if c.field == "estimated_claim_amount"]
    assert amounts == [50000.0]


def test_multiple_fields_are_extracted_from_one_natural_utterance():
    raw = "My bike accident happened yesterday in Chennai and the repair cost is 12 thousand. My policy ID is XYZ123."
    changes = nodes._rule_changes(raw, {"extracted_data": {}})
    result = {change.field: change.value for change in changes}
    assert result["event_date"] == (date.today() - timedelta(days=1)).isoformat()
    assert result["event_location"] == "Chennai"
    assert result["estimated_claim_amount"] == 12000.0
    assert result["policy_id"] == "XYZ123"
    assert result["insurance_type"] == "motor"


def test_policy_phrase_does_not_turn_idea_into_policy_number():
    changes = nodes._rule_changes("My policy idea is X, Y, Z.", {"extracted_data": {}})
    assert not any(c.field == "policy_id" for c in changes)


def test_policy_id_requires_a_real_identifier():
    changes = nodes._rule_changes("My policy ID is XYZ123.", {"extracted_data": {}})
    policies = [c.value for c in changes if c.field == "policy_id"]
    assert policies == ["XYZ123"]


def test_suspicious_policy_value_can_be_replaced_by_real_identifier():
    state = {"extracted_data": {"policy_id": "IDEA"}, "field_metadata": {}, "field_status": {}}
    changes = nodes._rule_changes("My policy ID is XYZ123.", state)
    assert any(c.field == "policy_id" and c.operation == "replace" and c.value == "XYZ123" for c in changes)


def test_location_stops_at_conjunction():
    changes = nodes._rule_changes("The incident happened at Chennai and my policy ID is XYZ123.", {"extracted_data": {}})
    locations = [c.value for c in changes if c.field == "event_location"]
    assert locations == ["Chennai"]


def test_description_does_not_store_entire_transcript_or_metadata():
    raw = "I had a bike accident yesterday, my bike was damaged, repair cost is 12000 rupees, my policy ID is XYZ123."
    change = nodes.FieldChange(field="event_description", operation="set", value=raw, confidence=0.99, evidence=raw)
    normalized = nodes._validate_change(change, {"extracted_data": {}, "last_user_utterance": raw})
    assert normalized is not None
    assert "policy ID" not in normalized.value
    assert "12000" not in normalized.value
    assert "yesterday" not in normalized.value


def test_confirmation_summary_is_grounded_and_not_transcript_length():
    text = nodes._confirmation_summary({
        "insurance_type": "motor",
        "event_date": "2026-09-07",
        "event_location": "Chennai",
        "estimated_claim_amount": 12000,
        "policy_id": "XYZ123",
        "event_description": "My bike was damaged in an accident",
    })
    assert "XYZ123" in text
    assert "Chennai" in text
    assert "12,000" in text
    assert len(text.split()) < 40
