"""Authoritative Phase 1 policy verification."""
from datetime import datetime
from typing import Optional, Any

from sqlalchemy.orm import Session

from src.database.models import Policy, Claim


def verify_policy_for_claim(
    policy_id: Optional[str],
    event_date_str: Optional[str],
    claimant_user_id: str,
    insurance_type: Optional[str] = None,
    db: Optional[Session] = None,
    claim_id: Optional[str] = None,
) -> dict[str, Any]:
    """Verify ownership, type, activity and date for the exact claimant claim."""
    result: dict[str, Any] = {"valid": False, "reason": None}
    if db is None:
        result["reason"] = "no_db_session"
        return result
    if not policy_id:
        result["reason"] = "no_policy_id"
        return result

    normalized_policy = policy_id.strip().upper()
    query = db.query(Claim).filter(Claim.claimant_id == claimant_user_id)
    if claim_id:
        query = query.filter(Claim.id == claim_id)
        candidate = query.first()
    else:
        candidate = query.order_by(Claim.created_at.desc()).first()

    if not candidate:
        result["reason"] = "claim_not_found"
        return result

    state = candidate.pipeline_state or {}
    extracted = state.get("extracted_data") or {}
    claim_policy = str(extracted.get("policy_id", "")).strip().upper()
    if claim_policy != normalized_policy:
        result["reason"] = "claim_policy_mismatch"
        return result
    if state.get("confirmed") is not True:
        result["reason"] = "claimant_confirmation_required"
        return result

    policy = db.query(Policy).filter(Policy.policy_number == normalized_policy).first()
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
        event_date = datetime.strptime(str(event_date_str), "%Y-%m-%d").date()
    except ValueError:
        result["reason"] = "invalid_event_date"
        return result
    if not (policy.effective_date <= event_date <= policy.expiry_date):
        result["reason"] = "policy_not_active_on_event_date"
        return result

    result.update({
        "valid": True,
        "policy_number": policy.policy_number,
        "policy_type": policy.policy_type,
        "effective_date": policy.effective_date.isoformat(),
        "expiry_date": policy.expiry_date.isoformat(),
    })
    return result
