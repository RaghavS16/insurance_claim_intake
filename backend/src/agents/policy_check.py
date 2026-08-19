from datetime import date, datetime
from typing import Optional, Any
from sqlalchemy.orm import Session
from src.database.models import Policy


def verify_policy_for_claim(
    policy_id: Optional[str],
    event_date_str: Optional[str],
    claimant_user_id: str,
    insurance_type: Optional[str] = None,
    db: Optional[Session] = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"valid": False, "reason": None}

    if db is None:
        result["reason"] = "no_db_session"
        return result

    if not policy_id:
        result["reason"] = "no_policy_id"
        return result

    policy = db.query(Policy).filter(
        Policy.policy_number == policy_id.strip().upper()
    ).first()

    if not policy:
        result["reason"] = "policy_not_found"
        return result

    if policy.customer_id is None:
        result["reason"] = "policy_not_linked"
        return result

    if str(policy.customer_id) != claimant_user_id:
        result["reason"] = "ownership_mismatch"
        return result

    if insurance_type and policy.policy_type != insurance_type:
        result["reason"] = "insurance_type_mismatch"
        return result

    if not policy.is_active:
        result["reason"] = "policy_inactive"
        return result

    if not event_date_str:
        result["reason"] = "missing_event_date"
        return result

    try:
        event_date = datetime.strptime(event_date_str, "%Y-%m-%d").date()
    except ValueError:
        result["reason"] = "invalid_event_date"
        return result

    if not (policy.effective_date <= event_date <= policy.expiry_date):
        result["reason"] = "policy_not_active_on_event_date"
        return result

    result["valid"] = True
    return result
