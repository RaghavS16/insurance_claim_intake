import pytest
from io import BytesIO
from fastapi.testclient import TestClient
from src.database.models import User, Claim

def test_auth_and_rbac_flow(client: TestClient):
    # 1. Claimant signup creates CLAIMANT
    signup_data = {
        "full_name": "Test Claimant",
        "email": "test_claimant@example.com",
        "phone": "+919999999999",
        "password": "ClaimantPassword123!",
        "confirm_password": "ClaimantPassword123!"
    }
    res = client.post("/api/v1/auth/signup", json=signup_data)
    assert res.status_code == 200
    user_data = res.json()
    assert user_data["role"] == "CLAIMANT"
    assert "password_hash" not in user_data
    assert "password" not in user_data

    # 2. Public signup cannot create ADJUSTER (role parameter ignored/escalation blocked)
    signup_data_escalated = {
        "full_name": "Hack Adjuster",
        "email": "hack_adjuster@example.com",
        "password": "AdjusterPassword123!",
        "confirm_password": "AdjusterPassword123!",
        "role": "ADJUSTER" # Escalation attempt
    }
    res = client.post("/api/v1/auth/signup", json=signup_data_escalated)
    assert res.status_code == 200
    user_data_esc = res.json()
    # It must still be CLAIMANT, not ADJUSTER!
    assert user_data_esc["role"] == "CLAIMANT"

    # 3. Duplicate email is rejected
    res = client.post("/api/v1/auth/signup", json=signup_data)
    assert res.status_code == 409
    assert "already registered" in res.json()["detail"].lower()

    # 4. Invalid login is rejected
    login_data_invalid = {
        "email": "test_claimant@example.com",
        "password": "WrongPassword123!"
    }
    res = client.post("/api/v1/auth/login", json=login_data_invalid)
    assert res.status_code == 401

    # 5. Valid claimant login succeeds
    login_data = {
        "email": "test_claimant@example.com",
        "password": "ClaimantPassword123!"
    }
    res = client.post("/api/v1/auth/login", json=login_data)
    assert res.status_code == 200
    login_res = res.json()
    assert "access_token" in login_res
    assert login_res["user"]["role"] == "CLAIMANT"
    claimant_token = login_res["access_token"]
    claimant_headers = {"Authorization": f"Bearer {claimant_token}"}

    # 6. Valid adjuster login succeeds
    # Adjusters are seeded with email 'priya@insure.co' and password 'AdjusterPassword123!'
    login_data_adj = {
        "email": "priya@insure.co",
        "password": "AdjusterPassword123!"
    }
    res = client.post("/api/v1/auth/login", json=login_data_adj)
    assert res.status_code == 200
    login_res_adj = res.json()
    assert "access_token" in login_res_adj
    assert login_res_adj["user"]["role"] == "ADJUSTER"
    adjuster_token = login_res_adj["access_token"]
    adjuster_headers = {"Authorization": f"Bearer {adjuster_token}"}

    # 7. Unauthenticated protected endpoint is rejected
    res = client.get("/api/v1/auth/me", headers={"X-Test-No-Fallback": "true"})
    assert res.status_code == 401

    # Verify endpoint is accessible with token
    res = client.get("/api/v1/auth/me", headers=claimant_headers)
    assert res.status_code == 200
    assert res.json()["email"] == "test_claimant@example.com"
    assert "password_hash" not in res.json()





    # 13. Claimant can only access their own claims
    # Claimant creates a claim:
    res = client.post("/api/v1/claims/voice-session", headers=claimant_headers)
    assert res.status_code == 200
    claim_a = res.json()
    ticket_a = claim_a["ticket_id"]

    # Retrieve own claim:
    res = client.get(f"/api/v1/claims/{ticket_a}", headers=claimant_headers)
    assert res.status_code == 200
    assert res.json()["ticket_id"] == ticket_a

    # 14. Claimant cannot access another claimant's claim
    # Create claimant B
    signup_b = {
        "full_name": "Claimant B",
        "email": "claimant_b@example.com",
        "password": "ClaimantPassword123!",
        "confirm_password": "ClaimantPassword123!"
    }
    client.post("/api/v1/auth/signup", json=signup_b)
    login_res_b = client.post("/api/v1/auth/login", json={"email": "claimant_b@example.com", "password": "ClaimantPassword123!"}).json()
    token_b = login_res_b["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Claimant B tries to view Claimant A's claim:
    res = client.get(f"/api/v1/claims/{ticket_a}", headers=headers_b)
    assert res.status_code == 403

    # Claimant B tries to confirm Claimant A's claim:
    res = client.post(f"/api/v1/claims/{ticket_a}/confirm", json={"confirmed": True}, headers=headers_b)
    assert res.status_code == 403



    # Adjuster can access the claim:
    res = client.get(f"/api/v1/claims/{ticket_a}", headers=adjuster_headers)
    assert res.status_code == 200
