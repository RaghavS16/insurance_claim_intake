from src.agents.policy_check import verify_policy_for_claim
from src.database.models import Claim, Policy


def _confirmed_claim(db, policy_number="XYZ123", user_id="TEST_USER_ID"):
    claim = Claim(
        ticket_id="CLAIM-VERIFY-TEST",
        claimant_id=user_id,
        customer_id=user_id,
        status="draft",
        conversation_status="pending_verification",
        pipeline_state={"confirmed": True, "extracted_data": {"policy_id": policy_number}},
    )
    db.add(claim)
    db.commit()
    return claim


def test_policy_not_found_requires_confirmation_first_only_when_claim_exists(db):
    result = verify_policy_for_claim("MISSING", "2025-05-05", "TEST_USER_ID", "motor", db)
    assert not result["valid"]
    assert result["reason"] == "claimant_confirmation_required"


def test_wrong_policy_owner(db):
    _confirmed_claim(db, "XYZ123", "TEST_USER_ID")
    result = verify_policy_for_claim("XYZ123", "2025-05-05", "TEST_USER_ID", "motor", db)
    assert result["valid"]


def test_policy_not_linked(db):
    pol = db.query(Policy).filter(Policy.policy_number == "MOT-5521").first()
    pol.customer_id = None
    db.commit()
    _confirmed_claim(db, "MOT-5521")
    result = verify_policy_for_claim("MOT-5521", "2025-05-05", "TEST_USER_ID", "motor", db)
    assert result["reason"] == "policy_not_linked"


def test_policy_type_mismatch(db):
    _confirmed_claim(db)
    result = verify_policy_for_claim("XYZ123", "2025-05-05", "TEST_USER_ID", "health", db)
    assert result["reason"] == "insurance_type_mismatch"


def test_policy_invalid_on_event_date(db):
    _confirmed_claim(db)
    result = verify_policy_for_claim("XYZ123", "2023-05-05", "TEST_USER_ID", "motor", db)
    assert result["reason"] == "policy_not_active_on_event_date"


def test_verify_policy_no_policy_id(db):
    result = verify_policy_for_claim(None, "2024-05-05", "user1", "motor", db)
    assert result["reason"] == "no_policy_id"


def test_verify_policy_valid_after_confirmation(db):
    _confirmed_claim(db)
    result = verify_policy_for_claim("XYZ123", "2025-05-05", "TEST_USER_ID", "motor", db)
    assert result["valid"] is True
    assert result["policy_number"] == "XYZ123"
