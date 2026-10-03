"""
Edge-case tests for src/utils/authorization.py

Covers: enforce_claim_ownership.
"""
import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException


class TestEnforceClaimOwnership:
    """Tests for enforce_claim_ownership."""

    def _make_claim(self, claimant_id=None, customer_id=None, tenant_id="tenant-1"):
        claim = MagicMock()
        claim.claimant_id = claimant_id
        claim.customer_id = customer_id
        claim.tenant_id = tenant_id
        return claim

    def _make_user(self, uid="user-1", role="CLAIMANT", tenant_id="tenant-1"):
        user = MagicMock()
        user.id = uid
        user.role = role
        user.tenant_id = tenant_id
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

