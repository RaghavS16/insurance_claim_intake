from fastapi.testclient import TestClient


def test_auth_and_rbac_flow(client: TestClient):
    claimant_signup = {
        "full_name": "Test Claimant",
        "email": "test_claimant@example.com",
        "phone": "+919999999999",
        "password": "ClaimantPassword123!",
        "confirm_password": "ClaimantPassword123!",
        "role": "CLAIMANT",
    }
    res = client.post("/api/v1/auth/signup", json=claimant_signup)
    assert res.status_code == 200
    assert res.json()["role"] == "CLAIMANT"
    assert "password_hash" not in res.json()

    # Role escalation without the private adjuster code must fail.
    res = client.post("/api/v1/auth/signup", json={
        "full_name": "Blocked Adjuster",
        "email": "blocked_adjuster@example.com",
        "password": "AdjusterPassword123!",
        "confirm_password": "AdjusterPassword123!",
        "role": "ADJUSTER",
    })
    assert res.status_code == 403

    # Valid adjuster registration is allowed only with the configured private code.
    from src.config import settings
    settings.ADJUSTER_SIGNUP_CODE = "test-adjuster-code"
    res = client.post("/api/v1/auth/signup", json={
        "full_name": "New Adjuster",
        "email": "new_adjuster@example.com",
        "password": "AdjusterPassword123!",
        "confirm_password": "AdjusterPassword123!",
        "role": "ADJUSTER",
        "adjuster_code": "test-adjuster-code",
    })
    assert res.status_code == 200
    assert res.json()["role"] == "ADJUSTER"

    # Duplicate email is rejected.
    res = client.post("/api/v1/auth/signup", json=claimant_signup)
    assert res.status_code == 409

    # Invalid login is rejected.
    res = client.post("/api/v1/auth/login", json={"email": claimant_signup["email"], "password": "WrongPassword123!"})
    assert res.status_code == 401

    # Valid claimant login succeeds.
    res = client.post("/api/v1/auth/login", json={"email": claimant_signup["email"], "password": claimant_signup["password"]})
    assert res.status_code == 200
    claimant_token = res.json()["access_token"]
    assert res.json()["user"]["role"] == "CLAIMANT"
    claimant_headers = {"Authorization": f"Bearer {claimant_token}"}

    # Seeded adjuster login succeeds.
    res = client.post("/api/v1/auth/login", json={"email": "priya@insure.co", "password": "AdjusterPassword123!"})
    assert res.status_code == 200
    adjuster_token = res.json()["access_token"]
    assert res.json()["user"]["role"] == "ADJUSTER"
    adjuster_headers = {"Authorization": f"Bearer {adjuster_token}"}

    res = client.get("/api/v1/auth/me", headers={"X-Test-No-Fallback": "true"})
    assert res.status_code == 401
    res = client.get("/api/v1/auth/me", headers=claimant_headers)
    assert res.status_code == 200
    assert res.json()["role"] == "CLAIMANT"
    assert "password_hash" not in res.json()

    # Claim ownership remains enforced.
    res = client.post("/api/v1/claims/voice-session", headers=claimant_headers)
    assert res.status_code == 200
    ticket_a = res.json()["ticket_id"]
    assert client.get(f"/api/v1/claims/{ticket_a}", headers=claimant_headers).status_code == 200

    signup_b = {
        "full_name": "Claimant B",
        "email": "claimant_b@example.com",
        "password": "ClaimantPassword123!",
        "confirm_password": "ClaimantPassword123!",
    }
    assert client.post("/api/v1/auth/signup", json=signup_b).status_code == 200
    token_b = client.post("/api/v1/auth/login", json={"email": signup_b["email"], "password": signup_b["password"]}).json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}
    assert client.get(f"/api/v1/claims/{ticket_a}", headers=headers_b).status_code == 403
    assert client.post(f"/api/v1/claims/{ticket_a}/verify", headers=headers_b).status_code == 403

    # Adjusters may inspect claims but cannot start claimant intake.
    assert client.get(f"/api/v1/claims/{ticket_a}", headers=adjuster_headers).status_code == 200
    assert client.post("/api/v1/claims/voice-session", headers=adjuster_headers).status_code == 403
