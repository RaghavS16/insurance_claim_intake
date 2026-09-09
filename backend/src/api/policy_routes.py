"""
Policy Management & Verified Linking API Routes.

Allows claimants to link policies to their account using PII validation
(Date of Birth and Last 4 digits of phone number) and list linked policies.
"""
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.database.session import get_db
from src.database.models import Policy, PolicyLinkAudit, User
from src.utils.logger import app_logger
from src.utils.rate_limiter import enforce_rate_limit
from src.api.deps import get_current_user

logger = app_logger
router = APIRouter(prefix="/api/v1/policies", tags=["Policies"])

MAX_LINK_ATTEMPTS = 5


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------
class LinkPolicyRequest(BaseModel):
    policy_number: str = Field(..., min_length=3, max_length=20, description="Policy number e.g. MOT-5521")
    policyholder_name: Optional[str] = Field(None, min_length=1, max_length=255, description="Full name of policyholder (Optional)")
    date_of_birth: str = Field(..., description="Date of birth in YYYY-MM-DD format")
    phone_last4: str = Field(..., min_length=4, max_length=4, description="Last 4 digits of phone number")


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------
def _resolve_user(request: Request, db: Session) -> User:
    """Resolve authenticated user via centralized get_current_user dependency."""
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
    Requires Date of Birth and Phone Last 4 digits.
    Enforces maximum attempt rate-limiting and logs all outcomes to the audit table.
    """
    enforce_rate_limit(request, action="link_policy", max_requests=10, window_seconds=60)
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
    
    stored_phone = policy.policyholder_phone_last4 or (policy.policyholder_phone[-4:] if policy.policyholder_phone else None)
    phone_match = stored_phone == payload.phone_last4.strip() if stored_phone else False

    name_match = True
    if payload.policyholder_name and policy.policyholder_name:
        req_name = payload.policyholder_name.strip().lower()
        pol_name = policy.policyholder_name.strip().lower()
        name_match = (req_name == pol_name) or (req_name in pol_name) or (pol_name in req_name)
    elif payload.policyholder_name and not policy.policyholder_name:
        policy.policyholder_name = payload.policyholder_name.strip()  # type: ignore[assignment]

    if not (dob_match and phone_match and name_match):
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
        "policyholder_name": policy.policyholder_name,
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
