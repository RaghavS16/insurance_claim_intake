"""
Adjuster-specific API routes.

Handles claim review pipeline and decision submission for adjusters.
Extracted from the monolithic main.py for clean architectural separation.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.database.session import get_db
from src.database.models import Claim, User
from src.utils.validators import (
    validate_enum, VALID_FINAL_DECISIONS, VALID_CLOSURE_STATUSES,
)
from src.utils.logger import app_logger

logger = app_logger
router = APIRouter(prefix="/api/v1/adjuster", tags=["Adjuster"])


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------
class ClaimReviewRequest(BaseModel):
    final_decision: str = Field(
        ...,
        description="Decision for the claim: approved, denied, need_more_info, need_documents, flagged_for_review, manual_review",
    )
    closure_status: str = Field(
        ...,
        description="Closure status: awaiting_user, pending_review, closed",
    )


# ---------------------------------------------------------------------------
# Helper: resolve authenticated user from request
# ---------------------------------------------------------------------------
def _resolve_user(request: Request, db: Session) -> User:
    """Resolve authenticated user via the centralized get_current_user dependency."""
    from src.api.main import get_current_user

    auth_header = request.headers.get("authorization", "")
    credentials = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    return get_current_user(request=request, credentials=credentials, db=db)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/claims")
def adjuster_list_claims(
    request: Request,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
):
    """
    List all submitted/evaluated claims for adjuster review.
    Only claims past the 'draft' stage are shown. Supports pagination.
    """
    current_user = _resolve_user(request, db)

    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 50

    query = (
        db.query(Claim)
        .filter(Claim.status.in_(["submitted", "evaluated"]))
        .order_by(Claim.created_at.desc())
    )
    total = query.count()
    offset = (page - 1) * page_size
    claims = query.offset(offset).limit(page_size).all()

    results = []
    for c in claims:
        st = c.pipeline_state or {}
        results.append({
            "id": str(c.id),
            "ticket_id": c.ticket_id,
            "claim_type": c.claim_type,
            "status": c.status,
            "conversation_status": c.conversation_status,
            "final_decision": c.final_decision,
            "closure_status": c.closure_status,
            "extracted_data": st.get("extracted_data") or {},
            "claimant_id": str(c.claimant_id) if c.claimant_id else None,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })

    return results


@router.post("/claims/{ticket_id}/review")
def adjuster_review_claim(
    ticket_id: str,
    payload: ClaimReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Submit an adjuster's review decision for a claim with validated enum values."""
    current_user = _resolve_user(request, db)

    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found for the given ticket_id.")

    # Validate enum values
    try:
        clean_decision = validate_enum(payload.final_decision, VALID_FINAL_DECISIONS, "final_decision")
        clean_closure = validate_enum(payload.closure_status, VALID_CLOSURE_STATUSES, "closure_status")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    claim.final_decision = clean_decision  # type: ignore
    claim.closure_status = clean_closure  # type: ignore

    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to persist adjuster review for claim %s", ticket_id)
        raise HTTPException(status_code=500, detail="Failed to save review decision.")

    return {
        "ticket_id": claim.ticket_id,
        "final_decision": claim.final_decision,
        "closure_status": claim.closure_status,
        "message": f"Claim {ticket_id} reviewed successfully.",
    }
