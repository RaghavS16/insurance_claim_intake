from datetime import datetime
from typing import Any, Optional
from sqlalchemy.orm import Session
from src.database.models import Policy


def verify_policy_for_claim(
    policy_id: Optional[str],
    event_date_str: Optional[str],
    claimant_user_id: str,
    db: Session,
    insurance_type: Optional[str] = None,
) -> dict[str, Any]:
    """Verify policy existence, ownership, active coverage, and optional type match."""
    result: dict[str, Any] = {"valid": False, "reason": None}

    if not policy_id:
        result["reason"] = "no_policy_id"
        return result

    policy = db.query(Policy).filter(Policy.policy_number == policy_id.strip().upper()).first()
    if not policy:
        result["reason"] = "policy_not_found"
        return result

    if str(policy.customer_id) != claimant_user_id:
        result["reason"] = "ownership_mismatch"
        return result

    if insurance_type and str(policy.policy_type).lower() != insurance_type.lower():
        result["reason"] = "policy_type_mismatch"
        result["policy_type"] = policy.policy_type
        return result

    if not event_date_str:
        result["reason"] = "missing_event_date"
        return result

    try:
        event_date = datetime.strptime(event_date_str, "%Y-%m-%d").date()
    except ValueError:
        result["reason"] = "invalid_event_date"
        return result

    if not policy.is_active:
        result["reason"] = "policy_inactive"
        return result

    if not (policy.effective_date <= event_date <= policy.expiry_date):
        result["reason"] = "policy_not_active_on_event_date"
        return result

    result.update({
        "valid": True,
        "policy_number": policy.policy_number,
        "policy_type": policy.policy_type,
        "coverage_amount": float(policy.coverage_amount),
        "deductible": float(policy.deductible),
    })
    return result
