"""
Unit tests for adjuster route helpers and queue logic in src/api/adjuster_routes.py.
"""
from datetime import datetime, timezone
import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException

from src.database.models import Adjuster, Claim, User
from src.database.hardening_models import ClaimAssignment
from src.api.adjuster_routes import _can_access_claim, _ensure_assigned_adjuster, _item, queue


class TestCanAccessClaim:
    def _make_claim(self, assigned_adjuster_id=None, tenant_id="tenant-1"):
        c = MagicMock(spec=Claim)
        c.id = "claim-uuid-1"
        c.tenant_id = tenant_id
        c.pipeline_state = {"assigned_adjuster_id": assigned_adjuster_id} if assigned_adjuster_id else {}
        return c

    def _make_user(self, uid="adj-1", email="adj@example.com", role="ADJUSTER", tenant_id="tenant-1"):
        u = MagicMock(spec=User)
        u.id = uid
        u.email = email
        u.role = role
        u.tenant_id = tenant_id
        return u

    def test_admin_always_can_access(self):
        c = self._make_claim()
        u = self._make_user(role="ADMIN")
        assert _can_access_claim(c, u) is True

    def test_adjuster_with_assigned_id_in_pipeline_state(self):
        c = self._make_claim(assigned_adjuster_id="adj-1")
        u = self._make_user(uid="adj-1")
        assert _can_access_claim(c, u) is True

    def test_adjuster_with_matching_email_in_db(self):
        c = self._make_claim(assigned_adjuster_id="adj-db-99")
        u = self._make_user(uid="user-1", email="matched@example.com")
        db = MagicMock()
        mock_adj = MagicMock(spec=Adjuster)
        mock_adj.id = "adj-db-99"
        db.query.return_value.filter.return_value.first.return_value = mock_adj
        assert _can_access_claim(c, u, db=db) is True

    def test_adjuster_with_claim_assignment_record(self):
        c = self._make_claim(assigned_adjuster_id="different-adj")
        u = self._make_user(uid="user-1", email="assigned@example.com")
        db = MagicMock()
        mock_adj = MagicMock(spec=Adjuster)
        mock_adj.id = "adj-assigned-1"
        # First query for Adjuster by email
        # Second query for ClaimAssignment
        assignment = MagicMock(spec=ClaimAssignment)
        db.query.return_value.filter.return_value.first.side_effect = [mock_adj, assignment]
        assert _can_access_claim(c, u, db=db) is True

    def test_unrelated_adjuster_cannot_access(self):
        c = self._make_claim(assigned_adjuster_id="adj-999")
        u = self._make_user(uid="adj-1", email="unrelated@example.com")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        assert _can_access_claim(c, u, db=db) is False


class TestEnsureAssignedAdjuster:
    def _make_claim(self, assigned_adjuster_id=None):
        c = MagicMock(spec=Claim)
        c.id = "claim-uuid-1"
        c.pipeline_state = {"assigned_adjuster_id": assigned_adjuster_id} if assigned_adjuster_id else {}
        return c

    def _make_user(self, uid="adj-1", email="adj@example.com", role="ADJUSTER"):
        u = MagicMock(spec=User)
        u.id = uid
        u.email = email
        u.role = role
        return u

    def test_admin_finds_assigned_adjuster(self):
        c = self._make_claim(assigned_adjuster_id="adj-10")
        u = self._make_user(role="ADMIN")
        db = MagicMock()
        adj = MagicMock(spec=Adjuster)
        adj.id = "adj-10"
        db.query.return_value.filter.return_value.first.return_value = adj
        result = _ensure_assigned_adjuster(c, u, db)
        assert result.id == "adj-10"

    def test_admin_falls_back_to_first_adjuster_when_unassigned(self):
        c = self._make_claim(assigned_adjuster_id=None)
        u = self._make_user(role="ADMIN")
        db = MagicMock()
        adj = MagicMock(spec=Adjuster)
        adj.id = "adj-fallback"
        db.query.return_value.first.return_value = adj
        db.query.return_value.filter.return_value.first.return_value = adj
        result = _ensure_assigned_adjuster(c, u, db)
        assert result.id == "adj-fallback"

    def test_adjuster_matched_by_email_and_assigned_id(self):
        c = self._make_claim(assigned_adjuster_id="adj-20")
        u = self._make_user(uid="user-20", email="adj20@example.com")
        db = MagicMock()
        adj = MagicMock(spec=Adjuster)
        adj.id = "adj-20"
        db.query.return_value.filter.return_value.first.return_value = adj
        result = _ensure_assigned_adjuster(c, u, db)
        assert result.id == "adj-20"

    def test_adjuster_matched_by_active_assignment(self):
        c = self._make_claim(assigned_adjuster_id="different-adj")
        u = self._make_user(uid="user-30", email="adj30@example.com")
        db = MagicMock()
        adj = MagicMock(spec=Adjuster)
        adj.id = "adj-30"
        assignment = MagicMock(spec=ClaimAssignment)
        db.query.return_value.filter.return_value.first.side_effect = [adj, assignment]
        result = _ensure_assigned_adjuster(c, u, db)
        assert result.id == "adj-30"

    def test_unassigned_raises_403(self):
        c = self._make_claim(assigned_adjuster_id="other-adj")
        u = self._make_user(uid="user-99", email="stranger@example.com")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(HTTPException) as exc:
            _ensure_assigned_adjuster(c, u, db)
        assert exc.value.status_code == 403


class TestItemSerialization:
    def test_item_formats_claim_metadata(self):
        c = MagicMock(spec=Claim)
        c.ticket_id = "CLAIM-12345678"
        c.status = "under_review"
        c.insurance_type = "motor"
        c.event_date = datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc).date()
        c.event_location = "Chennai"
        c.estimated_claim_amount = 25000.0
        c.updated_at = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
        c.pipeline_state = {
            "priority": "high",
            "assigned_adjuster_id": "adj-1",
            "confirmed": True,
            "policy_verification": {"valid": True},
            "dynamic_missing": [],
        }

        item = _item(c)
        assert item["ticket_id"] == "CLAIM-12345678"
        assert item["status"] == "under_review"
        assert item["priority"] == "high"
        assert item["claimant_confirmed"] is True
        assert item["policy_verified"] is True
        assert item["dynamic_requirements_complete"] is True
        assert item["estimated_claim_amount"] == 25000.0
