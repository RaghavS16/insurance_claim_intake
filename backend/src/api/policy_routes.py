"""
Policy Management & Verified Linking API Routes.

Allows claimants to link policies to their account using PII validation
(Date of Birth and Last 4 digits of phone number) and list linked policies.
"""
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.database.session import get_db
from src.database.models import Policy, PolicyLinkAudit, User
from src.utils.logger import app_logger

logger = app_logger
router = APIRouter(prefix="/api/v1/policies", tags=["Policies"])

MAX_LINK_ATTEMPTS = 5


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------
class LinkPolicyRequest(BaseModel):
    policy_number: str = Field(..., min_length=3, max_length=20, description="Policy number e.g. MOT-5521")
    date_of_birth: str = Field(..., description="Date of birth in YYYY-MM-DD format")
    phone_last4: str = Field(..., min_length=4, max_length=4, description="Last 4 digits of phone number")


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------
def _resolve_user(request: Request, db: Session) -> User:
    """Resolve authenticated user via centralized get_current_user dependency."""
    from src.api.main import get_current_user
    from fastapi.security import HTTPAuthorizationCredentials

    auth_header = request.headers.get("authorization", "")
    credentials = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    return get_current_user(request=request, credentials=credentials, db=db)


def _audit(db: Session, user_id: Any, policy_number: str, outcome: str, ip: Optional[str] = None):
    """Log a policy linking attempt to the policy_link_audit table."""
    try:
        audit = PolicyLinkAudit(
            user_id=user_id,
            policy_number=policy_number,
            outcome=outcome,
            ip_address=ip,
            created_at=datetime.now(timezone.utc),
        )
        db.add(audit)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to write to policy_link_audit")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/link")
def link_policy(
    payload: LinkPolicyRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Verify policyholder PII and link an existing policy to the claimant's account.
    Enforces maximum attempt rate-limiting and logs all outcomes to the audit table.
    """
    current_user = _resolve_user(request, db)
    ip = request.client.host if request.client else "unknown"
    policy_number = payload.policy_number.strip().upper()

    policy = db.query(Policy).filter(Policy.policy_number == policy_number).first()

    if not policy:
        _audit(db, current_user.id, policy_number, "not_found", ip)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="We couldn't verify those details.",
        )

    if (policy.link_attempts or 0) >= MAX_LINK_ATTEMPTS:
        _audit(db, current_user.id, policy_number, "rate_limited", ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please contact support.",
        )

    if policy.customer_id is not None:
        if str(policy.customer_id) == str(current_user.id):
            return {
                "policy_number": policy_number,
                "linked": True,
                "already_linked": True,
                "message": "This policy is already linked to your account.",
            }
        _audit(db, current_user.id, policy_number, "already_linked_other", ip)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This policy is already linked to another account.",
        )

    # Validate PII: Date of Birth and Last 4 digits of phone number
    dob_match = str(policy.policyholder_dob) == payload.date_of_birth.strip()
    phone_match = str(policy.policyholder_phone_last4) == payload.phone_last4.strip()

    if not (dob_match and phone_match):
        policy.link_attempts = int(getattr(policy, "link_attempts", 0) or 0) + 1  # type: ignore[assignment]
        db.commit()
        _audit(db, current_user.id, policy_number, "pii_mismatch", ip)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="We couldn't verify those details.",
        )

    # Success: Associate policy with user
    policy.customer_id = current_user.id  # type: ignore[assignment]
    policy.linked_at = datetime.now(timezone.utc)  # type: ignore[assignment]
    policy.link_attempts = 0  # type: ignore[assignment]
    db.commit()
    _audit(db, current_user.id, policy_number, "success", ip)

    cov_amt = float(getattr(policy, "coverage_amount", 0) or 0)
    return {
        "policy_number": policy_number,
        "linked": True,
        "already_linked": False,
        "policy_type": policy.policy_type,
        "coverage_amount": cov_amt,
        "expiry_date": str(policy.expiry_date),
        "message": "Policy successfully linked to your account.",
    }


@router.get("/my-policies")
def list_my_policies(
    request: Request,
    db: Session = Depends(get_db),
):
    """List all policies linked to the currently authenticated claimant."""
    current_user = _resolve_user(request, db)
    policies = (
        db.query(Policy)
        .filter(Policy.customer_id == current_user.id)
        .order_by(Policy.created_at.desc())
        .all()
    )

    results = []
    for p in policies:
        cov_val = float(getattr(p, "coverage_amount", 0) or 0)
        ded_val = float(getattr(p, "deductible", 0) or 0)
        linked_at_val = getattr(p, "linked_at", None)
        results.append({
            "policy_number": p.policy_number,
            "policy_type": p.policy_type,
            "coverage_amount": cov_val,
            "deductible": ded_val,
            "is_active": p.is_active,
            "effective_date": str(p.effective_date),
            "expiry_date": str(p.expiry_date),
            "policyholder_name": p.policyholder_name,
            "linked_at": linked_at_val.isoformat() if linked_at_val else None,
        })
    return results
