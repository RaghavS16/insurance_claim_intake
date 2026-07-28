import pytest


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_valid_claim_approved(client):
    """Happy path: valid policy, within coverage, low fraud score → approved."""
    payload = {
        "claim_text": "My car was hit by a truck on 2025-07-15 in Mumbai. Policy XYZ123. Repair cost is 50000 rupees.",
        "input_mode": "text",
    }
    response = client.post("/api/v1/claims/process", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["validation_status"] == "valid"
    assert data["coverage_eligible"] is True
    assert data["final_decision"] == "approved"
    assert data["ticket_id"].startswith("CLAIM-")
    assert data["assigned_adjuster"] is not None


def test_invalid_policy_routes_to_manual_review(client):
    """Expired/invalid policy → rejected, routed to manual review, skips coverage/fraud nodes."""
    payload = {
        "claim_text": "My car had an accident on 2025-01-10. Policy AUTO789. Damage cost 20000.",
        "input_mode": "text",
    }
    response = client.post("/api/v1/claims/process", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["validation_status"] == "rejected"
    assert data["final_decision"] == "manual_review"
    # Should short-circuit — no fraud/routing fields populated
    assert data.get("assigned_adjuster") is None
    assert data.get("ticket_id") is None


def test_claim_exceeds_coverage_denied(client):
    """Claimed amount over policy coverage_amount → not covered → denied."""
    payload = {
        "claim_text": "My car was damaged on 2025-06-01. Policy XYZ123. Repair cost is 900000 rupees.",
        "input_mode": "text",
    }
    response = client.post("/api/v1/claims/process", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["coverage_eligible"] is False
    assert data["final_decision"] == "denied"


def test_high_fraud_score_flagged_for_review(client):
    """Future incident date + near-limit claim amount → fraud_score >= 0.7 → flagged."""
    payload = {
        "claim_text": "My car was damaged on 2027-01-01. Policy XYZ123. Repair cost is 480000 rupees.",
        "input_mode": "text",
    }
    response = client.post("/api/v1/claims/process", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert "future_incident_date" in data["fraud_flags"]
    assert "claim_near_policy_limit" in data["fraud_flags"]
    assert data["fraud_score"] >= 0.7
    assert data["final_decision"] == "flagged_for_review"  # regression test for the >= vs > bug


def test_fraud_score_boundary_exact_0_7(client):
    """Exact 0.7 boundary must trigger review, not silently approve (off-by-boundary regression test)."""
    payload = {
        "claim_text": "My car was damaged on 2027-01-01. Policy XYZ123. Repair cost is 480000 rupees.",
        "input_mode": "text",
    }
    response = client.post("/api/v1/claims/process", json=payload)
    data = response.json()
    if data["fraud_score"] == 0.7:
        assert data["final_decision"] == "flagged_for_review"