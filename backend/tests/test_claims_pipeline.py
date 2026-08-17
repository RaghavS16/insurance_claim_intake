"""
Integration tests for the insurance claims intake pipeline and API endpoints (Phase 1).

Covers:
- Basic health checks & environment verification
- Field extraction & missing mandatory fields loop
- Multi-turn conversation handling
- Coercion of currency & numeric amounts
- Strict 6 insurance types enforcement
- Claim confirmation & structured claim persistence
- API failure and validation error handling
- Settings and configuration validation
"""
import io
import pytest
from src.config import Settings


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_config_validation():
    # Valid settings
    s = Settings(ENVIRONMENT="development", DATABASE_URL="sqlite:///test.db")
    assert s.ENVIRONMENT == "development"
    assert s.allowed_origins_list == ["http://localhost:3000"]

    # Invalid environment
    with pytest.raises(ValueError):
        Settings(ENVIRONMENT="invalid_env", DATABASE_URL="sqlite:///test.db")


def test_start_voice_session(client):
    response = client.post("/api/v1/claims/voice-session")
    assert response.status_code == 200
    data = response.json()
    assert data["ticket_id"].startswith("CLAIM-")
    assert "tell me what happened" in data["initial_message"].lower()


def test_intake_missing_fields_prompts_user(client):
    """Incomplete claim text -> missing_fields populated, awaiting_confirmation False."""
    payload = {"claim_text": "My car was damaged.", "input_mode": "text"}
    response = client.post("/api/v1/claims/intake", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["awaiting_confirmation"] is False
    assert "policy_id" in data["missing_fields"]
    assert data["ticket_id"].startswith("CLAIM-")


def test_intake_multi_turn_fills_missing_fields(client):
    """Simulates the field-prompt loop: first call is incomplete, second call completes it."""
    first = client.post("/api/v1/claims/intake", json={
        "claim_text": "My car was damaged on 2025-07-15. Repair cost is 50000 rupees.",
        "input_mode": "text",
    }).json()
    ticket_id = first["ticket_id"]
    assert "policy_id" in first["missing_fields"]

    second = client.post("/api/v1/claims/intake", json={
        "claim_text": "Policy XYZ123.",
        "input_mode": "text",
        "ticket_id": ticket_id,
    }).json()

    assert second["ticket_id"] == ticket_id
    assert second["missing_fields"] == []
    assert second["awaiting_confirmation"] is True
    assert second["extracted_data"]["policy_id"] == "XYZ123"


def test_confirm_before_fields_complete_rejected(client):
    """Confirming before mandatory fields are complete should fail."""
    intake = client.post("/api/v1/claims/intake", json={
        "claim_text": "My car was damaged.",
        "input_mode": "text",
    }).json()

    response = client.post(f"/api/v1/claims/{intake['ticket_id']}/confirm", json={"confirmed": True})
    assert response.status_code == 400


def test_valid_motor_claim_confirmed_end_to_end(client):
    """Happy path: complete fields, claim confirmed and persisted."""
    intake = client.post("/api/v1/claims/intake", json={
        "claim_text": "My car was hit by a truck on 2025-07-15 in Mumbai. Policy XYZ123. Repair cost is 50000 rupees.",
        "input_mode": "text",
    }).json()
    ticket_id = intake["ticket_id"]
    assert intake["missing_fields"] == []

    dummy_bytes = b"X" * 150
    client.post(
        f"/api/v1/claims/{ticket_id}/documents",
        data={"document_type": "damage_photo"},
        files={"file": ("damage.jpg", dummy_bytes, "image/jpeg")},
    )
    client.post(
        f"/api/v1/claims/{ticket_id}/documents",
        data={"document_type": "repair_estimate"},
        files={"file": ("estimate.pdf", dummy_bytes, "application/pdf")},
    )

    response = client.post(f"/api/v1/claims/{ticket_id}/confirm", json={"confirmed": True})
    assert response.status_code == 200
    data = response.json()

    assert data["final_decision"] == "approved"
    assert data["closure_status"] == "closed"
    assert data["coverage_eligible"] is True
    assert data["deductible_amount"] is not None
    assert data["payout_amount"] is not None


def test_claim_missing_documents_prompts_upload(client):
    """Motor claim with complete fields but no documents uploaded -> need_documents."""
    intake = client.post("/api/v1/claims/intake", json={
        "claim_text": "My car was dented on 2025-07-15. Policy XYZ123. Repair cost is 40000 rupees.",
        "input_mode": "text",
    }).json()
    ticket_id = intake["ticket_id"]

    response = client.post(f"/api/v1/claims/{ticket_id}/confirm", json={"confirmed": True})
    assert response.status_code == 200
    data = response.json()

    assert data["final_decision"] == "need_documents"
    assert data["closure_status"] == "awaiting_user"


def test_intake_claim_text_too_long_rejected(client):
    """claim_text over 5000 chars should be rejected by Pydantic validation."""
    response = client.post("/api/v1/claims/intake", json={
        "claim_text": "A" * 5001,
        "input_mode": "text",
    })
    assert response.status_code == 422


def test_confirm_idempotency_no_double_payment(client):
    """Calling /confirm twice on an approved claim returns cached result."""
    intake = client.post("/api/v1/claims/intake", json={
        "claim_text": "My car was hit on 2025-09-01. Policy XYZ123. Repair cost is 30000 rupees.",
        "input_mode": "text",
    }).json()
    ticket_id = intake["ticket_id"]
    assert intake["missing_fields"] == []

    dummy_bytes = b"X" * 150
    client.post(
        f"/api/v1/claims/{ticket_id}/documents",
        data={"document_type": "damage_photo"},
        files={"file": ("d.jpg", dummy_bytes, "image/jpeg")},
    )
    client.post(
        f"/api/v1/claims/{ticket_id}/documents",
        data={"document_type": "repair_estimate"},
        files={"file": ("e.pdf", dummy_bytes, "application/pdf")},
    )

    first = client.post(f"/api/v1/claims/{ticket_id}/confirm", json={"confirmed": True})
    assert first.status_code == 200
    assert first.json()["final_decision"] == "approved"

    second = client.post(f"/api/v1/claims/{ticket_id}/confirm", json={"confirmed": True})
    assert second.status_code == 200
    second_data = second.json()
    assert second_data["final_decision"] == "approved"
    assert second_data.get("_cached") is True


def test_get_conversation_history(client):
    session = client.post("/api/v1/claims/voice-session").json()
    tid = session["ticket_id"]

    intake = client.post("/api/v1/claims/intake", json={
        "ticket_id": tid,
        "claim_text": "I had an accident with my bike yesterday.",
        "input_mode": "text",
    }).json()

    history = client.get(f"/api/v1/claims/{tid}/conversation").json()
    assert len(history) >= 1
    assert any("bike" in t["text"].lower() for t in history)


def test_get_claim_by_ticket_id(client):
    intake = client.post("/api/v1/claims/intake", json={
        "claim_text": "My laptop was hacked yesterday in a cyber attack. Policy CYB-8820. Loss is 100000 rupees.",
        "input_mode": "text",
    }).json()
    tid = intake["ticket_id"]

    res = client.get(f"/api/v1/claims/{tid}")
    assert res.status_code == 200
    data = res.json()
    assert data["ticket_id"] == tid
    assert data["claim_type"] == "cyber"
    assert data["claimed_amount"] == 100000.0


def test_nonexistent_ticket_id_returns_404(client):
    res = client.get("/api/v1/claims/CLAIM-NONEXISTENT")
    assert res.status_code == 404