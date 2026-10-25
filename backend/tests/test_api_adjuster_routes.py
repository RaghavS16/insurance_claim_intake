"""
Unit tests for adjuster route helpers and queue logic in src/api/adjuster_routes.py.
"""
from datetime import datetime, timezone
import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException

from src.database.models import Adjuster, Claim, User
from src.database.hardening_models import ClaimAssignment
from src.api.adjuster_routes import _can_access_claim, _ensure_assigned_adjuster, _get_adjuster_relevant_claims, _item, queue


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


    def test_cross_tenant_adjuster_cannot_access_claim(self):
        c = self._make_claim(assigned_adjuster_id="adj-1", tenant_id="tenant-A")
        u = self._make_user(uid="adj-1", tenant_id="tenant-B")
        assert _can_access_claim(c, u) is False

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


class TestAdjusterQueueIsolation:
    def _make_claim(self, cid, ticket_id, assigned_adjuster_id=None, tenant_id="tenant-1", status="submitted"):
        c = MagicMock(spec=Claim)
        c.id = cid
        c.ticket_id = ticket_id
        c.tenant_id = tenant_id
        c.status = status
        c.pipeline_state = {"assigned_adjuster_id": assigned_adjuster_id} if assigned_adjuster_id else {}
        c.updated_at = datetime.now(timezone.utc)
        return c

    def _make_user(self, uid, role="ADJUSTER", tenant_id="tenant-1"):
        u = MagicMock(spec=User)
        u.id = uid
        u.role = role
        u.tenant_id = tenant_id
        return u

    def test_adjuster_isolation_claim1_for_adj1_and_claim2_for_adj2(self):
        c1 = self._make_claim("cid-1", "CLAIM-001", assigned_adjuster_id="adj-uuid-1")
        c2 = self._make_claim("cid-2", "CLAIM-002", assigned_adjuster_id="adj-uuid-2")
        c3 = self._make_claim("cid-3", "CLAIM-003", assigned_adjuster_id=None)

        all_claims = [c1, c2, c3]

        # DB mock setup
        def mock_query(model):
            q = MagicMock()
            if model is Claim:
                q.filter.return_value.order_by.return_value.all.return_value = all_claims
            elif model is Adjuster:
                # Returns adjuster profile matching query
                def filter_adj(*args, **kwargs):
                    sub_q = MagicMock()
                    sub_q.all.return_value = [adj_profile] if adj_profile else []
                    return sub_q
                q.filter.side_effect = filter_adj
            elif model is ClaimAssignment.claim_id:
                # Return assignments based on query
                def filter_assign(*args, **kwargs):
                    sub_q = MagicMock()
                    sub_q.all.return_value = active_assignments
                    return sub_q
                q.filter.side_effect = filter_assign
            return q

        db = MagicMock()
        db.query.side_effect = mock_query

        # Test Adjuster 1
        adj1_user = self._make_user("user-adj-1")
        adj_profile = MagicMock(spec=Adjuster)
        adj_profile.id = "adj-uuid-1"
        adj_profile.user_id = "user-adj-1"
        active_assignments = [MagicMock(claim_id="cid-1")]

        relevant_adj1, assigned_ids_adj1 = _get_adjuster_relevant_claims(db, adj1_user, "tenant-1", scope="assigned")
        adj1_cids = [c.id for c in relevant_adj1]

        assert "cid-1" in adj1_cids, "Adjuster 1 must see Claim 1 assigned to them"
        assert "cid-2" not in adj1_cids, "Adjuster 1 must NOT see Claim 2 assigned to Adjuster 2"
        assert "cid-3" not in adj1_cids, "Adjuster 1 must NOT see unassigned Claim 3 in their assigned queue"
        assert len(relevant_adj1) == 1

        # Test Adjuster 2
        adj2_user = self._make_user("user-adj-2")
        adj_profile = MagicMock(spec=Adjuster)
        adj_profile.id = "adj-uuid-2"
        adj_profile.user_id = "user-adj-2"
        active_assignments = [MagicMock(claim_id="cid-2")]

        relevant_adj2, assigned_ids_adj2 = _get_adjuster_relevant_claims(db, adj2_user, "tenant-1", scope="assigned")
        adj2_cids = [c.id for c in relevant_adj2]

        assert "cid-2" in adj2_cids, "Adjuster 2 must see Claim 2 assigned to them"
        assert "cid-1" not in adj2_cids, "Adjuster 2 must NOT see Claim 1 assigned to Adjuster 1"
        assert "cid-3" not in adj2_cids, "Adjuster 2 must NOT see unassigned Claim 3 in their assigned queue"
        assert len(relevant_adj2) == 1

    def test_admin_sees_all_claims_in_tenant(self):
        c1 = self._make_claim("cid-1", "CLAIM-001", assigned_adjuster_id="adj-uuid-1")
        c2 = self._make_claim("cid-2", "CLAIM-002", assigned_adjuster_id="adj-uuid-2")
        c3 = self._make_claim("cid-3", "CLAIM-003", assigned_adjuster_id=None)

        all_claims = [c1, c2, c3]
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = all_claims

        admin_user = self._make_user("admin-1", role="ADMIN")
        relevant, assigned_ids = _get_adjuster_relevant_claims(db, admin_user, "tenant-1", scope="assigned")

        assert len(relevant) == 3
        assert {c.id for c in relevant} == {"cid-1", "cid-2", "cid-3"}

    def test_adjuster_can_query_unassigned_scope(self):
        c1 = self._make_claim("cid-1", "CLAIM-001", assigned_adjuster_id="adj-uuid-1")
        c2 = self._make_claim("cid-2", "CLAIM-002", assigned_adjuster_id="adj-uuid-2")
        c3 = self._make_claim("cid-3", "CLAIM-003", assigned_adjuster_id=None)

        all_claims = [c1, c2, c3]

        def mock_query(model):
            q = MagicMock()
            if model is Claim:
                q.filter.return_value.order_by.return_value.all.return_value = all_claims
            elif model is Adjuster:
                q.filter.return_value.all.return_value = [MagicMock(id="adj-uuid-1")]
            elif model is ClaimAssignment.claim_id:
                # Return other assignments
                q.filter.return_value.all.return_value = [MagicMock(claim_id="cid-2")]
            return q

        db = MagicMock()
        db.query.side_effect = mock_query

        adj1_user = self._make_user("user-adj-1")
        relevant_unassigned, _ = _get_adjuster_relevant_claims(db, adj1_user, "tenant-1", scope="unassigned")
        unassigned_cids = [c.id for c in relevant_unassigned]

        assert "cid-3" in unassigned_cids, "Unassigned scope must return unassigned Claim 3"
        assert "cid-1" not in unassigned_cids, "Unassigned scope must NOT return Claim 1 (assigned to adj 1)"
        assert "cid-2" not in unassigned_cids, "Unassigned scope must NOT return Claim 2 (assigned to adj 2)"

    def test_can_access_claim_blocks_cross_adjuster_access(self):
        c2 = self._make_claim("cid-2", "CLAIM-002", assigned_adjuster_id="adj-uuid-2")
        adj1_user = self._make_user("user-adj-1")

        db = MagicMock()
        mock_adj = MagicMock(spec=Adjuster)
        mock_adj.id = "adj-uuid-1"
        # First query returns adjuster 1 profile, ClaimAssignment returns None (not assigned to adj 1)
        db.query.return_value.filter.return_value.first.side_effect = [mock_adj, None, None]

        assert _can_access_claim(c2, adj1_user, db=db) is False, "Adjuster 1 must NOT have access to Claim 2"

