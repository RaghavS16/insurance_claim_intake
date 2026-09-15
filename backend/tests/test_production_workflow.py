from src.database.claim_workflow import ALLOWED_TRANSITIONS

def test_claim_workflow_rejects_illegal_terminal_transition():
    assert "approved" not in ALLOWED_TRANSITIONS["draft"]
    assert "closed" not in ALLOWED_TRANSITIONS["draft"]

def test_claim_workflow_has_human_decision_paths():
    assert {"approved","partially_approved","rejected","pending_evidence","escalated"} <= ALLOWED_TRANSITIONS["under_review"]

def test_claim_workflow_allows_verified_assignment():
    assert "assigned" in ALLOWED_TRANSITIONS["verified"]
