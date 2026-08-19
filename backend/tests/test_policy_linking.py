from datetime import date
import pytest
from src.database.models import Policy, PolicyLinkAudit, User


def test_link_policy_success(client, db):
    # Ensure MOT-5521 is reset to unlinked state for this test
    pol = db.query(Policy).filter(Policy.policy_number == "MOT-5521").first()
    if pol:
        pol.customer_id = None
        pol.policyholder_dob = date(1990, 5, 15)
        pol.policyholder_phone_last4 = "1234"
        pol.link_attempts = 0
        db.commit()

    response = client.post("/api/v1/policies/link", json={
        "policy_number": "MOT-5521",
        "date_of_birth": "1990-05-15",
        "phone_last4": "1234",
    })

    assert response.status_code == 200
    data = response.json()
    assert data["linked"] is True
    assert data["already_linked"] is False
    assert data["policy_number"] == "MOT-5521"

    # Verify DB state
    db.refresh(pol)
    assert pol.customer_id == "TEST_USER_ID"
    assert pol.linked_at is not None
    assert pol.link_attempts == 0

    # Verify audit entry
    audit = db.query(PolicyLinkAudit).filter(
        PolicyLinkAudit.policy_number == "MOT-5521",
        PolicyLinkAudit.outcome == "success"
    ).first()
    assert audit is not None


def test_link_policy_already_linked_to_self(client, db):
    # XYZ123 is seeded to TEST_USER_ID
    response = client.post("/api/v1/policies/link", json={
        "policy_number": "XYZ123",
        "date_of_birth": "1990-05-15",
        "phone_last4": "1234",
    })

    assert response.status_code == 200
    data = response.json()
    assert data["linked"] is True
    assert data["already_linked"] is True


def test_link_policy_already_linked_to_other(client, db):
    # User B tries to link XYZ123 which is owned by TEST_USER_ID
    response = client.post("/api/v1/policies/link", json={
        "policy_number": "XYZ123",
        "date_of_birth": "1990-05-15",
        "phone_last4": "1234",
    }, headers={"X-User-ID": "OTHER_USER_2"})

    assert response.status_code == 409
    data = response.json()
    assert "already linked to another account" in data["detail"]

    # Verify audit
    audit = db.query(PolicyLinkAudit).filter(
        PolicyLinkAudit.outcome == "already_linked_other"
    ).first()
    assert audit is not None


def test_link_policy_not_found(client, db):
    response = client.post("/api/v1/policies/link", json={
        "policy_number": "NONEXISTENT-999",
        "date_of_birth": "1990-05-15",
        "phone_last4": "1234",
    })

    assert response.status_code == 404
    assert "couldn't verify those details" in response.json()["detail"]


def test_link_policy_pii_mismatch(client, db):
    # Create a fresh unlinked policy for testing PII mismatch
    pol = db.query(Policy).filter(Policy.policy_number == "HOME456").first()
    if pol:
        pol.customer_id = None
        pol.policyholder_dob = date(1985, 8, 20)
        pol.policyholder_phone_last4 = "5678"
        pol.link_attempts = 0
        db.commit()

    # Wrong DOB
    response = client.post("/api/v1/policies/link", json={
        "policy_number": "HOME456",
        "date_of_birth": "1999-01-01",
        "phone_last4": "5678",
    })
    assert response.status_code == 403
    db.refresh(pol)
    assert pol.link_attempts == 1

    # Wrong phone
    response = client.post("/api/v1/policies/link", json={
        "policy_number": "HOME456",
        "date_of_birth": "1985-08-20",
        "phone_last4": "0000",
    })
    assert response.status_code == 403
    db.refresh(pol)
    assert pol.link_attempts == 2


def test_link_policy_rate_limited(client, db):
    pol = db.query(Policy).filter(Policy.policy_number == "HOME456").first()
    if pol:
        pol.link_attempts = 5
        db.commit()

    response = client.post("/api/v1/policies/link", json={
        "policy_number": "HOME456",
        "date_of_birth": "1985-08-20",
        "phone_last4": "5678",
    })
    assert response.status_code == 429
    assert "Too many attempts" in response.json()["detail"]


def test_list_my_policies(client, db):
    # Ensure XYZ123 is linked to TEST_USER_ID
    response = client.get("/api/v1/policies/my-policies")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    policy_numbers = [p["policy_number"] for p in data]
    assert "XYZ123" in policy_numbers
