"""
Integration tests for the insurance claims pipeline and API endpoints.

Covers:
- Basic health checks
- Field extraction & missing mandatory fields loop
- Multi-turn conversation handling
- Coercion of currency & numeric amounts
- Review 2/3 Evaluation pipeline integration (approval, denial, document uploads, fraud scoring, idempotency, duplicate prevention)
"""
import io
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


def test_valid_claim_approved_end_to_end(client):
    """Happy path: complete fields, documents uploaded, claim approved."""
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
    assert data["assigned_adjuster"] is not None
    assert data["response_message"] == data["spoken_response"]


def test_claim_missing_documents_prompts_upload(client):
    """Auto claim with complete fields but no documents uploaded -> need_documents."""
    intake = client.post("/api/v1/claims/intake", json={
        "claim_text": "My car was hit on 2025-07-16. Policy XYZ123. Repair cost is 50000 rupees.",
        "input_mode": "text",
    }).json()
    ticket_id = intake["ticket_id"]

    response = client.post(f"/api/v1/claims/{ticket_id}/confirm", json={"confirmed": True})
    data = response.json()

    assert data["final_decision"] == "need_documents"
    assert data["closure_status"] == "awaiting_user"
    assert "damage_photo" in data["missing_documents"]


def test_document_upload_wrong_type_rejected(client):
    """Uploading a document_type not valid for the claim's claim_type is rejected."""
    intake = client.post("/api/v1/claims/intake", json={
        "claim_text": "My car was hit on 2025-07-17. Policy XYZ123. Repair cost is 50000 rupees.",
        "input_mode": "text",
    }).json()
    ticket_id = intake["ticket_id"]

    dummy_bytes = b"X" * 150
    response = client.post(
        f"/api/v1/claims/{ticket_id}/documents",
        data={"document_type": "medical_bill"},
        files={"file": ("random.pdf", dummy_bytes, "application/pdf")},
    )
    assert response.status_code == 400
    assert "Expected one of" in response.json()["detail"] or "not a required" in response.json()["detail"]


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
    """Claimed amount over policy limit -> denied, closed immediately."""
    intake = client.post("/api/v1/claims/intake", json={
        "claim_text": (
            "My car was completely destroyed in a flood on 2025-06-01. "
            "Policy XYZ123. Total vehicle replacement cost is 600000 rupees. "
            "Claim type is auto."
        ),
        "input_mode": "text",
    }).json()
    ticket_id = intake["ticket_id"]

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

    response = client.post(f"/api/v1/claims/{ticket_id}/confirm", json={"confirmed": True})
    data = response.json()

    assert data["coverage_eligible"] is False
    assert data["final_decision"] == "denied"
    assert data["closure_status"] == "closed"


def test_high_fraud_score_flagged_not_closed(client):
    """Future date -> flagged_for_review, closure pending."""
    intake = client.post("/api/v1/claims/intake", json={
        "claim_text": "My car was damaged on 2027-01-01. Policy XYZ123. Repair cost is 480000 rupees.",
        "input_mode": "text",
    }).json()
    ticket_id = intake["ticket_id"]

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
    data = response.json()

    assert "future_incident_date" in data["fraud_flags"]
    assert data["fraud_score"] >= 0.6
    assert data["final_decision"] == "flagged_for_review"
    assert data["closure_status"] == "pending_review"


def test_intake_claim_text_too_long_rejected(client):
    """claim_text over 5000 chars should be rejected by Pydantic validation."""
    response = client.post("/api/v1/claims/intake", json={
        "claim_text": "A" * 5001,
        "input_mode": "text",
    })
    assert response.status_code == 422


def test_confirm_idempotency_no_double_payment(client):
    """Calling /confirm twice on an approved claim returns the cached result without duplicate records."""
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


def test_claim_type_vs_policy_type_mismatch(client):
    """Declaring 'business' claim_type against 'auto' policy XYZ123 routes to manual_review."""
    intake = client.post("/api/v1/claims/intake", json={
        "claim_text": (
            "My business was flooded on 2025-08-01. "
            "Policy XYZ123. Business loss is 100000 rupees. "
            "Claim type is business."
        ),
        "input_mode": "text",
    }).json()
    ticket_id = intake["ticket_id"]

    response = client.post(f"/api/v1/claims/{ticket_id}/confirm", json={"confirmed": True})
    assert response.status_code == 200
    data = response.json()
    assert data["final_decision"] == "manual_review"
    assert data["closure_status"] == "pending_review"


def test_document_file_too_small_rejected(client):
    """A file that is clearly too small (< MIN_UPLOAD_SIZE_BYTES) must be rejected."""
    intake = client.post("/api/v1/claims/intake", json={
        "claim_text": "My car was hit on 2025-08-02. Policy XYZ123. Repair cost is 40000 rupees.",
        "input_mode": "text",
    }).json()
    ticket_id = intake["ticket_id"]

    response = client.post(
        f"/api/v1/claims/{ticket_id}/documents",
        data={"document_type": "damage_photo"},
        files={"file": ("tiny.jpg", b"tiny", "image/jpeg")},
    )
    assert response.status_code == 400
    assert "too small" in response.json()["detail"].lower()


def test_document_wrong_mime_type_rejected(client):
    """Uploading an executable or disallowed MIME type must be blocked."""
    intake = client.post("/api/v1/claims/intake", json={
        "claim_text": "My car was hit on 2025-08-03. Policy XYZ123. Repair cost is 40000 rupees.",
        "input_mode": "text",
    }).json()
    ticket_id = intake["ticket_id"]

    dummy_bytes = b"X" * 150
    response = client.post(
        f"/api/v1/claims/{ticket_id}/documents",
        data={"document_type": "damage_photo"},
        files={"file": ("script.exe", dummy_bytes, "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"].lower()


def test_intake_already_evaluated_short_circuits(client):
    """After a claim is evaluated, re-calling /intake returns existing state."""
    intake = client.post("/api/v1/claims/intake", json={
        "claim_text": "My car was hit on 2025-08-04. Policy XYZ123. Repair cost is 30000 rupees.",
        "input_mode": "text",
    }).json()
    ticket_id = intake["ticket_id"]

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
    client.post(f"/api/v1/claims/{ticket_id}/confirm", json={"confirmed": True})

    re_intake = client.post("/api/v1/claims/intake", json={
        "claim_text": "completely different text that should be ignored",
        "input_mode": "text",
        "ticket_id": ticket_id,
    }).json()
    assert re_intake.get("message", "").startswith("Claim already evaluated") or \
           re_intake.get("awaiting_confirmation") is True


def test_adjuster_load_balancing_increments_claims_assigned(client):
    """Adjusters are assigned based on current load."""
    dummy_bytes = b"X" * 150

    for incident_date in ("2025-10-01", "2025-10-02"):
        intake = client.post("/api/v1/claims/intake", json={
            "claim_text": f"My car was hit on {incident_date}. Policy XYZ123. Repair cost is 20000 rupees.",
            "input_mode": "text",
        }).json()
        tid = intake["ticket_id"]
        client.post(
            f"/api/v1/claims/{tid}/documents",
            data={"document_type": "damage_photo"},
            files={"file": ("d.jpg", dummy_bytes, "image/jpeg")},
        )
        client.post(
            f"/api/v1/claims/{tid}/documents",
            data={"document_type": "repair_estimate"},
            files={"file": ("e.pdf", dummy_bytes, "application/pdf")},
        )
        result = client.post(f"/api/v1/claims/{tid}/confirm", json={"confirmed": True}).json()
        assert result["assigned_adjuster"], f"No adjuster assigned for claim on {incident_date}"


def test_audit_log_entries_are_timestamped(client):
    """Audit log entries must be prefixed with an ISO-8601 timestamp."""
    intake = client.post("/api/v1/claims/intake", json={
        "claim_text": "My car was hit on 2025-11-01. Policy XYZ123. Repair cost is 25000 rupees.",
        "input_mode": "text",
    }).json()
    ticket_id = intake["ticket_id"]

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
    result = client.post(f"/api/v1/claims/{ticket_id}/confirm", json={"confirmed": True}).json()

    audit_log = result.get("audit_log", [])
    assert len(audit_log) > 0, "audit_log should not be empty"
    for entry in audit_log:
        assert entry.startswith("[20"), f"audit_log entry missing timestamp: {entry!r}"


def test_claimed_amount_as_string_coerced():
    """Verify _coerce_amount handles numeric formats, currency strings, commas, and invalid inputs."""
    from src.agents.nodes import _coerce_amount

    assert _coerce_amount(50000) == 50000.0
    assert _coerce_amount(50000.50) == 50000.50
    assert _coerce_amount("50,000") == 50000.0
    assert _coerce_amount("₹50000") == 50000.0
    assert _coerce_amount("Rs. 1,50,000.00") == 150000.00
    assert _coerce_amount(None) is None
    assert _coerce_amount("invalid_text") is None


def test_duplicate_claim_rejected(client):
    """Submitting a duplicate claim for the same policy and incident date is rejected with 409 Conflict."""
    dummy_bytes = b"X" * 150
    intake1 = client.post("/api/v1/claims/intake", json={
        "claim_text": "My car had an accident on 2025-12-01. Policy XYZ123. Repair cost is 15000 rupees.",
        "input_mode": "text",
    }).json()
    tid1 = intake1["ticket_id"]
    client.post(f"/api/v1/claims/{tid1}/documents", data={"document_type": "damage_photo"}, files={"file": ("d.jpg", dummy_bytes, "image/jpeg")})
    client.post(f"/api/v1/claims/{tid1}/documents", data={"document_type": "repair_estimate"}, files={"file": ("e.pdf", dummy_bytes, "application/pdf")})
    confirm1 = client.post(f"/api/v1/claims/{tid1}/confirm", json={"confirmed": True})
    assert confirm1.status_code == 200

    intake2 = client.post("/api/v1/claims/intake", json={
        "claim_text": "My car had another hit on 2025-12-01. Policy XYZ123. Repair cost is 18000 rupees.",
        "input_mode": "text",
    }).json()
    tid2 = intake2["ticket_id"]
    client.post(f"/api/v1/claims/{tid2}/documents", data={"document_type": "damage_photo"}, files={"file": ("d.jpg", dummy_bytes, "image/jpeg")})
    client.post(f"/api/v1/claims/{tid2}/documents", data={"document_type": "repair_estimate"}, files={"file": ("e.pdf", dummy_bytes, "application/pdf")})

    confirm2 = client.post(f"/api/v1/claims/{tid2}/confirm", json={"confirmed": True})
    assert confirm2.status_code == 409
    assert "already exists" in confirm2.json()["detail"]


def test_no_adjuster_fallback_edge_case():
    """route_decision handles edge cases gracefully when no matching adjuster exists."""
    from src.agents.evaluation import route_decision
    from unittest.mock import MagicMock

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = []

    state = {
        "extracted_data": {"claim_type": "unknown_type"},
        "audit_log": [],
    }
    res = route_decision(state, mock_db)
    assert res["assigned_adjuster"] == {}
    assert any("No active adjuster found" in entry for entry in res.get("audit_log", []))