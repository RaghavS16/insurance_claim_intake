"""
Centralized authorization dependencies.

Extracts the claim ownership check into a reusable FastAPI dependency
to eliminate the 6-way duplication across endpoint handlers.
"""
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.database.session import get_db
from src.database.models import Claim, User


def get_claim_with_ownership(
    ticket_id: str,
    db: Session = Depends(get_db),
) -> Claim:
    """
    Fetch a claim by ticket_id. Raises 404 if not found.
    Does NOT enforce ownership — use `enforce_claim_ownership` for that.
    """
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Claim not found for the given ticket_id.",
        )
    return claim


def enforce_claim_ownership(claim: Claim, current_user: User) -> None:
    """
    Enforce that a CLAIMANT user owns the given claim.
    ADJUSTERs bypass this check (they can view any claim).

    Raises HTTP 403 if the claimant does not own the claim.
    """
    if current_user.role != "CLAIMANT":
        return  # Adjusters can access any claim

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
