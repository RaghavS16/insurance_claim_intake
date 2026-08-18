"""
Claim intake and management API routes.
"""
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.database.session import get_db
from src.database.models import Claim, ConversationTurn, User
from src.api.voice_ws import process_claimant_turn
from src.utils.authorization import enforce_claim_ownership
from src.utils.logger import app_logger
from src.agents.policy_check import verify_policy_for_claim

logger = app_logger
router = APIRouter(prefix="/api/v1/claims", tags=["Claims"])


class ClaimIntakeRequest(BaseModel):
    claim_text: str = Field(..., min_length=1, max_length=5000)
    input_mode: str = Field("text")
    ticket_id: Optional[str] = None


class ClaimConfirmRequest(BaseModel):
    confirmed: bool = True


def _resolve_user(request: Request, db: Session) -> User:
    from src.api.main import get_current_user
    from fastapi.security import HTTPAuthorizationCredentials
    auth_header = request.headers.get("authorization", "")
    credentials = None
    if auth_header.startswith("Bearer "):
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=auth_header[7:])
    return get_current_user(request=request, credentials=credentials, db=db)


@router.post("/voice-session")
def start_voice_session(request: Request, db: Session = Depends(get_db)):
    current_user = _resolve_user(request, db)
    if current_user.role != "CLAIMANT":
        raise HTTPException(status_code=403, detail="Only claimant accounts can start a claim intake session.")
    ticket_id = f"CLAIM-{uuid.uuid4().hex[:8].upper()}"
    claim = Claim(ticket_id=ticket_id, claimant_id=current_user.id, customer_id=str(current_user.id), input_mode="voice", status="draft", conversation_status="not_started")
    db.add(claim)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to create voice session")
        raise HTTPException(status_code=500, detail="Failed to create claim session.")
    return {"ticket_id": ticket_id, "initial_message": "Please tell me what happened. You can describe the incident in your own words, and I'll collect the details I need."}


@router.post("/intake")
async def intake_claim(payload: ClaimIntakeRequest, request: Request, db: Session = Depends(get_db)):
    current_user = _resolve_user(request, db)
    if current_user.role != "CLAIMANT":
        raise HTTPException(status_code=403, detail="Only claimant accounts can submit claim intake information.")

    claim = None
    user_id = str(current_user.id)
    if payload.ticket_id:
        claim = db.query(Claim).filter(Claim.ticket_id == payload.ticket_id).first()
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found for the given ticket_id.")
        enforce_claim_ownership(claim, current_user)
        if claim.status == "verified":
            state = dict(claim.pipeline_state or {})
            return {"ticket_id": claim.ticket_id, "extracted_data": state.get("extracted_data", {}), "missing_fields": state.get("missing_fields", []), "awaiting_confirmation": False, "message": "This claim has already been verified."}

    ticket_id = payload.ticket_id or f"CLAIM-{uuid.uuid4().hex[:8].upper()}"
    if claim is None:
        claim = Claim(ticket_id=ticket_id, claimant_id=current_user.id, customer_id=user_id, input_mode=payload.input_mode, status="draft")
        db.add(claim)
        db.flush()

    turn_num = db.query(ConversationTurn).filter(ConversationTurn.claim_id == claim.id).count() + 1
    try:
        result = await process_claimant_turn(db, claim, payload.claim_text, payload.input_mode, turn_num)
    except Exception as exc:
        logger.exception("intake_claim: conversation turn processing failed")
        raise HTTPException(status_code=503, detail="The claim processing pipeline encountered an error. Please try again in a moment.") from exc

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
    return {"ticket_id": claim.ticket_id, "status": claim.status, "extracted_data": state.get("extracted_data", {}), "policy_verification": state.get("policy_verification"), "message": "Claim already verified.", "_cached": cached}


def _verification_failure_message(reason: str) -> str:
    return {
        "policy_not_found": "We couldn't find a policy with that number. Please double-check and try again.",
        "ownership_mismatch": "This policy isn't linked to your account. Please verify the policy number.",
        "policy_type_mismatch": "The policy type does not match the insurance type described for this claim. Please check the policy number or claim type.",
        "policy_inactive": "This policy is currently inactive.",
        "policy_not_active_on_event_date": "This policy wasn't active on the date you reported. Please check the incident date and policy number.",
        "missing_event_date": "We need a valid incident date to verify your policy.",
        "invalid_event_date": "The incident date couldn't be understood. Please provide it again.",
        "no_policy_id": "We need your policy number to verify this claim.",
    }.get(reason, "We couldn't verify your policy. A specialist will follow up.")


@router.post("/{ticket_id}/verify")
def verify_claim(ticket_id: str, request: Request, db: Session = Depends(get_db)):
    current_user = _resolve_user(request, db)
    if current_user.role != "CLAIMANT":
        raise HTTPException(status_code=403, detail="Only claimant accounts can verify claims.")
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found for the given ticket_id.")
    enforce_claim_ownership(claim, current_user)

    state = dict(claim.pipeline_state or {})
    missing = state.get("missing_fields", [])
    if missing:
        raise HTTPException(status_code=400, detail=f"Cannot verify claim: missing mandatory fields {missing}.")
    if claim.status == "verified":
        return _verify_response(claim, state, cached=True)

    extracted = state.get("extracted_data", {})
    verification = verify_policy_for_claim(
        policy_id=extracted.get("policy_id"),
        event_date_str=extracted.get("event_date"),
        claimant_user_id=str(current_user.id),
        db=db,
        insurance_type=extracted.get("insurance_type"),
    )
    if verification["valid"]:
        claim.status = "verified"
        claim.conversation_status = "verified"
        message = "Your claim details have been verified."
    else:
        claim.status = "verification_failed"
        claim.conversation_status = "verification_failed"
        message = _verification_failure_message(verification.get("reason", ""))
    state["policy_verification"] = verification
    claim.pipeline_state = state
    db.commit()
    return {"ticket_id": claim.ticket_id, "status": claim.status, "extracted_data": extracted, "policy_verification": verification, "message": message}


@router.get("/{ticket_id}/conversation")
def get_conversation_history(ticket_id: str, request: Request, db: Session = Depends(get_db)):
    current_user = _resolve_user(request, db)
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found for the given ticket_id.")
    enforce_claim_ownership(claim, current_user)
    turns = db.query(ConversationTurn).filter(ConversationTurn.claim_id == claim.id).order_by(ConversationTurn.turn_number, ConversationTurn.created_at).all()
    return [{"turn": t.turn_number, "speaker": t.speaker, "text": t.text, "created_at": t.created_at.isoformat() if t.created_at else None} for t in turns]


@router.get("/{ticket_id}")
def get_claim(ticket_id: str, request: Request, db: Session = Depends(get_db)):
    current_user = _resolve_user(request, db)
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found for the given ticket_id.")
    enforce_claim_ownership(claim, current_user)
    state = claim.pipeline_state or {}
    return {"ticket_id": claim.ticket_id, "status": claim.status, "conversation_status": claim.conversation_status, "insurance_type": claim.insurance_type, "event_date": str(claim.event_date) if claim.event_date else None, "event_description": claim.event_description, "estimated_claim_amount": float(claim.estimated_claim_amount) if claim.estimated_claim_amount is not None else None, "extracted_data": state.get("extracted_data") or {}, "missing_fields": state.get("missing_fields") or [], "response_message": state.get("response_message"), "created_at": claim.created_at.isoformat() if claim.created_at else None}


@router.get("")
def list_claims(request: Request, page: int = 1, page_size: int = 20, db: Session = Depends(get_db)):
    current_user = _resolve_user(request, db)
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    user_id = str(current_user.id)
    query = db.query(Claim).filter((Claim.claimant_id == current_user.id) | (Claim.customer_id == user_id)).order_by(Claim.created_at.desc())
    total = query.count()
    claims = query.offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [{"id": str(c.id), "ticket_id": c.ticket_id, "insurance_type": c.insurance_type, "status": c.status, "conversation_status": c.conversation_status, "extracted_data": (c.pipeline_state or {}).get("extracted_data") or {}, "created_at": c.created_at.isoformat() if c.created_at else None} for c in claims], "total": total, "page": page, "page_size": page_size}
