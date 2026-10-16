"""Authoritative Phase 1 policy verification."""
from datetime import datetime
from typing import Optional, Any

from sqlalchemy.orm import Session

from src.database.models import Policy, Claim, User


def verify_policy_for_claim(
    policy_id: Optional[str],
    event_date_str: Optional[str],
    claimant_user_id: str,
    insurance_type: Optional[str] = None,
    db: Optional[Session] = None,
    claim_id: Optional[str] = None,
) -> dict[str, Any]:
    """Verify ownership, type, activity and date for the exact claimant claim as soon as policy_id is provided."""
    result: dict[str, Any] = {"valid": False, "reason": None, "identity_verified": False}
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

    state = candidate.pipeline_state if isinstance(getattr(candidate, "pipeline_state", None), dict) else {}
    extracted = state.get("extracted_data") if isinstance(state.get("extracted_data"), dict) else {}
    claim_policy = extracted.get("policy_id")
    if isinstance(claim_policy, str) and claim_policy.strip():
        if claim_policy.strip().upper() != normalized_policy:
            result["reason"] = "claim_policy_mismatch"
            return result

    tenant_id = getattr(candidate, "tenant_id", None)
    if tenant_id is not None:
        policy = db.query(Policy).filter(
            Policy.policy_number == normalized_policy,
            Policy.tenant_id == tenant_id,
        ).first()
    else:
        policy = db.query(Policy).filter(Policy.policy_number == normalized_policy).first()

    if not policy:
        result["reason"] = "policy_not_found"
        return result

    # Check ownership
    if policy.customer_id is not None:
        if str(policy.customer_id) != str(claimant_user_id):
            result["reason"] = "ownership_mismatch"
            return result
    else:
        result["valid"] = False
        result["reason"] = "policy_not_linked"
        result["identity_verified"] = False
        return result

    result["identity_verified"] = True

    if insurance_type and policy.policy_type and policy.policy_type.lower() != insurance_type.lower():
        result["reason"] = "insurance_type_mismatch"
        return result

    if not policy.is_active or getattr(policy, "status", "active") in ("cancelled", "lapsed", "expired"):
        result["reason"] = "policy_inactive"
        return result

    date_verified = False
    if event_date_str:
        try:
            event_date = datetime.strptime(event_date_str, "%Y-%m-%d").date()
            if not (policy.effective_date <= event_date <= policy.expiry_date):
                result["reason"] = "policy_not_active_on_event_date"
                return result
            date_verified = True
        except ValueError:
            result["reason"] = "invalid_event_date"
            return result
    else:
        today = datetime.now().date()
        if policy.expiry_date and policy.expiry_date < today:
            result["reason"] = "policy_expired"
            return result

    fraud_flags: list[dict[str, Any]] = []
    if date_verified and db is not None:
        try:
            from datetime import timedelta
            from src.database.hardening_models import ClaimException
            window_start = event_date - timedelta(days=7)
            window_end = event_date + timedelta(days=7)

            other_claims = (
                db.query(Claim)
                .filter(
                    Claim.policy_id == policy.id,
                    Claim.id != candidate.id,
                    Claim.event_date.isnot(None),
                    Claim.event_date >= window_start,
                    Claim.event_date <= window_end,
                    Claim.status.notin_(["discarded", "rejected"]),
                )
                .all()
            )
            for oc in other_claims:
                fraud_flags.append({
                    "flag": "duplicate_loss_window",
                    "severity": "high",
                    "reason": f"Potential duplicate claim detected: Claim #{oc.ticket_id} occurred on {oc.event_date} (within ±7 days of {event_date}).",
                    "related_ticket_id": oc.ticket_id,
                })

            if policy.effective_date:
                days_since_inception = (event_date - policy.effective_date).days
                if 0 <= days_since_inception <= 7:
                    fraud_flags.append({
                        "flag": "early_loss_inception_proximity",
                        "severity": "high",
                        "reason": f"Early loss warning: Incident occurred {days_since_inception} day(s) after policy inception ({policy.effective_date}).",
                    })

            if fraud_flags and candidate.id:
                for ff in fraud_flags:
                    existing_exc = db.query(ClaimException).filter(
                        ClaimException.claim_id == candidate.id,
                        ClaimException.event_type == "duplicate_or_early_loss_warning",
                        ClaimException.reason == ff["reason"],
                        ClaimException.status == "open",
                    ).first()
                    if not existing_exc:
                        db.add(ClaimException(
                            tenant_id=str(candidate.tenant_id or ""),
                            claim_id=candidate.id,
                            event_type="duplicate_or_early_loss_warning",
                            severity="high",
                            reason=ff["reason"],
                            source_type="FRAUD_DETECTION_ENGINE",
                            source_id="velocity_rules",
                            blocking=False,
                            status="open",
                            resolution_json=ff,
                        ))
                db.flush()
        except Exception:
            pass

    result.update({
        "valid": True,
        "identity_verified": True,
        "date_verified": date_verified,
        "policy_number": policy.policy_number,
        "policy_type": policy.policy_type,
        "effective_date": policy.effective_date.isoformat(),
        "expiry_date": policy.expiry_date.isoformat(),
        "coverage_amount": float(policy.coverage_amount) if policy.coverage_amount is not None else None,
        "fraud_flags": fraud_flags,
        "verification_steps": [
            {"step": "Policyholder Identity Verification", "passed": True},
            {"step": "Policy In-Force Status", "passed": True},
            {"step": "Incident Date Coverage Validity", "passed": date_verified},
            {"step": "Claim Eligibility & Schedule", "passed": True},
        ],
    })
    return result
