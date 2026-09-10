"""Phase 1 API behavior tests."""
from datetime import date, timedelta


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_start_voice_session(client):
    response = client.post("/api/v1/claims/voice-session")
    assert response.status_code == 200
    assert response.json()["ticket_id"].startswith("CLAIM-")


def test_intake_requires_only_missing_common_fields(client):
    response = client.post("/api/v1/claims/intake", json={
        "claim_text": "I had a bike accident yesterday in Bengaluru. Policy MOT-5521. Repair cost is ₹20,000.",
        "input_mode": "text",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["extracted_data"]["event_date"] == (date.today() - timedelta(days=1)).isoformat()
    assert data["extracted_data"]["policy_id"] == "MOT-5521"
    assert data["extracted_data"]["estimated_claim_amount"] == 20000.0
    assert "event_date" not in data["missing_fields"]
    assert "policy_id" not in data["missing_fields"]
    assert "estimated_claim_amount" not in data["missing_fields"]
    assert data["awaiting_confirmation"] is True
    assert data["confirmed"] is False


def test_verify_is_blocked_before_confirmation(client):
    intake = client.post("/api/v1/claims/intake", json={
        "claim_text": "I had a bike accident yesterday in Bengaluru. Policy XYZ123. Repair cost is ₹20,000.",
        "input_mode": "text",
    }).json()
    response = client.post(f"/api/v1/claims/{intake['ticket_id']}/verify")
    assert response.status_code in {200, 400}
    if response.status_code == 200:
        assert response.json()["status"] != "verified"


def test_claim_confirmation_then_verification(client):
    first = client.post("/api/v1/claims/intake", json={
        "claim_text": "I had a bike accident yesterday in Bengaluru. Policy XYZ123. Repair cost is ₹20,000.",
        "input_mode": "text",
    }).json()
    tid = first["ticket_id"]
    second = client.post(f"/api/v1/claims/{tid}/text-turn", json={"text": "Yes, everything looks correct."}).json()
    assert second["confirmed"] is True
    assert second["conversation_status"] == "pending_verification"
    verify = client.post(f"/api/v1/claims/{tid}/verify")
    assert verify.status_code == 200
    assert verify.json()["status"] == "verified"


def test_failed_policy_verification_does_not_verify(client):
    first = client.post("/api/v1/claims/intake", json={
        "claim_text": "I had a bike accident yesterday in Bengaluru. Policy DOES-NOT-EXIST. Repair cost is ₹20,000.",
        "input_mode": "text",
    }).json()
    tid = first["ticket_id"]
    client.post(f"/api/v1/claims/{tid}/text-turn", json={"text": "Yes, everything looks correct."})
    response = client.post(f"/api/v1/claims/{tid}/verify")
    assert response.status_code == 200
    assert response.json()["status"] == "verification_failed"


def test_conversation_history_persists_turns(client):
    session = client.post("/api/v1/claims/voice-session").json()
    tid = session["ticket_id"]
    client.post(f"/api/v1/claims/{tid}/text-turn", json={"text": "I had a bike accident yesterday."})
    history = client.get(f"/api/v1/claims/{tid}/conversation").json()
    assert any("bike" in turn["text"].lower() for turn in history)
