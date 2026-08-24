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
from src.agents.policy_check import verify_policy_for_claim

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


class VoiceSessionRequest(BaseModel):
    policy_number: Optional[str] = Field(None, description="Preselected policy number")


class UpdateClaimRequest(BaseModel):
    policy_id: Optional[str] = None
    insurance_type: Optional[str] = None
    event_date: Optional[str] = None
    event_description: Optional[str] = None
    estimated_claim_amount: Optional[float] = None
    extracted_data: Optional[Dict[str, Any]] = None


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
    payload: Optional[VoiceSessionRequest] = None,
    db: Session = Depends(get_db),
):
    """Create a new draft claim session and return ticket_id for WebSocket voice streaming."""
    current_user = _resolve_user(request, db)
    ticket_id = f"CLAIM-{uuid.uuid4().hex[:8].upper()}"
    
    init_extracted: Dict[str, Any] = {}
    if payload and payload.policy_number:
        init_extracted["policy_id"] = payload.policy_number.strip().upper()
    
    claim = Claim(
        ticket_id=ticket_id,
        claimant_id=current_user.id,
        customer_id=str(current_user.id),
        input_mode="voice",
        status="draft",
        conversation_status="not_started",
        pipeline_state={"extracted_data": init_extracted} if init_extracted else {},
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
        "extracted_data": init_extracted,
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


def _verify_response(claim, state, cached=False):
    return {
        "ticket_id": claim.ticket_id,
        "status": claim.status,
        "extracted_data": state.get("extracted_data", {}),
        "policy_verification": state.get("policy_verification"),
        "message": "Claim already verified.",
        "_cached": cached,
    }


def _verification_failure_message(reason: str) -> str:
    messages = {
        "policy_not_found": "We couldn't find a policy with that number. Please double-check and try again.",
        "policy_not_linked": "Please link this policy to your account before filing a claim.",
        "ownership_mismatch": "This policy isn't linked to your account. Please verify the policy number.",
        "insurance_type_mismatch": "This policy type doesn't match the claim you're filing.",
        "policy_inactive": "This policy is currently inactive.",
        "policy_not_active_on_event_date": "This policy wasn't active on the date you reported. Please check the incident date and policy number.",
        "missing_event_date": "We need a valid incident date to verify your policy.",
        "invalid_event_date": "The incident date couldn't be understood. Please provide it again.",
        "no_policy_id": "We need your policy number to verify this claim.",
    }
    return messages.get(reason, "We couldn't verify your policy. A specialist will follow up.")


@router.post("/{ticket_id}/verify")
def verify_claim(
    ticket_id: str,
    request: Request,
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
        raise HTTPException(status_code=400, detail=f"Cannot verify claim: missing mandatory fields {missing}.")

    if claim.status == "verified":
        return _verify_response(claim, state, cached=True)

    extracted = state.get("extracted_data", {})
    raw_itype = extracted.get("insurance_type") or getattr(claim, "insurance_type", None)
    insurance_type = str(raw_itype) if raw_itype else None
    verification = verify_policy_for_claim(
        policy_id=extracted.get("policy_id"),
        event_date_str=extracted.get("event_date"),
        claimant_user_id=str(current_user.id),
        insurance_type=insurance_type,
        db=db,
    )

    if verification["valid"]:
        claim.status = "verified"  # type: ignore
        claim.conversation_status = "verified"  # type: ignore
        message = "Your claim details have been verified."
    else:
        claim.status = "verification_failed"  # type: ignore
        claim.conversation_status = "verification_failed"  # type: ignore
        message = _verification_failure_message(verification.get("reason", ""))

    state["policy_verification"] = verification
    claim.pipeline_state = state  # type: ignore
    db.commit()

    return {
        "ticket_id": claim.ticket_id,
        "status": claim.status,
        "extracted_data": extracted,
        "policy_verification": verification,
        "message": message,
    }


@router.post("/{ticket_id}/confirm")
@router.post("/confirm/{ticket_id}")
async def confirm_claim(
    ticket_id: str,
    request: Request,
    payload: Optional[ClaimConfirmRequest] = None,
    db: Session = Depends(get_db),
):
    """
    Confirm and submit a claim after verifying required fields and policy validity.
    Assigns claim to specialization adjuster and marks status as submitted/confirmed.
    """
    current_user = _resolve_user(request, db)
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found for the given ticket_id.")
    enforce_claim_ownership(claim, current_user)

    state = dict(getattr(claim, "pipeline_state", None) or {})
    extracted = dict(state.get("extracted_data") or {})

    # Extract all required claim fields
    policy_id = extracted.get("policy_id")
    raw_itype = extracted.get("insurance_type") or getattr(claim, "insurance_type", None)
    insurance_type = str(raw_itype) if raw_itype else None
    event_date_str = extracted.get("event_date") or (str(claim.event_date) if claim.event_date else None)
    est_amount = extracted.get("estimated_claim_amount") or getattr(claim, "estimated_claim_amount", None)

    missing = []
    if not policy_id:
        missing.append("Policy ID")
    if not insurance_type:
        missing.append("Insurance Category")
    if not event_date_str:
        missing.append("Incident Date")
    if est_amount is None:
        missing.append("Estimated Cost")

    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot submit claim: Please provide all required details: {', '.join(missing)}.",
        )

    # Perform strict policy verification against database
    verification = verify_policy_for_claim(
        policy_id=str(policy_id),
        event_date_str=str(event_date_str),
        claimant_user_id=str(current_user.id),
        insurance_type=insurance_type,
        db=db,
    )

    if not verification.get("valid"):
        reason = verification.get("reason", "")
        fail_msg = _verification_failure_message(reason)
        claim.status = "verification_failed"
        claim.conversation_status = "verification_failed"
        state["policy_verification"] = verification
        claim.pipeline_state = state
        try:
            db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Claim verification failed: {fail_msg}",
        )

    # Policy verified: Link policy foreign key if available
    from src.database.models import Policy
    pol_record = db.query(Policy).filter(Policy.policy_number == str(policy_id).strip().upper()).first()
    if pol_record:
        claim.policy_id = pol_record.id

    # Mark as confirmed / submitted
    claim.status = "submitted"
    claim.conversation_status = "confirmed"

    state["confirmed"] = True
    state["awaiting_confirmation"] = False
    state["policy_verification"] = verification
    claim.pipeline_state = state

    # Assign to an adjuster matching the specialization if available
    try:
        from src.database.models import Adjuster
        claim_itype = claim.insurance_type or extracted.get("insurance_type")
        if claim_itype:
            adjuster = db.query(Adjuster).filter(
                Adjuster.specialization == claim_itype,
                Adjuster.is_active == True
            ).first()
            if adjuster:
                adjuster.claims_assigned = (adjuster.claims_assigned or 0) + 1
    except Exception:
        pass

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to confirm claim: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save claim confirmation.")

    return {
        "ticket_id": claim.ticket_id,
        "status": "submitted",
        "conversation_status": "confirmed",
        "confirmed": True,
        "policy_verification": verification,
        "message": f"Claim #{ticket_id} has been verified, confirmed, and submitted to an adjuster.",
    }


@router.post("/message/{ticket_id}")
async def send_claim_message(
    ticket_id: str,
    payload: Dict[str, Any],
    request: Request,
    db: Session = Depends(get_db),
):
    """Text-based message submission fallback for claim intake."""
    message_text = payload.get("message") or payload.get("text") or ""
    req = ClaimIntakeRequest(
        claim_text=message_text,
        input_mode="text",
        ticket_id=ticket_id,
    )
    result = await intake_claim(req, request, db)
    return {
        "ticket_id": ticket_id,
        "agent_message": result.get("message"),
        "extracted_data": result.get("extracted_data"),
        "missing_fields": result.get("missing_fields"),
        "confirmed": result.get("confirmed", False),
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
        "insurance_type": claim.insurance_type,
        "event_date": str(claim.event_date) if claim.event_date else None,
        "event_description": claim.event_description,
        "estimated_claim_amount": float(claim.estimated_claim_amount) if claim.estimated_claim_amount is not None else None,  # type: ignore[arg-type]
        "extracted_data": state.get("extracted_data") or {},
        "missing_fields": state.get("missing_fields") or [],
        "response_message": state.get("response_message"),
        "created_at": claim.created_at.isoformat() if claim.created_at else None,
    }


@router.patch("/{ticket_id}")
def update_claim_details(
    ticket_id: str,
    payload: UpdateClaimRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Partially update claim details and extracted data."""
    from datetime import datetime
    current_user = _resolve_user(request, db)
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found for the given ticket_id.")
    enforce_claim_ownership(claim, current_user)

    state = dict(getattr(claim, "pipeline_state", None) or {})
    extracted = dict(state.get("extracted_data") or {})

    if payload.extracted_data:
        extracted.update(payload.extracted_data)

    if payload.policy_id is not None:
        extracted["policy_id"] = payload.policy_id.strip().upper() if payload.policy_id else None

    if payload.insurance_type is not None:
        claim.insurance_type = payload.insurance_type.strip().lower() if payload.insurance_type else None
        extracted["insurance_type"] = claim.insurance_type

    if payload.event_date is not None:
        extracted["event_date"] = payload.event_date.strip() if payload.event_date else None
        if payload.event_date and payload.event_date.strip():
            try:
                claim.event_date = datetime.strptime(payload.event_date.strip(), "%Y-%m-%d").date()
            except ValueError:
                pass

    if payload.event_description is not None:
        claim.event_description = payload.event_description
        extracted["event_description"] = payload.event_description

    if payload.estimated_claim_amount is not None:
        claim.estimated_claim_amount = payload.estimated_claim_amount
        extracted["estimated_claim_amount"] = payload.estimated_claim_amount

    state["extracted_data"] = extracted
    claim.pipeline_state = state

    try:
        db.commit()
        db.refresh(claim)
    except Exception:
        db.rollback()
        logger.exception("Failed to patch claim %s", ticket_id)
        raise HTTPException(status_code=500, detail="Failed to update claim.")

    return {
        "ticket_id": claim.ticket_id,
        "status": claim.status,
        "conversation_status": claim.conversation_status,
        "insurance_type": claim.insurance_type,
        "event_date": str(claim.event_date) if claim.event_date else None,
        "event_description": claim.event_description,
        "estimated_claim_amount": float(claim.estimated_claim_amount) if claim.estimated_claim_amount is not None else None,
        "extracted_data": extracted,
        "message": "Claim updated successfully.",
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
            "insurance_type": c.insurance_type,
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
