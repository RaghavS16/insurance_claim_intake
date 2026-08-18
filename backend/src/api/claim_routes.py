"""
Claim intake and management API routes.

Handles claim creation, voice sessions, text intake, confirmation,
document upload, and claim listing.
Extracted from the monolithic main.py for clean architectural separation.
"""
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.config import settings
from src.database.session import get_db
from src.database.models import Claim, ConversationTurn, User
from src.agents.graph import build_conversation_graph
from src.api.voice_ws import process_claimant_turn
from src.utils.authorization import enforce_claim_ownership
from src.utils.logger import app_logger
from src.agents.policy_check import verify_policy_basic

logger = app_logger
router = APIRouter(prefix="/api/v1/claims", tags=["Claims"])




# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------
class ClaimIntakeRequest(BaseModel):
    claim_text: str = Field(..., min_length=1, max_length=5000, description="User utterance or input text")
    input_mode: str = Field("text", description="'voice' or 'text'")
    ticket_id: Optional[str] = Field(None, description="Existing claim ticket ID for subsequent turns")


class ClaimConfirmRequest(BaseModel):
    confirmed: bool = Field(True, description="True to confirm and submit claim")


# ---------------------------------------------------------------------------
# Lazy dependency accessor to avoid circular imports
# ---------------------------------------------------------------------------
def _get_current_user():
    """Lazy import to break the circular dependency between main.py and route modules."""
    from src.api.main import get_current_user
    return get_current_user


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/voice-session")
def start_voice_session(
    request: Request,
    db: Session = Depends(get_db),
):
    """Create a new draft claim session and return ticket_id for WebSocket voice streaming."""
    current_user = _resolve_user(request, db)
    ticket_id = f"CLAIM-{uuid.uuid4().hex[:8].upper()}"
    claim = Claim(
        ticket_id=ticket_id,
        claimant_id=current_user.id,
        customer_id=str(current_user.id),
        input_mode="voice",
        status="draft",
        conversation_status="not_started",
    )
    db.add(claim)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to create voice session")
        raise HTTPException(status_code=500, detail="Failed to create claim session.")
    return {
        "ticket_id": ticket_id,
        "initial_message": "Please tell me what happened. You can describe the incident in your own words, and I'll collect the details I need.",
    }


@router.post("/intake")
async def intake_claim(
    payload: ClaimIntakeRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Process user claim utterance, extract mandatory fields, and evaluate missing fields."""
    current_user = _resolve_user(request, db)
    claim = None
    user_id = str(current_user.id)

    if payload.ticket_id:
        claim = db.query(Claim).filter(Claim.ticket_id == payload.ticket_id).first()
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found for the given ticket_id.")
        enforce_claim_ownership(claim, current_user)

    # Short-circuit if already evaluated to prevent overwriting confirmed data
    if claim and getattr(claim, "status", None) == "evaluated":
        state = dict(getattr(claim, "pipeline_state", None) or {})
        return {
            "ticket_id": claim.ticket_id,
            "extracted_data": state.get("extracted_data", {}),
            "missing_fields": state.get("missing_fields", []),
            "awaiting_confirmation": state.get("awaiting_confirmation", True),
            "message": "Claim already evaluated. Use GET /api/v1/claims/{ticket_id} to see result.",
        }

    ticket_id = payload.ticket_id or (claim.ticket_id if claim else f"CLAIM-{uuid.uuid4().hex[:8].upper()}")

    if claim is None:
        claim = Claim(
            ticket_id=ticket_id,
            claimant_id=current_user.id,
            customer_id=user_id,
            input_mode=payload.input_mode,
            status="draft",
        )
        db.add(claim)
        db.flush()

    prior_turns = db.query(ConversationTurn).filter(ConversationTurn.claim_id == claim.id).count()
    turn_num = prior_turns + 1

    try:
        result = await process_claimant_turn(db, claim, payload.claim_text, payload.input_mode, turn_num)
    except Exception as exc:
        logger.exception("intake_claim: conversation turn processing failed")
        raise HTTPException(
            status_code=503,
            detail=(
                "The claim processing pipeline encountered an error. "
                "Please try again in a moment. "
                f"(Error: {type(exc).__name__})"
            ),
        )

    return {
        "ticket_id": ticket_id,
        "extracted_data": result.get("extracted_data", {}),
        "missing_fields": result.get("missing_fields", []),
        "field_status": result.get("field_status", {}),
        "awaiting_confirmation": result.get("awaiting_confirmation", False),
        "confirmed": result.get("confirmed", False),
        "conversation_status": result.get("conversation_status"),
        "message": result.get("next_question") or result.get("message", ""),
    }


@router.post("/{ticket_id}/confirm")
def confirm_claim(
    ticket_id: str,
    request: Request,
    payload: ClaimConfirmRequest = ClaimConfirmRequest(),
    db: Session = Depends(get_db),
):
    current_user = _resolve_user(request, db)
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found for the given ticket_id.")
    enforce_claim_ownership(claim, current_user)

    state = dict(getattr(claim, "pipeline_state", None) or {})
    missing = state.get("missing_fields", [])
    if missing:
        raise HTTPException(status_code=400, detail=f"Cannot confirm claim: missing mandatory fields {missing}.")

    if claim.status == "verified":
        return {
            "ticket_id": claim.ticket_id,
            "status": claim.status,
            "extracted_data": state.get("extracted_data", {}),
            "policy_valid": state.get("policy_valid"),
            "message": "Claim already verified.",
            "_cached": True,
        }

    policy_id = state.get("extracted_data", {}).get("policy_id")
    policy_valid = verify_policy_basic(policy_id, db)

    claim.status = "verified"  # type: ignore
    claim.conversation_status = "claimant_confirmed"  # type: ignore
    state["policy_valid"] = policy_valid
    claim.pipeline_state = state  # type: ignore
    db.commit()

    return {
        "ticket_id": claim.ticket_id,
        "status": claim.status,
        "extracted_data": state.get("extracted_data", {}),
        "policy_valid": policy_valid,
        "message": "Your claim details have been verified." if policy_valid else "Details verified, but we couldn't confirm your policy. A specialist will follow up.",
    }


@router.get("/{ticket_id}/conversation")
def get_conversation_history(
    ticket_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Fetch the complete chronological conversation turns for a claim."""
    current_user = _resolve_user(request, db)
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found for the given ticket_id.")
    enforce_claim_ownership(claim, current_user)

    turns = (
        db.query(ConversationTurn)
        .filter(ConversationTurn.claim_id == claim.id)
        .order_by(ConversationTurn.turn_number, ConversationTurn.created_at)
        .all()
    )
    return [
        {
            "turn": t.turn_number,
            "speaker": t.speaker,
            "text": t.text,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in turns
    ]


@router.get("/{ticket_id}")
def get_claim(
    ticket_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Retrieve current status and structured state of a claim."""
    current_user = _resolve_user(request, db)
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found for the given ticket_id.")
    enforce_claim_ownership(claim, current_user)

    state = claim.pipeline_state or {}
    return {
        "ticket_id": claim.ticket_id,
        "status": claim.status,
        "conversation_status": claim.conversation_status,
        "claim_type": claim.claim_type,
        "incident_date": str(claim.incident_date) if claim.incident_date else None,
        "description": claim.description,
        "claimed_amount": float(claim.claimed_amount) if claim.claimed_amount is not None else None,  # type: ignore[arg-type]
        "extracted_data": state.get("extracted_data") or {},
        "missing_fields": state.get("missing_fields") or [],
        "response_message": state.get("response_message"),
        "created_at": claim.created_at.isoformat() if claim.created_at else None,
    }


@router.get("")
def list_claims(
    request: Request,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    """List claims owned by the authenticated user with pagination."""
    current_user = _resolve_user(request, db)

    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    user_id = str(current_user.id)
    query = db.query(Claim).filter(
        (Claim.claimant_id == current_user.id) | (Claim.customer_id == user_id)
    ).order_by(Claim.created_at.desc())

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
            "extracted_data": st.get("extracted_data") or {},
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })
    return {
        "items": results,
        "total": total,
        "page": page,
        "page_size": page_size,
    }




# ---------------------------------------------------------------------------
# Helper: resolve authenticated user from request
# ---------------------------------------------------------------------------
def _resolve_user(request: Request, db: Session) -> User:
    """
    Resolve authenticated user via the centralized get_current_user dependency.
    Uses lazy import to avoid circular imports.
    """
    from src.api.main import get_current_user
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
    
    security = HTTPBearer(auto_error=False)
    # Extract token from Authorization header
    auth_header = request.headers.get("authorization", "")
    credentials = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    
    # Call get_current_user with the resolved dependencies
    db_gen = None
    try:
        return get_current_user(request=request, credentials=credentials, db=db)
    except Exception:
        raise
