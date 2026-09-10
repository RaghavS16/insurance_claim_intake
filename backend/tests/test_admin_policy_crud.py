"""
Tests for Admin Policy Management (CRUD) and Policyholder Name Verification.
"""
import uuid
import pytest
from datetime import date
from fastapi.testclient import TestClient

from src.api.main import app
from src.database.session import get_db, SessionLocal
from src.database.models import Policy, User
from src.utils.auth import create_access_token, get_password_hash


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def admin_token(db_session):
    admin_id = str(uuid.uuid4())
    admin_user = User(id=admin_id, full_name="Admin Boss", email=f"admin_{admin_id[:6]}@insure.co", password_hash=get_password_hash("AdminPass123!"), role="ADMIN", status="active")
    db_session.add(admin_user); db_session.commit()
    return create_access_token(data={"sub": admin_id, "role": "ADMIN"})


@pytest.fixture
def claimant_token(db_session):
    claimant_id = str(uuid.uuid4())
    claimant_user = User(id=claimant_id, full_name="Alice Claimant", email=f"claimant_{claimant_id[:6]}@test.com", password_hash=get_password_hash("ClaimantPass123!"), role="CLAIMANT", status="active")
    db_session.add(claimant_user); db_session.commit()
    return create_access_token(data={"sub": claimant_id, "role": "CLAIMANT"}), claimant_id


def test_admin_create_update_delete_policy(admin_token):
    client = TestClient(app); headers = {"Authorization": f"Bearer {admin_token}"}; unique_pol = f"POL-{uuid.uuid4().hex[:6].upper()}"
    create_payload = {"policy_number": unique_pol, "policy_type": "motor", "coverage_amount": 750000, "deductible": 5000, "effective_date": "2024-01-01", "expiry_date": "2026-12-31", "policyholder_name": "Alice Wonderland", "policyholder_dob": "1988-04-12", "policyholder_phone_last4": "4321", "is_active": True}
    res = client.post("/api/v1/admin/policies", json=create_payload, headers=headers); assert res.status_code == 200, res.text
    assert res.json()["policy_number"] == unique_pol
    update_payload = {"coverage_amount": 900000, "policyholder_name": "Alice W. Carroll", "is_active": False}
    res_up = client.put(f"/api/v1/admin/policies/{unique_pol}", json=update_payload, headers=headers); assert res_up.status_code == 200, res_up.text
    assert res_up.json()["coverage_amount"] == 900000
    res_del = client.delete(f"/api/v1/admin/policies/{unique_pol}", headers=headers); assert res_del.status_code == 200, res_del.text
    assert client.put(f"/api/v1/admin/policies/{unique_pol}", json={"is_active": True}, headers=headers).status_code == 404


def test_link_policy_with_policyholder_name(claimant_token, db_session):
    client = TestClient(app); token, claimant_id = claimant_token; headers = {"Authorization": f"Bearer {token}"}; unique_pol = f"POL-{uuid.uuid4().hex[:6].upper()}"
    policy = Policy(id=str(uuid.uuid4()), policy_number=unique_pol, policy_type="health", coverage_amount=500000, deductible=2000, effective_date=date(2024, 1, 1), expiry_date=date(2027, 12, 31), is_active=True, policyholder_name="David Attenborough", policyholder_dob=date(1980, 5, 20), policyholder_phone_last4="9876", link_attempts=0)
    db_session.add(policy); db_session.commit()
    res = client.post("/api/v1/policies/link", json={"policy_number": unique_pol, "policyholder_name": "David Attenborough", "date_of_birth": "1980-05-20", "phone_last4": "9876"}, headers=headers)
    assert res.status_code == 200, res.text; assert res.json()["linked"] is True


def test_claim_patch_details(claimant_token):
    client = TestClient(app); token, claimant_id = claimant_token; headers = {"Authorization": f"Bearer {token}"}
    res = client.post("/api/v1/claims/voice-session", headers=headers); assert res.status_code == 200; ticket_id = res.json()["ticket_id"]
    res_patch = client.patch(f"/api/v1/claims/{ticket_id}", json={"policy_id": "MOT-5521", "insurance_type": "motor", "event_date": "2024-05-10", "estimated_claim_amount": 45000, "event_description": "Rear-end collision on highway"}, headers=headers)
    assert res_patch.status_code == 200, res_patch.text
    patched = res_patch.json(); assert patched["extracted_data"]["policy_id"] == "MOT-5521"; assert patched["insurance_type"] == "motor"; assert patched["event_date"] == "2024-05-10"; assert patched["estimated_claim_amount"] == 45000


def test_reject_invalid_claim_confirmation(claimant_token):
    client = TestClient(app); token, claimant_id = claimant_token; headers = {"Authorization": f"Bearer {token}"}
    res = client.post("/api/v1/claims/voice-session", headers=headers); assert res.status_code == 200; ticket_id = res.json()["ticket_id"]
    res_conf_missing = client.post(f"/api/v1/claims/{ticket_id}/confirm", headers=headers)
    assert res_conf_missing.status_code == 400
    assert "confirm the claim details" in res_conf_missing.json()["detail"].lower()
    patch_payload = {"policy_id": "FAKE-POLICY-9999", "insurance_type": "motor", "event_date": "2024-05-10", "estimated_claim_amount": 10000}
    client.patch(f"/api/v1/claims/{ticket_id}", json=patch_payload, headers=headers)
    res_conf_invalid = client.post(f"/api/v1/claims/{ticket_id}/confirm", headers=headers)
    assert res_conf_invalid.status_code == 400
    assert "Claim verification failed" in res_conf_invalid.json()["detail"]
