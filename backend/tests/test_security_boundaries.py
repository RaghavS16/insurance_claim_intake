from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException

from src.api import claim_routes
from src.utils.authorization import enforce_claim_ownership


def test_cross_tenant_claim_is_denied():
    claim = SimpleNamespace(id="c1", tenant_id="tenant-a", claimant_id="u1", customer_id="u1")
    user = SimpleNamespace(id="u1", tenant_id="tenant-b", role="CLAIMANT")
    with pytest.raises(HTTPException) as exc:
        enforce_claim_ownership(claim, user)
    assert exc.value.status_code == 403


def test_same_tenant_claim_owner_is_allowed():
    claim = SimpleNamespace(id="c1", tenant_id="tenant-a", claimant_id="u1", customer_id="u1")
    user = SimpleNamespace(id="u1", tenant_id="tenant-a", role="CLAIMANT")
    enforce_claim_ownership(claim, user)


def test_active_claim_query_is_tenant_scoped(monkeypatch):
    user = SimpleNamespace(id="user-a", tenant_id="tenant-a", role="CLAIMANT")
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.first.return_value = None
    db = MagicMock()
    db.query.return_value = query
    monkeypatch.setattr(claim_routes, "_resolve_user", lambda request, db: user)

    claim_routes.get_active_claim(SimpleNamespace(), db)

    first_filter = query.filter.call_args_list[0].args
    rendered = " ".join(str(item) for item in first_filter)
    assert "claims.tenant_id" in rendered
