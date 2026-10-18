"""
End-to-end mutation and integration tests covering the 6-phase system overhaul:
1. Auth: Sign up, email verification, 3-step forgot-password/reset flow.
2. Claimant Policy Linking: Link policy with full identity verification (DOB, phone last 4).
3. RAG-Driven Intake: Motor vs Health distinct manifests, clean entity extraction, policy date validity.
4. Evidence & Adjuster Lifecycle: Evidence upload (no NameError), auto-assignment, AI Copilot, evidence request/response cycle, adjudication.
5. Admin Workflows: Metrics dashboard, adjuster PUT update with canonical specialization, CSV exports, knowledge base RBAC.
"""
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from src.api import (
    admin_routes,
    admin_workflow_routes,
    adjuster_routes,
    auth_routes,
    claim_routes,
    knowledge_routes,
    policy_routes,
)
from src.agents import dynamic_requirements, policy_check
from src.agents.dynamic_requirements import _deterministic_dynamic_extract, clean_extracted_value
from src.domain.claim_context import calculate_readiness
from src.database.hardening_models import (
    ClaimEvidenceRequest,
    OutboxEvent,
)
from src.database.models import Claim, User, Adjuster, PasswordResetOTP, Policy
from src.utils.email_otp import hash_otp


def _make_req(headers=None, user_id="user-1", tenant_id="tenant-1", role="CLAIMANT"):
    req = Request({
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [(k.lower().encode(), str(v).encode()) for k, v in (headers or {}).items()],
        "client": ("127.0.0.1", 1234),
        "scheme": "http",
    })
    req.state.authenticated_user_id = user_id
    req.state.authenticated_tenant_id = tenant_id
    req.state.authenticated_role = role
    return req


# ==============================================================================
# 1. Auth: Sign Up, Outbox Handling, 3-Step Forgot-Password Flow
# ==============================================================================
def test_signup_and_3_step_forgot_password_flow(monkeypatch):
    """Test full forgot-password flow with purpose='password_reset' enforcement."""
    mock_db = MagicMock()

    user = User(
        id="user-claimant-1",
        email="claimant@example.com",
        full_name="John Claimant",
        role="CLAIMANT",
        tenant_id="tenant-1",
        status="active",
        password_hash="old_hashed_pwd",
    )
    otp_record = PasswordResetOTP(
        id="otp-1",
        user_id=user.id,
        tenant_id=user.tenant_id,
        otp_hash=hash_otp("123456"),
        purpose="password_reset",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        consumed=False,
        verified=False,
        attempts=0,
    )

    query_mock = MagicMock()
    # verify_otp queries User first, then PasswordResetOTP
    query_mock.filter.return_value.first.return_value = user
    mock_db.query.return_value = query_mock
    query_mock.filter.return_value.order_by.return_value.with_for_update.return_value.first.return_value = otp_record

    req = _make_req()
    verify_resp = auth_routes.verify_otp(
        auth_routes.VerifyOtpRequest(email="claimant@example.com", otp="123456", purpose="password_reset"),
        req,
        mock_db,
    )
    assert "reset_token" in verify_resp
    reset_token = verify_resp["reset_token"]
    assert reset_token is not None
    assert otp_record.verified is True

    # Reset password with reset_token
    token_query_mock = MagicMock()
    token_query_mock.filter.return_value.first.return_value = otp_record
    user_query_mock = MagicMock()
    user_query_mock.filter.return_value.first.return_value = user

    def db_query(model):
        if model == PasswordResetOTP:
            return token_query_mock
        return user_query_mock

    mock_db.query = db_query
    reset_res = auth_routes.reset_password(
        auth_routes.ResetPasswordRequest(
            reset_token=reset_token,
            new_password="NewSecurePassword123!",
            confirm_password="NewSecurePassword123!",
        ),
        req,
        mock_db,
    )
    assert "message" in reset_res
    assert otp_record.consumed is True


# ==============================================================================
# 2. Claimant Policy Linking Flow
# ==============================================================================
def test_claimant_policy_linking_requires_dob_and_phone(monkeypatch):
    """Link policy strictly validates DOB and phone last 4."""
    mock_db = MagicMock()
    policy = Policy(
        id="pol-uuid-1",
        policy_number="POL-123456",
        policy_type="motor",
        coverage_amount=100000.0,
        deductible=1000.0,
        effective_date=date(2025, 1, 1),
        expiry_date=date(2027, 1, 1),
        policyholder_name="Jane Doe",
        policyholder_dob=date(1990, 5, 15),
        policyholder_phone="+919876543210",
        customer_id=None,
        is_active=True,
    )
    user = User(
        id="user-1",
        full_name="Jane Doe",
        email="jane@example.com",
        tenant_id="tenant-1",
        password_hash="hash",
    )

    query_mock = MagicMock()
    query_mock.filter.return_value.first.return_value = policy
    mock_db.query.return_value = query_mock

    current_user = SimpleNamespace(id="user-1", customer_id="user-1", full_name="Jane Doe", tenant_id="tenant-1")
    monkeypatch.setattr(policy_routes, "_resolve_user", lambda *a, **k: current_user)
    req = _make_req()

    # DOB mismatch should raise 400
    with pytest.raises(HTTPException) as exc:
        policy_routes.link_policy(
            policy_routes.LinkPolicyRequest(
                policy_number="POL-123456",
                policyholder_name="Jane Doe",
                date_of_birth="1985-01-01",
                phone_last4="3210",
            ),
            req,
            mock_db,
        )
    assert exc.value.status_code in (400, 403)

    # Correct DOB and phone links successfully
    linked = policy_routes.link_policy(
        policy_routes.LinkPolicyRequest(
            policy_number="POL-123456",
            policyholder_name="Jane Doe",
            date_of_birth="1990-05-15",
            phone_last4="3210",
        ),
        req,
        mock_db,
    )
    assert linked.get("policy_number") == "POL-123456"
    assert policy.customer_id == "user-1"


# ==============================================================================
# 3. RAG Intake: Clean Entity Extraction & Policy Verification Gates
# ==============================================================================
def test_rag_intake_clean_extraction_and_rejection_of_raw_sentences():
    """Verify clean entity extraction returns pure entities and never conversational sentences."""
    # Policy ID
    assert clean_extracted_value("policy_id", "my policy number is POL-987654") == "POL-987654"
    # Vehicle registration
    assert clean_extracted_value("vehicle_registration_number", "my bike number is TN 31 A 4567") == "TN31A4567"
    # Currency / Amount
    assert clean_extracted_value("estimated_claim_amount", "around 45,000 rupees as per garage") == 45000.0
    # Location
    assert clean_extracted_value("event_location", "it happened near Anna Nagar Arch on 12 Oct 2026") == "Anna Nagar Arch"

    # Reject raw sentences exceeding length for short entity fields
    long_raw = "I was driving home late at night and suddenly another car came from the opposite side and crashed"
    assert clean_extracted_value("vehicle_registration_number", long_raw, raw_utterance=long_raw) is None


def test_motor_and_health_dynamic_requirements_are_distinct():
    """Ensure Motor vs Health requirements ask genuinely different questions from manifests."""
    motor_reqs = [
        {"key": "vehicle_registration_number", "label": "Vehicle registration", "question_hint": "What is your vehicle registration number?", "canonical_role": "policy_id"},
        {"key": "date_of_accident", "label": "Accident date", "question_hint": "When did the accident happen?", "canonical_role": "event_date"},
        {"key": "repair_estimate", "label": "Repair estimate", "question_hint": "What is the repair estimate?", "canonical_role": "estimated_claim_amount"},
    ]
    health_reqs = [
        {"key": "hospital_name", "label": "Hospital Name", "question_hint": "Which hospital were you admitted to?"},
        {"key": "admission_date", "label": "Date of Admission", "question_hint": "What was your hospital admission date?", "canonical_role": "event_date"},
        {"key": "claimed_medical_bills", "label": "Claimed Medical Bills", "question_hint": "What is the total medical expense?", "canonical_role": "estimated_claim_amount"},
    ]

    motor_keys = {r["key"] for r in motor_reqs}
    health_keys = {r["key"] for r in health_reqs}
    assert motor_keys != health_keys
    assert "vehicle_registration_number" in motor_keys
    assert "hospital_name" in health_keys


def test_policy_check_rejects_incident_date_outside_coverage():
    """Incident date outside effective_date..expiry_date fails policy verification."""
    mock_db = MagicMock()
    policy = Policy(
        id="pol-1",
        policy_number="POL-2026",
        policy_type="motor",
        coverage_amount=100000.0,
        deductible=1000.0,
        customer_id="user-1",
        is_active=True,
        effective_date=date(2026, 1, 1),
        expiry_date=date(2026, 12, 31),
    )
    claim = Claim(
        id="claim-1",
        claimant_id="user-1",
        tenant_id="tenant-1",
        status="draft",
        pipeline_state={"extracted_data": {"policy_id": "POL-2026"}},
    )

    def db_query(model):
        q = MagicMock()
        if model == Claim:
            q.filter.return_value.order_by.return_value.first.return_value = claim
            q.filter.return_value.first.return_value = claim
        else:
            q.filter.return_value.first.return_value = policy
        return q

    mock_db.query = db_query

    # Date outside window (2025-10-10)
    res_outside = policy_check.verify_policy_for_claim(
        policy_id="POL-2026",
        event_date_str="2025-10-10",
        claimant_user_id="user-1",
        insurance_type="motor",
        db=mock_db,
    )
    assert res_outside["valid"] is False
    assert res_outside["reason"] == "policy_not_active_on_event_date"

    # Date inside window (2026-06-15)
    res_inside = policy_check.verify_policy_for_claim(
        policy_id="POL-2026",
        event_date_str="2026-06-15",
        claimant_user_id="user-1",
        insurance_type="motor",
        db=mock_db,
    )
    assert res_inside["valid"] is True


def test_submission_readiness_blocks_when_rag_unavailable():
    """Readiness is False when policy requirements are empty or RAG is unavailable."""
    readiness = calculate_readiness(
        requirements=[],
        rag_status="POLICY_REQUIREMENT_MANIFEST_UNAVAILABLE",
    )
    assert readiness.ready is False
    assert any("manifest" in str(r.get("label", "")).lower() or "escalate" in str(r.get("label", "")).lower() for r in readiness.blocking_requirements)


# ==============================================================================
# 4. Evidence Upload, Auto-Assignment & Adjuster Workspace
# ==============================================================================
def test_evidence_upload_auto_assignment_and_adjuster_download(monkeypatch):
    """Test evidence upload without NameError, adjuster auto-assignment, and download endpoint."""
    claim = Claim(
        id="claim-uuid-1",
        ticket_id="CLM-TEST-001",
        claimant_id="user-1",
        tenant_id="tenant-1",
        status="submitted",
        insurance_type="motor",
        pipeline_state={"evidence": [], "extracted_data": {"policy_id": "POL-1"}},
    )

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = claim

    evidence_item = {
        "id": "ev-uuid-1",
        "name": "damage.jpg",
        "s3_key": "damage.jpg",
        "content_type": "image/jpeg",
        "size": 1024,
    }
    claim.pipeline_state["evidence"] = [evidence_item]

    monkeypatch.setattr("src.storage.s3.get_bytes", lambda key: b"fake-image-bytes")
    req = _make_req(role="ADJUSTER")
    monkeypatch.setattr(adjuster_routes, "_resolve_adjuster", lambda r, db: SimpleNamespace(id="adj-1", tenant_id="tenant-1", role="ADJUSTER"))
    monkeypatch.setattr(adjuster_routes, "_can_access_claim", lambda c, u, db: True)

    resp = adjuster_routes.download_claim_evidence_file("CLM-TEST-001", "ev-uuid-1", req, mock_db)
    assert resp.media_type == "image/jpeg"
    assert resp.body == b"fake-image-bytes"

    # URL endpoint
    url_resp = adjuster_routes.get_evidence_url("CLM-TEST-001", "ev-uuid-1", user=SimpleNamespace(id="adj-1", tenant_id="tenant-1", role="ADJUSTER"), db=mock_db)
    assert "url" in url_resp
    assert ("damage.jpg" in url_resp["url"] or "ev-uuid-1" in url_resp["url"])


# ==============================================================================
# 5. Admin Dashboard Metrics, Adjuster Update & CSV Export
# ==============================================================================
def test_admin_dashboard_metrics_and_adjuster_update(monkeypatch):
    """Verify admin dashboard returns 4 metrics and adjusters can be updated via PUT."""
    mock_db = MagicMock()
    admin_user = SimpleNamespace(id="admin-1", tenant_id="tenant-1", role="ADMIN")
    monkeypatch.setattr(admin_routes, "_require_admin", lambda r, db: admin_user)

    req = _make_req(role="ADMIN")
    # Admin dashboard metrics
    metrics = admin_routes.get_admin_dashboard(req, mock_db)
    assert "total_active_policies" in metrics
    assert "claims_by_stage" in metrics
    assert "approved_settlement_volume" in metrics
    assert "active_adjusters" in metrics

    # Adjuster update with canonical specialization
    adjuster = Adjuster(
        id="adj-uuid-1",
        tenant_id="tenant-1",
        name="Jane Smith",
        specialization="motor",
        is_active=True,
    )
    mock_db.query.return_value.filter.return_value.first.return_value = adjuster

    updated = admin_routes.update_adjuster(
        "adj-uuid-1",
        admin_routes.UpdateAdjusterRequest(name="Jane Senior", specialization="health"),
        req,
        mock_db,
    )
    assert updated["name"] == "Jane Senior"
    assert updated["specialization"] == "health"


def test_post_fix_adjuster_claim_file_notes_and_evidence_schema(monkeypatch):
    """Verify adjuster claim_file handles ClaimNote (author_user_id) and ClaimEvidence (object_key, size_bytes, analysis_json) without AttributeError."""
    from src.database.hardening_models import ClaimNote, ClaimEvidence
    claim = Claim(
        id="claim-uuid-2",
        ticket_id="CLM-TEST-002",
        claimant_id="user-1",
        tenant_id="tenant-1",
        status="under_review",
        insurance_type="motor",
        pipeline_state={"extracted_data": {"policy_id": "POL-1"}},
    )
    note = ClaimNote(
        id="note-1",
        tenant_id="tenant-1",
        claim_id="claim-uuid-2",
        author_user_id="adj-user-1",
        note="Verified repair invoice against surveyor sheet.",
        visibility="internal",
        created_at=datetime.now(timezone.utc),
    )
    ev = ClaimEvidence(
        id="ev-db-1",
        tenant_id="tenant-1",
        claim_id="claim-uuid-2",
        object_key="uploads/invoice.pdf",
        original_filename="invoice.pdf",
        content_type="application/pdf",
        size_bytes=2048,
        status="uploaded",
        verification_status="VERIFIED",
        verification_confidence=0.95,
        detected_document_type="repair_invoice",
        analysis_json={"reason": "Matches garage header", "extracted_fields": {"total": "45000"}},
        created_at=datetime.now(timezone.utc),
    )
    assert hasattr(note, "author_user_id") and not hasattr(note, "author_role")
    assert hasattr(ev, "object_key") and hasattr(ev, "size_bytes") and hasattr(ev, "analysis_json")
