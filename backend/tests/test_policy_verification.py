import uuid

from src.agents.policy_check import verify_policy_for_claim
from src.database.models import Claim, Policy


def _claim(db, policy_number="XYZ123", user_id="TEST_USER_ID", confirmed=True):
    claim = Claim(
        ticket_id=f"CLAIM-VERIFY-{uuid.uuid4().hex[:8]}",
        claimant_id=user_id,
        customer_id=user_id,
        status="draft",
        conversation_status="pending_verification" if confirmed else "collecting",
        pipeline_state={"confirmed": confirmed, "extracted_data": {"policy_id": policy_number}},
    )
    db.add(claim)
    db.commit()
    return claim


def test_policy_requires_confirmation(db):
    _claim(db, confirmed=False)
    result = verify_policy_for_claim("XYZ123", "2025-05-05", "TEST_USER_ID", "motor", db)
    assert not result["valid"]
    assert result["reason"] == "claimant_confirmation_required"


def test_policy_not_linked(db):
    pol = db.query(Policy).filter(Policy.policy_number == "MOT-5521").first()
    pol.customer_id = None
    db.commit()
    _claim(db, "MOT-5521")
    result = verify_policy_for_claim("MOT-5521", "2025-05-05", "TEST_USER_ID", "motor", db)
    assert result["reason"] == "policy_not_linked"


def test_policy_type_mismatch(db):
    _claim(db)
    result = verify_policy_for_claim("XYZ123", "2025-05-05", "TEST_USER_ID", "health", db)
    assert result["reason"] == "insurance_type_mismatch"


def test_policy_invalid_on_event_date(db):
    _claim(db)
    result = verify_policy_for_claim("XYZ123", "2023-05-05", "TEST_USER_ID", "motor", db)
    assert result["reason"] == "policy_not_active_on_event_date"


def test_verify_policy_no_policy_id(db):
    result = verify_policy_for_claim(None, "2024-05-05", "user1", "motor", db)
    assert result["reason"] == "no_policy_id"


def test_verify_policy_valid_after_confirmation(db):
    _claim(db)
    result = verify_policy_for_claim("XYZ123", "2025-05-05", "TEST_USER_ID", "motor", db)
    assert result["valid"] is True
    assert result["policy_number"] == "XYZ123"
