import pytest


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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
    """Simulates the field-prompt loop: first call is incomplete, second call
    (same ticket_id, additional text) completes it."""
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


def test_valid_claim_approved_end_to_end(client):
    """Happy path: complete fields, no documents required (auto requires docs
    in this config, so this test explicitly uses claim_type-agnostic amount
    under the limit and skips document upload only if claim_type needs none).
    For 'auto', documents ARE required, so this test uploads them."""
    intake = client.post("/api/v1/claims/intake", json={
        "claim_text": "My car was hit by a truck on 2025-07-15 in Mumbai. Policy XYZ123. Repair cost is 50000 rupees.",
        "input_mode": "text",
    }).json()
    ticket_id = intake["ticket_id"]
    assert intake["missing_fields"] == []

    # auto claims require damage_photo + repair_estimate
    client.post(
        f"/api/v1/claims/{ticket_id}/documents",
        data={"document_type": "damage_photo"},
        files={"file": ("damage.jpg", b"fake-image-bytes", "image/jpeg")},
    )
    client.post(
        f"/api/v1/claims/{ticket_id}/documents",
        data={"document_type": "repair_estimate"},
        files={"file": ("estimate.pdf", b"fake-pdf-bytes", "application/pdf")},
    )

    response = client.post(f"/api/v1/claims/{ticket_id}/confirm", json={"confirmed": True})
    assert response.status_code == 200
    data = response.json()

    assert data["final_decision"] == "approved"
    assert data["closure_status"] == "closed"
    assert data["coverage_eligible"] is True
    assert data["deductible_amount"] is not None
    assert data["payout_amount"] is not None
    assert data["assigned_adjuster"] is not None
    assert data["response_message"] == data["spoken_response"]


def test_claim_missing_documents_prompts_upload(client):
    """Auto claim with complete fields but no documents uploaded -> need_documents."""
    intake = client.post("/api/v1/claims/intake", json={
        "claim_text": "My car was hit on 2025-07-15. Policy XYZ123. Repair cost is 50000 rupees.",
        "input_mode": "text",
    }).json()
    ticket_id = intake["ticket_id"]

    response = client.post(f"/api/v1/claims/{ticket_id}/confirm", json={"confirmed": True})
    data = response.json()

    assert data["final_decision"] == "need_documents"
    assert data["closure_status"] == "awaiting_user"
    assert "damage_photo" in data["missing_documents"]


def test_document_upload_wrong_type_rejected(client):
    """Uploading a document_type not valid for the claim's claim_type is rejected
    with a message asking the user to re-upload the correct one."""
    intake = client.post("/api/v1/claims/intake", json={
        "claim_text": "My car was hit on 2025-07-15. Policy XYZ123. Repair cost is 50000 rupees.",
        "input_mode": "text",
    }).json()
    ticket_id = intake["ticket_id"]

    response = client.post(
        f"/api/v1/claims/{ticket_id}/documents",
        data={"document_type": "medical_bill"},  # not valid for auto
        files={"file": ("random.pdf", b"fake-bytes", "application/pdf")},
    )
    assert response.status_code == 400
    assert "re-upload" in response.json()["detail"]


def test_invalid_policy_routes_to_manual_review(client):
    """Expired/invalid policy -> rejected, routed to manual review."""
    intake = client.post("/api/v1/claims/intake", json={
        "claim_text": "My car had an accident on 2025-01-10. Policy AUTO789. Damage cost 20000.",
        "input_mode": "text",
    }).json()
    ticket_id = intake["ticket_id"]

    response = client.post(f"/api/v1/claims/{ticket_id}/confirm", json={"confirmed": True})
    data = response.json()

    assert data["final_decision"] == "manual_review"
    assert data["closure_status"] == "pending_review"


def test_claim_exceeds_coverage_denied(client):
    """Claimed amount over policy limit -> denied, closed immediately.
    Uses 'business' claim_type which has no required documents so the
    evaluation graph reaches coverage_checker without needing doc uploads."""
    intake = client.post("/api/v1/claims/intake", json={
        "claim_text": "My business was damaged on 2025-06-01. Policy XYZ123. Business loss is 900000 rupees. Claim type is business.",
        "input_mode": "text",
    }).json()
    ticket_id = intake["ticket_id"]

    response = client.post(f"/api/v1/claims/{ticket_id}/confirm", json={"confirmed": True})
    data = response.json()

    assert data["coverage_eligible"] is False
    assert data["final_decision"] == "denied"
    assert data["closure_status"] == "closed"



def test_high_fraud_score_flagged_not_closed(client):
    """Future date + near-limit amount -> flagged_for_review, closure pending
    (NOT closed -- distinguishes flagged claims from auto approved/denied)."""
    intake = client.post("/api/v1/claims/intake", json={
        "claim_text": "My car was damaged on 2027-01-01. Policy XYZ123. Repair cost is 480000 rupees.",
        "input_mode": "text",
    }).json()
    ticket_id = intake["ticket_id"]

    client.post(
        f"/api/v1/claims/{ticket_id}/documents",
        data={"document_type": "damage_photo"},
        files={"file": ("damage.jpg", b"fake-bytes", "image/jpeg")},
    )
    client.post(
        f"/api/v1/claims/{ticket_id}/documents",
        data={"document_type": "repair_estimate"},
        files={"file": ("estimate.pdf", b"fake-bytes", "application/pdf")},
    )

    response = client.post(f"/api/v1/claims/{ticket_id}/confirm", json={"confirmed": True})
    data = response.json()

    assert "future_incident_date" in data["fraud_flags"]
    assert data["fraud_score"] >= 0.7
    assert data["final_decision"] == "flagged_for_review"
    assert data["closure_status"] == "pending_review"  # regression test: must NOT be "closed"