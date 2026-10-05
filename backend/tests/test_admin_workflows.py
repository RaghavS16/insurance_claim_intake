from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from src.api import admin_workflow_routes as admin
from src.api import auth_onboarding_routes as onboarding
from src.database.hardening_models import AdjusterInvitation


class FakeQuery:
    def __init__(self, first_value=None, all_value=None):
        self._first = first_value
        self._all = [] if all_value is None else all_value
    def filter(self, *args, **kwargs): return self
    def order_by(self, *args, **kwargs): return self
    def first(self): return self._first
    def all(self): return self._all
    def limit(self, *args, **kwargs): return self
    def count(self): return len(self._all)


class FakeDB:
    def __init__(self, query_values):
        self.query_values = list(query_values)
        self.added = []
    def query(self, model):
        return self.query_values.pop(0)
    def add(self, obj): self.added.append(obj)
    def execute(self, *args, **kwargs):
        class R:
            def scalar_one_or_none(self): return None
        return R()
    def flush(self): pass
    def commit(self): pass
    def rollback(self): pass
    def refresh(self, obj): 
        if getattr(obj, "id", None) is None:
            obj.id = "generated-id"


def admin_user():
    return SimpleNamespace(id="admin-1", tenant_id="tenant-1", role="ADMIN", status="active")


def test_invite_adjuster_creates_durable_invitation(monkeypatch):
    monkeypatch.setattr(admin, "_admin", lambda request, db: admin_user())
    monkeypatch.setattr(admin.settings, "PUBLIC_APP_URL", "http://localhost:3000")
    monkeypatch.setattr(admin, "get_password_hash", lambda _: "hashed")
    monkeypatch.setattr(admin, "validate_full_name", lambda x: x.strip())
    monkeypatch.setattr(admin, "validate_email", lambda x: x.strip().lower())
    monkeypatch.setattr(admin, "validate_phone", lambda x: "9876543210")
    monkeypatch.setattr(admin, "enqueue", lambda *a, **k: SimpleNamespace(id="email-event-1"))
    req = SimpleNamespace()
    db = FakeDB([FakeQuery(None), FakeQuery(None)])
    result = admin.invite_adjuster(
        admin.InviteAdjusterRequest(name="John Doe", email="John@Example.com", phone="9876543210", specialization="motor"),
        req,
        db,
    )
    assert result["status"] == "invited"
    assert result["invitation_url"].startswith("http://localhost:3000/onboarding/adjuster?token=")
    assert any(isinstance(x, AdjusterInvitation) for x in db.added)


def test_preview_invitation_rejects_unknown_token(monkeypatch):
    monkeypatch.setattr(onboarding, "_find_invite", lambda db, token: None)
    with pytest.raises(HTTPException) as exc:
        onboarding.preview_adjuster_invitation("invalid-token", MagicMock())
    assert exc.value.status_code == 404


def test_preview_invitation_rejects_expired_token(monkeypatch):
    monkeypatch.setattr(
        onboarding,
        "_find_invite",
        lambda db, token: SimpleNamespace(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)),
    )
    with pytest.raises(HTTPException) as exc:
        onboarding.preview_adjuster_invitation("expired-token", MagicMock())
    assert exc.value.status_code == 404


def test_strict_policy_rejects_invalid_policy_type(monkeypatch):
    monkeypatch.setattr(admin, "_admin", lambda request, db: admin_user())
    payload = admin.StrictPolicyRequest(
        policy_number="POL-1", policy_type="invalid", coverage_amount=1000, deductible=10,
        effective_date="2026-01-01", expiry_date="2027-01-01",
        policyholder_name="Policy Holder", policyholder_dob="1990-01-01",
        policyholder_phone="9876543210",
    )
    with pytest.raises(HTTPException) as exc:
        admin.create_strict_policy(payload, SimpleNamespace(), FakeDB([]))
    assert exc.value.status_code == 400


def test_policy_template_returns_download_response(monkeypatch):
    monkeypatch.setattr(admin, "_admin", lambda request, db: admin_user())
    response = admin.policy_template(SimpleNamespace(), "csv", MagicMock())
    assert response.media_type == "text/csv"
    assert "policy-import-template.csv" in str(response.headers.get("content-disposition"))


def test_reassign_requires_active_target(monkeypatch):
    monkeypatch.setattr(admin, "_admin", lambda request, db: admin_user())
    claim = SimpleNamespace(id="claim-1", tenant_id="tenant-1", ticket_id="CLAIM-1")
    db = FakeDB([FakeQuery(claim), FakeQuery(None)])
    with pytest.raises(HTTPException) as exc:
        admin.reassign_claim(
            "CLAIM-1",
            admin.ReassignClaimRequest(adjuster_id="adj-2", reason="Workload balancing"),
            SimpleNamespace(),
            db,
        )
    assert exc.value.status_code == 404
