from datetime import date
import pytest
import uuid
from src.agents.policy_check import verify_policy_for_claim
from src.database.models import Policy


def test_wrong_policy_owner(db, client):
    # Unit check
    res = verify_policy_for_claim("XYZ123", "2025-05-05", "wrong-claimant-id", "motor", db)
    assert not res["valid"]
    assert res["reason"] == "ownership_mismatch"

    # API check: Claimant B tries to verify with Claimant A's policy
    intake = client.post("/api/v1/claims/intake", json={
        "claim_text": "My car was hit on 2025-07-15. Policy XYZ123. Repair cost 50000 rupees.",
        "input_mode": "text",
    }, headers={"X-User-ID": "OTHER_USER"}).json()
    ticket_id = intake["ticket_id"]
    response = client.post(f"/api/v1/claims/{ticket_id}/verify", headers={"X-User-ID": "OTHER_USER"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "verification_failed"
    assert data["policy_verification"]["reason"] == "ownership_mismatch"


def test_policy_not_linked(db, client):
    # Ensure MOT-5521 is unlinked (customer_id is None)
    pol = db.query(Policy).filter(Policy.policy_number == "MOT-5521").first()
    if pol:
        pol.customer_id = None
        db.commit()

    res = verify_policy_for_claim("MOT-5521", "2025-05-05", "TEST_USER_ID", "motor", db)
    assert not res["valid"]
    assert res["reason"] == "policy_not_linked"

    # API check
    intake = client.post("/api/v1/claims/intake", json={
        "claim_text": "My car was damaged on 2025-06-10. Policy MOT-5521. Repair cost 15000 rupees.",
        "input_mode": "text",
    }).json()
    ticket_id = intake["ticket_id"]
    response = client.post(f"/api/v1/claims/{ticket_id}/verify")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "verification_failed"
    assert data["policy_verification"]["reason"] == "policy_not_linked"
    assert "Please link this policy" in data["message"]


def test_policy_type_mismatch(db, client):
    # XYZ123 is motor, but claimed as health
    res = verify_policy_for_claim("XYZ123", "2025-05-05", "TEST_USER_ID", "health", db)
    assert not res["valid"]
    assert res["reason"] == "insurance_type_mismatch"


def test_policy_invalid_on_event_date(db, client):
    # XYZ123 is valid 2024-01-01 to 2030-12-31. Date 2023-05-05 is before effective date.
    res = verify_policy_for_claim("XYZ123", "2023-05-05", "TEST_USER_ID", "motor", db)
    assert not res["valid"]
    assert res["reason"] == "policy_not_active_on_event_date"

    # API check
    intake = client.post("/api/v1/claims/intake", json={
        "claim_text": "My car was hit on 2023-05-05. Policy XYZ123. Repair cost 50000 rupees.",
        "input_mode": "text",
    }).json()
    ticket_id = intake["ticket_id"]
    response = client.post(f"/api/v1/claims/{ticket_id}/verify")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "verification_failed"
    assert data["policy_verification"]["reason"] == "policy_not_active_on_event_date"


def test_verify_policy_no_policy_id(db):
    res = verify_policy_for_claim(None, "2024-05-05", "user1", "motor", db)
    assert not res["valid"]
    assert res["reason"] == "no_policy_id"


def test_verify_policy_not_found(db):
    res = verify_policy_for_claim("MISSING", "2024-05-05", "user1", "motor", db)
    assert not res["valid"]
    assert res["reason"] == "policy_not_found"


def test_verify_policy_ownership_mismatch(db):
    res = verify_policy_for_claim("XYZ123", "2024-05-05", "wrong_user_id", "motor", db)
    assert not res["valid"]
    assert res["reason"] == "ownership_mismatch"


def test_verify_policy_missing_event_date(db):
    res = verify_policy_for_claim("XYZ123", None, "TEST_USER_ID", "motor", db)
    assert not res["valid"]
    assert res["reason"] == "missing_event_date"


def test_verify_policy_invalid_event_date(db):
    res = verify_policy_for_claim("XYZ123", "2024-13-45", "TEST_USER_ID", "motor", db)
    assert not res["valid"]
    assert res["reason"] == "invalid_event_date"


def test_verify_policy_inactive(db):
    pol = db.query(Policy).filter(Policy.policy_number == "EXP-0001").first()
    if pol:
        # Set customer_id so it passes ownership check first
        pol.customer_id = "TEST_USER_ID"
        db.commit()
        res = verify_policy_for_claim("EXP-0001", "2021-05-05", "TEST_USER_ID", "motor", db)
        assert not res["valid"]
        assert res["reason"] == "policy_inactive"


def test_verify_policy_not_active_on_event_date(db):
    res = verify_policy_for_claim("XYZ123", "2023-05-05", "TEST_USER_ID", "motor", db)
    assert not res["valid"]
    assert res["reason"] == "policy_not_active_on_event_date"


def test_verify_policy_valid(db):
    res = verify_policy_for_claim("XYZ123", "2025-05-05", "TEST_USER_ID", "motor", db)
    assert res["valid"]
    assert res["reason"] is None
