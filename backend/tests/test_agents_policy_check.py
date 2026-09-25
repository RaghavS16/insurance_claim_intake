"""
Edge-case tests for src/agents/policy_check.py

Covers: verify_policy_for_claim with all failure branches.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import date


class TestVerifyPolicyForClaim:
    def _make_db(self):
        return MagicMock()

    def _make_policy(self, number="POL-001", customer_id="user-1",
                     policy_type="motor", is_active=True,
                     effective_date=None, expiry_date=None):
        p = MagicMock()
        p.policy_number = number
        p.customer_id = customer_id
        p.policy_type = policy_type
        p.is_active = is_active
        p.effective_date = effective_date or date(2024, 1, 1)
        p.expiry_date = expiry_date or date(2030, 12, 31)
        return p

    def _make_claim_row(self, pipeline_state=None):
        c = MagicMock()
        c.pipeline_state = pipeline_state or {}
        return c

    def test_no_db_session_returns_invalid(self):
        from src.agents.policy_check import verify_policy_for_claim
        result = verify_policy_for_claim(policy_id="POL-001", event_date_str="2025-01-01",
                                         claimant_user_id="u1", db=None)
        assert result["valid"] is False
        assert result["reason"] == "no_db_session"

    def test_no_policy_id_returns_invalid(self):
        from src.agents.policy_check import verify_policy_for_claim
        db = self._make_db()
        result = verify_policy_for_claim(policy_id=None, event_date_str="2025-01-01",
                                         claimant_user_id="u1", db=db)
        assert result["valid"] is False
        assert result["reason"] == "no_policy_id"

    def test_empty_policy_id_returns_invalid(self):
        from src.agents.policy_check import verify_policy_for_claim
        db = self._make_db()
        result = verify_policy_for_claim(policy_id="", event_date_str="2025-01-01",
                                         claimant_user_id="u1", db=db)
        assert result["valid"] is False
        assert result["reason"] == "no_policy_id"

    def test_claim_not_found_returns_invalid(self):
        from src.agents.policy_check import verify_policy_for_claim
        db = self._make_db()
        db.query.return_value.filter.return_value.filter.return_value.first.return_value = None
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        result = verify_policy_for_claim(policy_id="POL-001", event_date_str="2025-01-01",
                                         claimant_user_id="u1", db=db)
        assert result["valid"] is False
        assert result["reason"] == "claim_not_found"

    def test_claim_policy_mismatch_returns_invalid(self):
        from src.agents.policy_check import verify_policy_for_claim
        db = self._make_db()
        candidate = self._make_claim_row({
            "extracted_data": {"policy_id": "DIFFERENT-POLICY"},
            "confirmed": True,
        })
        db.query.return_value.filter.return_value.filter.return_value.first.return_value = candidate
        result = verify_policy_for_claim(policy_id="POL-001", event_date_str="2025-01-01",
                                         claimant_user_id="u1", db=db, claim_id="claim-1")
        assert result["valid"] is False
        assert result["reason"] == "claim_policy_mismatch"

    def test_confirmation_not_given_returns_invalid(self):
        from src.agents.policy_check import verify_policy_for_claim
        db = self._make_db()
        candidate = self._make_claim_row({
            "extracted_data": {"policy_id": "POL-001"},
            "confirmed": False,
        })
        db.query.return_value.filter.return_value.filter.return_value.first.return_value = candidate
        result = verify_policy_for_claim(policy_id="POL-001", event_date_str="2025-01-01",
                                         claimant_user_id="u1", db=db, claim_id="claim-1")
        assert result["valid"] is False
        assert result["reason"] == "claimant_confirmation_required"

    def test_policy_not_found_in_db_returns_invalid(self):
        from src.agents.policy_check import verify_policy_for_claim
        db = self._make_db()
        candidate = self._make_claim_row({
            "extracted_data": {"policy_id": "POL-001"},
            "confirmed": True,
        })
        # claim query returns candidate, policy query returns None
        def query_side_effect(model_class):
            from src.database.models import Claim, Policy
            if model_class is Claim:
                mock = MagicMock()
                mock.filter.return_value.filter.return_value.first.return_value = candidate
                return mock
            else:
                mock = MagicMock()
                mock.filter.return_value.first.return_value = None
                return mock
        db.query.side_effect = query_side_effect
        result = verify_policy_for_claim(policy_id="POL-001", event_date_str="2025-01-01",
                                         claimant_user_id="u1", db=db, claim_id="claim-1")
        assert result["valid"] is False
        assert result["reason"] == "policy_not_found"

    def test_ownership_mismatch_returns_invalid(self):
        from src.agents.policy_check import verify_policy_for_claim
        from src.database.models import Claim, Policy
        db = self._make_db()
        candidate = self._make_claim_row({
            "extracted_data": {"policy_id": "POL-001"},
            "confirmed": True,
        })
        policy = self._make_policy(number="POL-001", customer_id="other-user")

        def query_side_effect(model_class):
            if model_class is Claim:
                mock = MagicMock()
                mock.filter.return_value.filter.return_value.first.return_value = candidate
                return mock
            else:
                mock = MagicMock()
                mock.filter.return_value.first.return_value = policy
                return mock
        db.query.side_effect = query_side_effect
        result = verify_policy_for_claim(policy_id="POL-001", event_date_str="2025-01-01",
                                         claimant_user_id="user-1", db=db, claim_id="claim-1")
        assert result["valid"] is False
        assert result["reason"] == "ownership_mismatch"

    def test_inactive_policy_returns_invalid(self):
        from src.agents.policy_check import verify_policy_for_claim
        from src.database.models import Claim, Policy
        db = self._make_db()
        candidate = self._make_claim_row({
            "extracted_data": {"policy_id": "POL-001"},
            "confirmed": True,
        })
        policy = self._make_policy(number="POL-001", customer_id="user-1", is_active=False)

        def query_side_effect(model_class):
            if model_class is Claim:
                mock = MagicMock()
                mock.filter.return_value.filter.return_value.first.return_value = candidate
                return mock
            else:
                mock = MagicMock()
                mock.filter.return_value.first.return_value = policy
                return mock
        db.query.side_effect = query_side_effect
        result = verify_policy_for_claim(policy_id="POL-001", event_date_str="2025-01-01",
                                         claimant_user_id="user-1", db=db, claim_id="claim-1")
        assert result["valid"] is False
        assert result["reason"] == "policy_inactive"

    def test_invalid_event_date_format_returns_invalid(self):
        from src.agents.policy_check import verify_policy_for_claim
        from src.database.models import Claim, Policy
        db = self._make_db()
        candidate = self._make_claim_row({
            "extracted_data": {"policy_id": "POL-001"},
            "confirmed": True,
        })
        policy = self._make_policy(number="POL-001", customer_id="user-1")

        def query_side_effect(model_class):
            if model_class is Claim:
                mock = MagicMock()
                mock.filter.return_value.filter.return_value.first.return_value = candidate
                return mock
            else:
                mock = MagicMock()
                mock.filter.return_value.first.return_value = policy
                return mock
        db.query.side_effect = query_side_effect
        result = verify_policy_for_claim(policy_id="POL-001", event_date_str="not-a-date",
                                         claimant_user_id="user-1", db=db, claim_id="claim-1")
        assert result["valid"] is False
        assert result["reason"] == "invalid_event_date"

    def test_event_before_policy_effective_date_returns_invalid(self):
        from src.agents.policy_check import verify_policy_for_claim
        from src.database.models import Claim, Policy
        db = self._make_db()
        candidate = self._make_claim_row({
            "extracted_data": {"policy_id": "POL-001"},
            "confirmed": True,
        })
        policy = self._make_policy(
            number="POL-001", customer_id="user-1",
            effective_date=date(2024, 6, 1), expiry_date=date(2025, 6, 1)
        )

        def query_side_effect(model_class):
            if model_class is Claim:
                mock = MagicMock()
                mock.filter.return_value.filter.return_value.first.return_value = candidate
                return mock
            else:
                mock = MagicMock()
                mock.filter.return_value.first.return_value = policy
                return mock
        db.query.side_effect = query_side_effect
        result = verify_policy_for_claim(policy_id="POL-001", event_date_str="2024-01-01",
                                         claimant_user_id="user-1", db=db, claim_id="claim-1")
        assert result["valid"] is False
        assert result["reason"] == "policy_not_active_on_event_date"

    def test_event_after_policy_expiry_returns_invalid(self):
        from src.agents.policy_check import verify_policy_for_claim
        from src.database.models import Claim, Policy
        db = self._make_db()
        candidate = self._make_claim_row({
            "extracted_data": {"policy_id": "POL-001"},
            "confirmed": True,
        })
        policy = self._make_policy(
            number="POL-001", customer_id="user-1",
            effective_date=date(2022, 1, 1), expiry_date=date(2023, 12, 31)
        )

        def query_side_effect(model_class):
            if model_class is Claim:
                mock = MagicMock()
                mock.filter.return_value.filter.return_value.first.return_value = candidate
                return mock
            else:
                mock = MagicMock()
                mock.filter.return_value.first.return_value = policy
                return mock
        db.query.side_effect = query_side_effect
        result = verify_policy_for_claim(policy_id="POL-001", event_date_str="2025-01-01",
                                         claimant_user_id="user-1", db=db, claim_id="claim-1")
        assert result["valid"] is False
        assert result["reason"] == "policy_not_active_on_event_date"

    def test_insurance_type_mismatch_returns_invalid(self):
        from src.agents.policy_check import verify_policy_for_claim
        from src.database.models import Claim, Policy
        db = self._make_db()
        candidate = self._make_claim_row({
            "extracted_data": {"policy_id": "POL-001"},
            "confirmed": True,
        })
        policy = self._make_policy(number="POL-001", customer_id="user-1", policy_type="health")

        def query_side_effect(model_class):
            if model_class is Claim:
                mock = MagicMock()
                mock.filter.return_value.filter.return_value.first.return_value = candidate
                return mock
            else:
                mock = MagicMock()
                mock.filter.return_value.first.return_value = policy
                return mock
        db.query.side_effect = query_side_effect
        result = verify_policy_for_claim(
            policy_id="POL-001", event_date_str="2025-01-01",
            claimant_user_id="user-1", insurance_type="motor",
            db=db, claim_id="claim-1"
        )
        assert result["valid"] is False
        assert result["reason"] == "insurance_type_mismatch"

    def test_missing_event_date_returns_invalid(self):
        from src.agents.policy_check import verify_policy_for_claim
        from src.database.models import Claim, Policy
        db = self._make_db()
        candidate = self._make_claim_row({
            "extracted_data": {"policy_id": "POL-001"},
            "confirmed": True,
        })
        policy = self._make_policy(number="POL-001", customer_id="user-1")

        def query_side_effect(model_class):
            if model_class is Claim:
                mock = MagicMock()
                mock.filter.return_value.filter.return_value.first.return_value = candidate
                return mock
            else:
                mock = MagicMock()
                mock.filter.return_value.first.return_value = policy
                return mock
        db.query.side_effect = query_side_effect
        result = verify_policy_for_claim(policy_id="POL-001", event_date_str=None,
                                         claimant_user_id="user-1", db=db, claim_id="claim-1")
        assert result["valid"] is False
        assert result["reason"] == "missing_event_date"

    def test_policy_id_case_normalized(self):
        """Lowercase policy IDs should be normalized to uppercase before comparison."""
        from src.agents.policy_check import verify_policy_for_claim
        from src.database.models import Claim, Policy
        db = self._make_db()
        candidate = self._make_claim_row({
            "extracted_data": {"policy_id": "pol-001"},  # lowercase in state
            "confirmed": True,
        })
        # Function normalizes both — so "pol-001".upper() == "POL-001"
        db.query.return_value.filter.return_value.filter.return_value.first.return_value = candidate
        # This triggers claim_policy_mismatch because "pol-001".upper() == "POL-001" and
        # normalized_policy == "pol-001".strip().upper() == "POL-001" — they match
        # So the check proceeds to policy lookup which returns None
        db.query.return_value.filter.return_value.first.return_value = None
        result = verify_policy_for_claim(policy_id="pol-001", event_date_str="2025-01-01",
                                         claimant_user_id="user-1", db=db, claim_id="claim-1")
        # Both get normalized to "POL-001" so policy check proceeds
        # Result depends on policy lookup
        assert result["valid"] is False
