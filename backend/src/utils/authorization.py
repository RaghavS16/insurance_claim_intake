"""Centralized claim authorization.

Claimants may access only their own claims. Adjusters may access only claims
assigned to them. Administrators have global claim access.
"""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.database.models import Adjuster, Claim, User

def enforce_claim_ownership(claim: Claim, current_user: User, db: Session | None = None) -> None:
    role = str(current_user.role).upper()
    if role == "ADMIN":
        return
    user_id = str(current_user.id)
    if role == "ADJUSTER":
        if db is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Claim access requires assignment context.")
        from src.database.hardening_models import ClaimAssignment
        assignment = (
            db.query(ClaimAssignment)
            .filter(
                ClaimAssignment.claim_id == claim.id,
                ClaimAssignment.is_active.is_(True),
                ClaimAssignment.adjuster_id.in_(
                    db.query(Adjuster.id).filter(Adjuster.email == current_user.email)
                ),
            )
            .first()
        )
        if not assignment:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Claim is not assigned to this adjuster.")
        return
    claimant_id = str(claim.claimant_id) if claim.claimant_id else None
    customer_id = str(claim.customer_id) if claim.customer_id else None
    if (claimant_id and claimant_id != user_id) or (customer_id and customer_id != user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: You do not own this claim.")
