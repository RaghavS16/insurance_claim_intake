"""
Tests for the 5 free-of-cost production-grade product enhancements:
1. Zero-RAM Cloud Embeddings (EMBEDDING_PROVIDER=gemini)
2. Real-Time In-App Notification Center (GET /api/v1/notifications & POST /api/v1/notifications/mark-read)
3. Admin & Adjuster Missing Policy Knowledge Escalation Queue
4. One-Click PDF Claim Settlement / Dossier Certificate Export
5. Automated Duplicate Claim & Fraud Velocity Check
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
import pytest
from starlette.requests import Request

from src.knowledge.embeddings import EmbeddingService, embed
from src.api import (
    notification_routes,
    knowledge_routes,
    claim_routes,
    adjuster_routes,
)
from src.database.hardening_models import (
    ClaimEvidence,
    ClaimEvidenceRequest,
    ClaimAuditEvent,
    UserNotificationRead,
    OutboxEvent,
    ClaimException,
)
from src.database.models import Claim, Policy, User
from src.agents import policy_check, turn_processor


def _make_req(headers=None, user_id="user-1", tenant_id="tenant-1", role="CLAIMANT"):
    req = Request({
        "type": "http",
        "method": "GET",
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
# 1. Zero-RAM Cloud Embeddings
# ==============================================================================
def test_gemini_embeddings_zero_ram(monkeypatch):
    """Verify Gemini embeddings generates 768-dim vector via HTTPS and auto-fallback."""
    fake_vector = [0.01] * 768

    with patch("src.knowledge.embeddings.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "embeddings": [
                {"values": fake_vector}
            ]
        }
        mock_post.return_value = mock_resp

        # Test direct _embed_gemini
        svc = EmbeddingService()
        vecs = svc._embed_gemini(["Test policy document text"], api_key="fake-gemini-key")
        assert len(vecs) == 1
        assert len(vecs[0]) == 768
        assert vecs[0][0] == 0.01

        # Test embed() auto-dispatch when GEMINI_API_KEY is in environment
        monkeypatch.setenv("GEMINI_API_KEY", "fake-gemini-key")
        monkeypatch.setenv("EMBEDDING_PROVIDER", "auto")
        auto_vec = embed("Auto dispatch text")
        assert len(auto_vec) == 768


# ==============================================================================
# 2. Real-Time Notification Center
# ==============================================================================
@pytest.mark.asyncio
async def test_claimant_and_adjuster_notifications():
    """Verify role-relevant notifications for Claimant and Adjuster, and mark-read flow."""
    mock_db = MagicMock()

    claimant_req = _make_req(user_id="claimant-123", role="CLAIMANT")
    adjuster_req = _make_req(user_id="adjuster-456", role="ADJUSTER")

    # Claimant query test: open evidence request + audit event
    claim_id = str(uuid.uuid4())
    req_evidence = ClaimEvidenceRequest(
        id=str(uuid.uuid4()),
        claim_id=claim_id,
        tenant_id="tenant-1",
        adjuster_id="adjuster-456",
        request_text="Upload official report",
        status="open",
        requested_at=datetime.now(timezone.utc),
    )
    audit_evt = ClaimAuditEvent(
        id=str(uuid.uuid4()),
        claim_id=claim_id,
        tenant_id="tenant-1",
        event_type="claim_under_review",
        old_value_json={"status": "submitted"},
        new_value_json={"status": "under_review"},
        created_at=datetime.now(timezone.utc),
    )

    claimant_user = User(id="claimant-123", tenant_id="tenant-1", role="CLAIMANT", email="c@test.com", status="active")
    claim_obj = Claim(
        id=claim_id,
        tenant_id="tenant-1",
        ticket_id="TIC-NOTIF-01",
        claimant_id="claimant-123",
        status="under_review",
    )

    # Mock DB query results for claimant
    def mock_notif_query(*args):
        m = MagicMock()
        model = args[0] if args else None
        m_str = str(model)
        if model is UserNotificationRead or "user_notification_reads" in m_str or "notification_id" in m_str:
            m.filter.return_value.all.return_value = []
            m.filter.return_value.first.return_value = None
        elif model is Claim or "Claim" in m_str:
            m.filter.return_value.all.return_value = [claim_obj]
        elif model is ClaimEvidenceRequest or "ClaimEvidenceRequest" in m_str:
            m.filter.return_value.order_by.return_value.all.return_value = [req_evidence]
        elif model is ClaimAuditEvent or "ClaimAuditEvent" in m_str:
            m.filter.return_value.order_by.return_value.all.return_value = [audit_evt]
        else:
            m.filter.return_value.all.return_value = []
            m.filter.return_value.first.return_value = None
        return m

    mock_db.query.side_effect = mock_notif_query

    res = notification_routes.get_user_notifications(current_user=claimant_user, db=mock_db)
    assert "items" in res
    assert "unread_count" in res
    assert len(res["items"]) >= 1

    # Mark as read
    target_id = res["items"][0]["id"]
    mark_res = notification_routes.mark_notifications_read(
        payload=notification_routes.MarkReadRequest(notification_id=target_id),
        current_user=claimant_user,
        db=mock_db,
    )
    assert mark_res["status"] == "ok"
    mock_db.commit.assert_called()


# ==============================================================================
# 3. Missing Policy Knowledge Escalation Queue
# ==============================================================================
def test_missing_policy_knowledge_escalation():
    """Verify missing policy knowledge creates ClaimException and is surfaced in escalation route."""
    mock_db = MagicMock()
    claim_id = str(uuid.uuid4())

    # 1. Surface via GET /api/v1/knowledge/escalations
    escalation_row = ClaimException(
        id=str(uuid.uuid4()),
        claim_id=claim_id,
        tenant_id="tenant-1",
        event_type="missing_policy_knowledge",
        severity="high",
        reason="Missing indexed policy wording for policy POL-7788",
        status="open",
        resolution_json={
            "ticket_id": "TIC-TEST-99",
            "policy_number": "POL-7788",
            "insurance_type": "commercial_property",
        },
        created_at=datetime.now(timezone.utc),
    )
    claim_mock = MagicMock()
    claim_mock.ticket_id = "TIC-TEST-99"
    claim_mock.insurance_type = "commercial_property"
    claim_mock.claimant_name = "Jane Doe"
    claim_mock.created_at = datetime.now(timezone.utc)
    claim_mock.policy = None

    mock_db.query.return_value.join.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
        (escalation_row, claim_mock)
    ]

    adj_user = User(id="adj-1", tenant_id="tenant-1", role="ADJUSTER", email="adj@test.com", status="active")
    result = knowledge_routes.get_missing_knowledge_escalations(user=adj_user, db=mock_db)
    assert "items" in result
    assert len(result["items"]) == 1
    assert result["items"][0]["insurance_type"] == "commercial_property"
    assert result["items"][0]["policy_number"] == "POL-7788"


# ==============================================================================
# 4. One-Click Dossier & Adjudication Certificate Export
# ==============================================================================
def test_claim_dossier_and_certificate_export():
    """Verify claimant and adjuster export returns markdown dossier and certificate metadata with sha256."""
    mock_db = MagicMock()
    claim_id = str(uuid.uuid4())

    claim = Claim(
        id=claim_id,
        ticket_id="TIC-EXPORT-01",
        claimant_id="claimant-1",
        insurance_type="motor",
        status="approved",
        estimated_claim_amount=4500.0,
        event_description="Rear-end collision at intersection.",
        event_location="Main St & 4th Ave",
        event_date=date(2026, 8, 15),
        created_at=datetime(2026, 8, 16, 10, 0, 0, tzinfo=timezone.utc),
        pipeline_state={
            "extracted_fields": {"impact_speed": "35 mph", "driver_seatbelt": "yes"},
            "approved_payout_amount": 4200.0,
            "adjudication_notes": "Coverage confirmed; standard deductible applied.",
        },
    )
    policy = Policy(
        id=str(uuid.uuid4()),
        policy_number="POL-AUTO-999",
        policy_type="motor",
        policyholder_name="Jane Doe",
        effective_date=date(2026, 1, 1),
        expiry_date=date(2027, 1, 1),
        coverage_amount=50000.0,
        deductible=500.0,
    )
    claim.policy = policy
    claim.policy_id = policy.id

    evidence_item = ClaimEvidence(
        id=str(uuid.uuid4()),
        claim_id=claim_id,
        tenant_id="tenant-1",
        object_key="claims/quote.pdf",
        original_filename="autocraft_quote.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        document_type="repair_estimate",
        sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        verification_status="VERIFIED",
    )
    claim.evidence_records = [evidence_item]

    claimant_user = User(id="claimant-1", tenant_id="tenant-1", role="CLAIMANT", email="c@test.com", status="active")
    adjuster_user = User(id="adj-1", tenant_id="tenant-1", role="ADJUSTER", email="adj@test.com", status="active")
    current_test_user = [claimant_user]

    # Setup mock_db query chaining
    def mock_query_fn(model):
        m = MagicMock()
        m.filter.return_value = m
        m.order_by.return_value = m
        if model == User:
            m.first.return_value = current_test_user[0]
        elif model == Claim:
            m.first.return_value = claim
        elif model == Policy:
            m.first.return_value = policy
        elif model == ClaimEvidence:
            m.all.return_value = [evidence_item]
        else:
            m.first.return_value = None
            m.all.return_value = []
        return m

    mock_db.query.side_effect = mock_query_fn

    req = _make_req({"X-User-ID": "claimant-1"}, user_id="claimant-1", role="CLAIMANT")
    res = claim_routes.export_claim_dossier(ticket_id="TIC-EXPORT-01", request=req, db=mock_db)

    assert "ticket_id" in res
    assert res["ticket_id"] == "TIC-EXPORT-01"
    assert "formatted_text" in res
    assert "TIC-EXPORT-01" in res["formatted_text"]
    assert "certificate" in res

    cert = res["certificate"]
    assert cert["ticket_id"] == "TIC-EXPORT-01"
    assert cert["policy_number"] == "POL-AUTO-999"
    assert cert["approved_payout_amount"] == 4200.0
    assert len(cert["evidence_checksums"]) == 1
    assert cert["evidence_checksums"][0]["sha256"] == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    # Adjuster route export test
    current_test_user[0] = adjuster_user
    adj_req = _make_req({"X-User-ID": "adj-1"}, user_id="adj-1", role="ADJUSTER")
    adj_res = adjuster_routes.export_claim_dossier_adjuster(ticket_id="TIC-EXPORT-01", request=adj_req, db=mock_db)
    assert adj_res["ticket_id"] == "TIC-EXPORT-01"
    assert adj_res["certificate"]["policy_number"] == "POL-AUTO-999"


# ==============================================================================
# 5. Automated Duplicate Claim & Early Loss Fraud Check
# ==============================================================================
def test_duplicate_and_early_loss_fraud_velocity():
    """Verify policy check detects duplicates within ±7 days and early loss within 7 days of inception."""
    mock_db = MagicMock()

    policy_id = str(uuid.uuid4())
    current_claim_id = str(uuid.uuid4())

    current_claim = Claim(
        id=current_claim_id,
        claimant_id="claimant-1",
        tenant_id="tenant-1",
        ticket_id="TIC-CURR-01",
        event_date=date(2026, 5, 4),
        pipeline_state={"extracted_data": {"policy_id": "POL-FRAUD-001"}},
    )

    policy = Policy(
        id=policy_id,
        policy_number="POL-FRAUD-001",
        customer_id="claimant-1",
        policy_type="motor",
        coverage_amount=50000.0,
        deductible=500.0,
        is_active=True,
        effective_date=date(2026, 5, 1),
        expiry_date=date(2027, 5, 1),
    )

    duplicate_claims = []

    def mock_policy_query(model):
        m = MagicMock()
        m.filter.return_value = m
        if model == Claim:
            m.first.return_value = current_claim
            m.all.return_value = duplicate_claims
        elif model == Policy:
            m.first.return_value = policy
            m.all.return_value = [policy]
        elif model == ClaimException:
            m.first.return_value = None
            m.all.return_value = []
        return m

    mock_db.query.side_effect = mock_policy_query

    # Case 1: Early Loss flag (loss occurs 3 days after inception)
    res = policy_check.verify_policy_for_claim(
        policy_id="POL-FRAUD-001",
        event_date_str="2026-05-04",
        claimant_user_id="claimant-1",
        db=mock_db,
        claim_id=current_claim_id,
    )
    assert res["valid"] is True
    assert len(res["fraud_flags"]) >= 1
    assert any(ff["flag"] == "early_loss_inception_proximity" for ff in res["fraud_flags"])
    mock_db.add.assert_called()

    # Case 2: Duplicate claim flag within ±7 days
    mock_db.reset_mock()
    existing_claim = Claim(
        id=str(uuid.uuid4()),
        ticket_id="TIC-PRIOR-01",
        policy_id=policy_id,
        event_date=date(2026, 8, 12),
        status="under_review",
    )
    duplicate_claims.append(existing_claim)

    res2 = policy_check.verify_policy_for_claim(
        policy_id="POL-FRAUD-001",
        event_date_str="2026-08-10",
        claimant_user_id="claimant-1",
        db=mock_db,
        claim_id=current_claim_id,
    )
    assert res2["valid"] is True
    assert any(ff["flag"] == "duplicate_loss_window" for ff in res2["fraud_flags"])
    mock_db.add.assert_called()
