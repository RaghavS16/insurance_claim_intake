from datetime import date, datetime, timezone
from types import SimpleNamespace
import pytest
from fastapi import HTTPException

from src.api import policy_routes
from src.database.models import Policy


class FakeQuery:
    def __init__(self, items=None):
        self._items = list(items or [])

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def offset(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def count(self):
        return len(self._items)

    def all(self):
        return self._items


class FakeDB:
    def __init__(self, query_items):
        self.query_items = list(query_items)

    def query(self, model):
        return FakeQuery(self.query_items)


def test_adjuster_can_view_policies_directory(monkeypatch):
    adjuster_user = SimpleNamespace(id="adj-1", tenant_id="tenant-1", role="ADJUSTER", status="active")
    monkeypatch.setattr(policy_routes, "resolve_bearer_user", lambda req, db, roles: adjuster_user)

    mock_policy = SimpleNamespace(
        id="pol-uuid-1",
        tenant_id="tenant-1",
        policy_number="POL-MOT-2026-904",
        policy_type="motor",
        coverage_amount=1000000.0,
        deductible=5000.0,
        effective_date=date(2026, 1, 1),
        expiry_date=date(2027, 1, 1),
        is_active=True,
        policyholder_name="Alice Smith",
        policyholder_dob=date(1985, 4, 12),
        policyholder_phone="+15551234567",
        policyholder_email="alice@example.com",
        customer_id="cust-1",
        linked_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    db = FakeDB([mock_policy])
    res = policy_routes.list_policies_directory(request=SimpleNamespace(), db=db)

    assert res["total"] == 1
    item = res["items"][0]
    assert item["policy_number"] == "POL-MOT-2026-904"
    assert item["policyholder_name"] == "Alice Smith"
    assert item["policyholder_phone"] == "+15551234567"
    assert item["policyholder_dob"] == "1985-04-12"
    assert item["policyholder_email"] == "alice@example.com"
    assert item["coverage_amount"] == 1000000.0
    assert item["is_active"] is True
    assert item["linked"] is True


def test_claimant_forbidden_from_directory(monkeypatch):
    def fake_resolve(req, db, roles):
        if "CLAIMANT" not in roles:
            raise HTTPException(status_code=403, detail="Forbidden")
        return SimpleNamespace(id="claimant-1", role="CLAIMANT")

    monkeypatch.setattr(policy_routes, "resolve_bearer_user", fake_resolve)

    with pytest.raises(HTTPException) as exc_info:
        policy_routes.list_policies_directory(request=SimpleNamespace(), db=FakeDB([]))
    assert exc_info.value.status_code == 403
