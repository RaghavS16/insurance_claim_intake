from src.agents import nodes


def test_scalar_is_not_overwritten_without_replace():
    state = {"extracted_data": {"estimated_claim_amount": 20000}, "field_metadata": {}, "field_status": {}}
    change = nodes.FieldChange(field="estimated_claim_amount", operation="set", value=30000, confidence=0.99, evidence="30000")
    assert nodes._merge(state, change, 2) is False
    assert state["extracted_data"]["estimated_claim_amount"] == 20000


def test_scalar_correction_replaces_value():
    state = {"extracted_data": {"estimated_claim_amount": 20000}, "field_metadata": {}, "field_status": {}}
    change = nodes.FieldChange(field="estimated_claim_amount", operation="replace", value=30000, confidence=0.99, evidence="the amount is 30000")
    assert nodes._merge(state, change, 3) is True
    assert state["extracted_data"]["estimated_claim_amount"] == 30000


def test_description_append_preserves_existing_text():
    state = {"extracted_data": {"event_description": "Bike fell on the road."}, "field_metadata": {}, "field_status": {}}
    change = nodes.FieldChange(field="event_description", operation="append", value="The front wheel was damaged.", confidence=0.95, evidence="front wheel damaged")
    assert nodes._merge(state, change, 4) is True
    assert state["extracted_data"]["event_description"] == "Bike fell on the road. The front wheel was damaged."


def test_invalid_insurance_type_is_rejected():
    change = nodes.FieldChange(field="insurance_type", operation="set", value="business", confidence=0.99, evidence="business")
    assert nodes._valid_change(change) is None
