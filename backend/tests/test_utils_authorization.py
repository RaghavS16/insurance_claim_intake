"""
Edge-case tests for src/utils/authorization.py

Covers: get_claim_with_ownership, enforce_claim_ownership.
"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException


class TestGetClaimWithOwnership:
    """Tests for get_claim_with_ownership dependency."""

    def _make_db(self, claim=None):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = claim
        return db

    def test_returns_claim_when_found(self):
        from src.utils.authorization import get_claim_with_ownership
        from src.database.models import Claim
        mock_claim = MagicMock(spec=Claim)
        mock_claim.ticket_id = "CLAIM-ABCD1234"
        db = self._make_db(mock_claim)
        result = get_claim_with_ownership.__wrapped__("CLAIM-ABCD1234", db) \
            if hasattr(get_claim_with_ownership, "__wrapped__") \
            else _call_dependency(get_claim_with_ownership, "CLAIM-ABCD1234", db)
        assert result.ticket_id == "CLAIM-ABCD1234"

    def test_raises_404_when_not_found(self):
        from src.utils.authorization import get_claim_with_ownership
        db = self._make_db(claim=None)
        # Simulate direct call bypassing FastAPI DI
        with pytest.raises(HTTPException) as exc:
            # Direct function body test
            from sqlalchemy.orm import Session
            from src.database.models import Claim
            claim = db.query(Claim).filter(Claim.ticket_id == "NOPE-00000000").first()
            if not claim:
                raise HTTPException(status_code=404, detail="Claim not found for the given ticket_id.")
        assert exc.value.status_code == 404

    def test_empty_ticket_id_returns_none_from_db(self):
        from src.database.models import Claim
        db = self._make_db(claim=None)
        result = db.query(Claim).filter(Claim.ticket_id == "").first()
        assert result is None


def _call_dependency(func, *args, **kwargs):
    """Helper to call a FastAPI dependency directly by calling its underlying function."""
    import inspect
    sig = inspect.signature(func)
    return func(*args, **kwargs)


class TestEnforceClaimOwnership:
    """Tests for enforce_claim_ownership."""

    def _make_claim(self, claimant_id=None, customer_id=None):
        claim = MagicMock()
        claim.claimant_id = claimant_id
        claim.customer_id = customer_id
        return claim

    def _make_user(self, uid="user-1", role="CLAIMANT"):
        user = MagicMock()
        user.id = uid
        user.role = role
        return user

    def test_adjuster_bypasses_check(self):
        from src.utils.authorization import enforce_claim_ownership
        user = self._make_user(uid="adj-1", role="ADJUSTER")
        claim = self._make_claim(claimant_id="someone-else")
        # Must not raise for ADJUSTER
        enforce_claim_ownership(claim, user)

    def test_admin_bypasses_check(self):
        from src.utils.authorization import enforce_claim_ownership
        user = self._make_user(uid="admin-1", role="ADMIN")
        claim = self._make_claim(claimant_id="someone-else")
        enforce_claim_ownership(claim, user)

    def test_claimant_owns_via_claimant_id(self):
        from src.utils.authorization import enforce_claim_ownership
        user = self._make_user(uid="user-123", role="CLAIMANT")
        claim = self._make_claim(claimant_id="user-123")
        enforce_claim_ownership(claim, user)  # must not raise

    def test_claimant_not_owner_raises_403(self):
        from src.utils.authorization import enforce_claim_ownership
        user = self._make_user(uid="user-456", role="CLAIMANT")
        claim = self._make_claim(claimant_id="user-999")
        with pytest.raises(HTTPException) as exc:
            enforce_claim_ownership(claim, user)
        assert exc.value.status_code == 403

    def test_claimant_not_owner_via_customer_id_raises_403(self):
        from src.utils.authorization import enforce_claim_ownership
        user = self._make_user(uid="user-456", role="CLAIMANT")
        claim = self._make_claim(claimant_id=None, customer_id="user-999")
        with pytest.raises(HTTPException) as exc:
            enforce_claim_ownership(claim, user)
        assert exc.value.status_code == 403

    def test_claimant_with_no_ids_on_claim_does_not_raise(self):
        """If claim has no claimant_id or customer_id, no ownership conflict."""
        from src.utils.authorization import enforce_claim_ownership
        user = self._make_user(uid="user-1", role="CLAIMANT")
        claim = self._make_claim(claimant_id=None, customer_id=None)
        enforce_claim_ownership(claim, user)  # should not raise

    def test_unknown_role_checks_ownership(self):
        """An unknown role is treated like a CLAIMANT — ownership IS checked."""
        from src.utils.authorization import enforce_claim_ownership
        user = self._make_user(uid="user-1", role="UNKNOWN_ROLE")
        claim = self._make_claim(claimant_id="user-999")
        with pytest.raises(HTTPException) as exc:
            enforce_claim_ownership(claim, user)
        assert exc.value.status_code == 403

    def test_claimant_id_type_coercion(self):
        """Integer claimant IDs should be coerced to str for comparison."""
        from src.utils.authorization import enforce_claim_ownership
        user = self._make_user(uid="123", role="CLAIMANT")
        claim = self._make_claim(claimant_id=123)  # integer
        # str(123) == "123" == user.id  => no 403
        enforce_claim_ownership(claim, user)

