"""
Edge-case tests for src/database/claim_workflow.py

Covers: ALLOWED_TRANSITIONS map, transition_claim, assign_claim.
"""
import pytest
from unittest.mock import MagicMock, patch, call
from src.database.claim_workflow import ALLOWED_TRANSITIONS, transition_claim, assign_claim


# ---------------------------------------------------------------------------
# ALLOWED_TRANSITIONS map
# ---------------------------------------------------------------------------
class TestAllowedTransitions:
    def test_draft_can_move_to_pending_confirmation(self):
        assert "pending_confirmation" in ALLOWED_TRANSITIONS["draft"]

    def test_closed_has_no_transitions(self):
        assert ALLOWED_TRANSITIONS["closed"] == set()

    def test_all_states_present(self):
        expected_states = {
            "draft", "pending_confirmation", "pending_verification", "verified",
            "pending_evidence", "submitted", "pending_adjuster", "assigned",
            "under_review", "approved", "partially_approved", "rejected",
            "escalated", "closed", "verification_failed",
        }
        assert expected_states.issubset(set(ALLOWED_TRANSITIONS.keys()))


# ---------------------------------------------------------------------------
# transition_claim
# ---------------------------------------------------------------------------
class TestTransitionClaim:
    def _make_claim(self, status="draft"):
        claim = MagicMock()
        claim.id = "claim-1"
        claim.status = status
        return claim

    def _make_db(self):
        return MagicMock()

    def test_valid_transition_updates_status(self):
        claim = self._make_claim("draft")
        db = self._make_db()
        result = transition_claim(db, claim, "pending_confirmation")
        assert claim.status == "pending_confirmation"
        assert result is claim

    def test_same_status_is_noop(self):
        claim = self._make_claim("draft")
        db = self._make_db()
        result = transition_claim(db, claim, "draft")
        assert result is claim
        db.add.assert_not_called()  # no audit event for no-op

    def test_invalid_transition_raises_value_error(self):
        claim = self._make_claim("closed")
        db = self._make_db()
        with pytest.raises(ValueError, match="Invalid claim transition"):
            transition_claim(db, claim, "draft")

    def test_audit_event_added_on_transition(self):
        claim = self._make_claim("draft")
        db = self._make_db()
        transition_claim(db, claim, "pending_confirmation", actor_user_id="actor-1", reason="test")
        db.add.assert_called_once()
        added = db.add.call_args[0][0]
        assert added.event_type == "status_changed"

    def test_transition_verified_to_submitted(self):
        claim = self._make_claim("verified")
        db = self._make_db()
        transition_claim(db, claim, "submitted")
        assert claim.status == "submitted"

    def test_transition_under_review_to_approved(self):
        claim = self._make_claim("under_review")
        db = self._make_db()
        transition_claim(db, claim, "approved")
        assert claim.status == "approved"

    def test_transition_under_review_to_rejected(self):
        claim = self._make_claim("under_review")
        db = self._make_db()
        transition_claim(db, claim, "rejected")
        assert claim.status == "rejected"

    def test_none_actor_allowed(self):
        claim = self._make_claim("draft")
        db = self._make_db()
        transition_claim(db, claim, "pending_confirmation", actor_user_id=None)
        assert claim.status == "pending_confirmation"

    def test_escalation_from_any_active_state(self):
        """Most active states can escalate."""
        for state in ["draft", "verified", "submitted", "assigned", "under_review"]:
            claim = self._make_claim(state)
            db = self._make_db()
            transition_claim(db, claim, "escalated")
            assert claim.status == "escalated"

    def test_unknown_source_status_raises(self):
        """Status not in ALLOWED_TRANSITIONS should raise ValueError."""
        claim = self._make_claim("nonexistent_status")
        db = self._make_db()
        with pytest.raises(ValueError):
            transition_claim(db, claim, "draft")


# ---------------------------------------------------------------------------
# assign_claim
# ---------------------------------------------------------------------------
class TestAssignClaim:
    def _make_db(self, existing_assignment=None, adjusters=None):
        db = MagicMock()
        # Active assignment check
        db.execute.return_value.scalar_one_or_none.return_value = existing_assignment
        # Adjuster list query
        if adjusters is not None:
            db.execute.return_value.scalars.return_value = iter(adjusters)
        return db

    def _make_adjuster(self, adj_id, specialization="motor", is_active=True, claims_assigned=0):
        a = MagicMock()
        a.id = adj_id
        a.specialization = specialization
        a.is_active = is_active
        a.claims_assigned = claims_assigned
        a.name = f"Adjuster-{adj_id}"
        return a

    def _make_claim(self, insurance_type="motor"):
        claim = MagicMock()
        claim.id = "claim-1"
        claim.insurance_type = insurance_type
        return claim

    def test_already_assigned_raises(self):
        claim = self._make_claim()
        existing = MagicMock()  # active assignment exists
        db = MagicMock()

        # First execute call returns the active assignment
        scalar_mock = MagicMock()
        scalar_mock.scalar_one_or_none.return_value = existing
        db.execute.return_value = scalar_mock

        with pytest.raises(ValueError, match="already has an active assignment"):
            assign_claim(db, claim)

    def test_no_adjusters_raises(self):
        claim = self._make_claim()
        db = MagicMock()

        call_count = [0]
        def execute_side_effect(stmt):
            mock_exec = MagicMock()
            if call_count[0] == 0:
                mock_exec.scalar_one_or_none.return_value = None  # no active assignment
            else:
                mock_exec.scalars.return_value = iter([])  # no adjusters
            call_count[0] += 1
            return mock_exec

        db.execute.side_effect = execute_side_effect
        with pytest.raises(ValueError, match="No active adjuster"):
            assign_claim(db, claim)

    def test_specialization_match_preferred(self):
        """Adjuster with matching specialization should be chosen over others."""
        claim = self._make_claim(insurance_type="health")
        adj_motor = self._make_adjuster("adj-1", specialization="motor", claims_assigned=0)
        adj_health = self._make_adjuster("adj-2", specialization="health", claims_assigned=5)

        db = MagicMock()
        call_count = [0]
        def execute_side_effect(stmt):
            mock_exec = MagicMock()
            if call_count[0] == 0:
                mock_exec.scalar_one_or_none.return_value = None
            elif call_count[0] == 1:
                mock_exec.scalars.return_value = iter([adj_motor, adj_health])
            else:
                mock_exec.return_value = None
            call_count[0] += 1
            return mock_exec

        db.execute.side_effect = execute_side_effect
        chosen = assign_claim(db, claim)
        assert chosen.id == "adj-2"

    def test_falls_back_to_lowest_load_when_no_specialization_match(self):
        """When no matching specialization, pick the one with fewest claims."""
        claim = self._make_claim(insurance_type="cyber")
        adj_high = self._make_adjuster("adj-1", specialization="motor", claims_assigned=10)
        adj_low = self._make_adjuster("adj-2", specialization="health", claims_assigned=2)

        db = MagicMock()
        call_count = [0]
        def execute_side_effect(stmt):
            mock_exec = MagicMock()
            if call_count[0] == 0:
                mock_exec.scalar_one_or_none.return_value = None
            elif call_count[0] == 1:
                # Sorted by claims_assigned asc, so adj_low comes first
                mock_exec.scalars.return_value = iter([adj_low, adj_high])
            else:
                mock_exec.return_value = None
            call_count[0] += 1
            return mock_exec

        db.execute.side_effect = execute_side_effect
        chosen = assign_claim(db, claim)
        assert chosen.id == "adj-2"

    def test_assignment_record_created(self):
        """A ClaimAssignment and ClaimAuditEvent should be added to db."""
        claim = self._make_claim(insurance_type="motor")
        adj = self._make_adjuster("adj-1", specialization="motor")

        db = MagicMock()
        call_count = [0]
        def execute_side_effect(stmt):
            mock_exec = MagicMock()
            if call_count[0] == 0:
                mock_exec.scalar_one_or_none.return_value = None
            elif call_count[0] == 1:
                mock_exec.scalars.return_value = iter([adj])
            else:
                mock_exec.return_value = None
            call_count[0] += 1
            return mock_exec

        db.execute.side_effect = execute_side_effect
        assign_claim(db, claim)
        assert db.add.call_count >= 2  # ClaimAssignment + ClaimAuditEvent
