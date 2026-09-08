import pytest
import time
from fastapi.testclient import TestClient
from src.database.models import Claim
from src.database.session import SessionLocal





def test_auth_claim_endpoints(client: TestClient):
    """Test claim endpoints enforce authentication and authorization (ownership)."""
    # 1. Initialize session for USER-A
    headers_a = {"X-User-ID": "USER-A"}
    res = client.post("/api/v1/claims/voice-session", headers=headers_a)
    assert res.status_code == 200
    data = res.json()
    ticket_id = data["ticket_id"]

    # 2. Verify USER-A can retrieve the claim details
    res_get = client.get(f"/api/v1/claims/{ticket_id}", headers=headers_a)
    assert res_get.status_code == 200

    # 3. Verify USER-B is blocked from retrieving the claim details (403 Forbidden)
    headers_b = {"X-User-ID": "USER-B"}
    res_blocked = client.get(f"/api/v1/claims/{ticket_id}", headers=headers_b)
    assert res_blocked.status_code == 403

    # 4. Verify list_claims returns only USER-A's claims for USER-A
    res_list = client.get("/api/v1/claims", headers=headers_a)
    assert res_list.status_code == 200
    claims = res_list.json()["items"]
    assert all(c["ticket_id"] == ticket_id for c in claims)
