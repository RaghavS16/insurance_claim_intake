"""
Centralized authorization dependencies.

Extracts the claim ownership check into a reusable FastAPI dependency
to eliminate the 6-way duplication across endpoint handlers.
"""
from fastapi import HTTPException, status

from src.database.models import Claim, User


def enforce_claim_ownership(claim: Claim, current_user: User) -> None:
    """
    Enforce that a CLAIMANT user owns the given claim.
    ADJUSTERs and ADMINs bypass this check — they can view and act on any claim.

    Raises HTTP 403 if the claimant does not own the claim.
    """
    # Non-claimant roles (ADJUSTER, ADMIN) have global access to claims
    if current_user.role in ("ADJUSTER", "ADMIN"):
        return

    user_id = str(current_user.id)
    claimant_id = str(claim.claimant_id) if claim.claimant_id else None
    customer_id = claim.customer_id

    if claimant_id and claimant_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You do not own this claim.",
        )
    if customer_id and customer_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You do not own this claim.",
        )
