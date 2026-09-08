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
) -> dict[str, Any]:
    """Verify policy ownership/type/activity/date after explicit claimant confirmation."""
    result: dict[str, Any] = {"valid": False, "reason": None}
    if db is None:
        result["reason"] = "no_db_session"
        return result
    if not policy_id:
        result["reason"] = "no_policy_id"
        return result

    # Verification is a state transition, not a data-completeness shortcut.
    # Require a confirmed draft for this claimant/policy before any verification.
    candidate_claims = db.query(Claim).filter(Claim.claimant_id == claimant_user_id).order_by(Claim.created_at.desc()).all()
    confirmed = False
    for candidate in candidate_claims:
        state = candidate.pipeline_state or {}
        extracted = state.get("extracted_data") or {}
        if str(extracted.get("policy_id", "")).strip().upper() == policy_id.strip().upper() and state.get("confirmed") is True:
            confirmed = True
            break
    if not confirmed:
        result["reason"] = "claimant_confirmation_required"
        return result

    policy = db.query(Policy).filter(Policy.policy_number == policy_id.strip().upper()).first()
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
    result["policy_number"] = policy.policy_number
    result["policy_type"] = policy.policy_type
    result["effective_date"] = policy.effective_date.isoformat()
    result["expiry_date"] = policy.expiry_date.isoformat()
    return result
