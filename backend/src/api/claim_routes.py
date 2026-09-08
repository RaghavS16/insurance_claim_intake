"""
Claim intake and management API routes.

Phase 1 owns the persistent claimant conversation: draft sessions can be
resumed after navigation, browser refresh, or a disconnected voice socket.
"""
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.config import settings
from src.database.session import get_db
from src.database.models import Claim, ConversationTurn, User
from src.api.voice_ws import process_claimant_turn
from src.utils.authorization import enforce_claim_ownership
from src.utils.logger import app_logger
from src.utils.auth import verify_token
from src.agents.policy_check import verify_policy_for_claim

logger = app_logger
router = APIRouter(prefix="/api/v1/claims", tags=["Claims"])

class ClaimIntakeRequest(BaseModel):
    claim_text: str = Field(..., min_length=1, max_length=5000)
    input_mode: str = Field("text")
    ticket_id: Optional[str] = None

class ClaimConfirmRequest(BaseModel):
    confirmed: bool = Field(True)

class VoiceSessionRequest(BaseModel):
    policy_number: Optional[str] = None

class TextTurnRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)

class UpdateClaimRequest(BaseModel):
    policy_id: Optional[str] = None
    insurance_type: Optional[str] = None
    event_date: Optional[str] = None
    event_description: Optional[str] = None
    event_location: Optional[str] = None
    estimated_claim_amount: Optional[float] = None
    extracted_data: Optional[Dict[str, Any]] = None


def _resolve_user(request: Request, db: Session) -> User:
    """Resolve the authenticated claimant for both HTTP and test requests."""
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else None
    uid = None
    if token:
        payload = verify_token(token)
        uid = payload.get("sub") if payload else None
    elif settings.ENVIRONMENT == "test":
        uid = request.headers.get("X-User-ID")
    if not uid:
        raise HTTPException(status_code=401, detail="Authentication required.")
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=401, detail="Authenticated user not found.")
    return user


def _claim_payload(claim: Claim) -> Dict[str, Any]:
    state = dict(getattr(claim, "pipeline_state", None) or {})
    return {
        "ticket_id": claim.ticket_id,
        "status": claim.status,
        "conversation_status": claim.conversation_status,
        "extracted_data": state.get("extracted_data") or {},
        "missing_fields": state.get("missing_fields") or [],
        "field_status": state.get("field_status") or {},
        "awaiting_confirmation": bool(state.get("awaiting_confirmation")),
        "confirmed": bool(state.get("confirmed")),
        "created_at": claim.created_at.isoformat() if claim.created_at else None,
        "updated_at": claim.updated_at.isoformat() if claim.updated_at else None,
    }


def _conversation_payload(db: Session, claim: Claim) -> List[Dict[str, Any]]:
    turns = (
        db.query(ConversationTurn)
        .filter(ConversationTurn.claim_id == claim.id)
        .order_by(ConversationTurn.turn_number, ConversationTurn.created_at, ConversationTurn.id)
        .all()
    )
    return [
        {
            "turn": t.turn_number,
            "speaker": "user" if t.speaker in {"user", "claimant"} else "agent",
            "text": t.text,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in turns
    ]


@router.post("/voice-session")
def start_voice_session(request: Request, payload: Optional[VoiceSessionRequest] = None, db: Session = Depends(get_db)):
    """Create a draft only when no resumable draft exists; otherwise resume it."""
    current_user = _resolve_user(request, db)
    resumable = (
        db.query(Claim)
        .filter(Claim.claimant_id == current_user.id)
        .filter(Claim.status.in_(["draft", "pending_confirmation"]))
        .order_by(Claim.updated_at.desc())
        .first()
    )
    if resumable:
        return {
            **_claim_payload(resumable),
            "resumed": True,
            "initial_message": "Welcome back. We can continue from where we left off.",
            "conversation": _conversation_payload(db, resumable),
        }

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
        conversation_status="collecting",
        pipeline_state={"extracted_data": init_extracted} if init_extracted else {},
    )
    db.add(claim)
    try:
        db.commit(); db.refresh(claim)
    except Exception:
        db.rollback(); logger.exception("Failed to create voice session")
        raise HTTPException(status_code=500, detail="Failed to create claim session.")
    return {**_claim_payload(claim), "resumed": False, "initial_message": "Tell me what happened, in your own words. I'll collect the details as we go.", "conversation": []}


@router.get("/active")
def get_active_claim(request: Request, db: Session = Depends(get_db)):
    """Return the claimant's newest resumable draft and its complete chat history."""
    current_user = _resolve_user(request, db)
    claim = (
        db.query(Claim)
        .filter(Claim.claimant_id == current_user.id)
        .filter(Claim.status.in_(["draft", "pending_confirmation"]))
        .order_by(Claim.updated_at.desc())
        .first()
    )
    if not claim:
        return {"active": False}
    return {"active": True, **_claim_payload(claim), "conversation": _conversation_payload(db, claim)}


@router.get("/{ticket_id}/conversation")
def get_conversation_history(ticket_id: str, request: Request, db: Session = Depends(get_db)):
    current_user = _resolve_user(request, db)
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim: raise HTTPException(status_code=404, detail="Claim not found for the given ticket_id.")
    enforce_claim_ownership(claim, current_user)
    return _conversation_payload(db, claim)


@router.get("/{ticket_id}")
def get_claim(ticket_id: str, request: Request, db: Session = Depends(get_db)):
    current_user = _resolve_user(request, db)
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim: raise HTTPException(status_code=404, detail="Claim not found for the given ticket_id.")
    enforce_claim_ownership(claim, current_user)
    return _claim_payload(claim)


@router.post("/intake")
async def intake_claim(payload: ClaimIntakeRequest, request: Request, db: Session = Depends(get_db)):
    current_user = _resolve_user(request, db)
    claim = None
    if payload.ticket_id:
        claim = db.query(Claim).filter(Claim.ticket_id == payload.ticket_id).first()
        if not claim: raise HTTPException(status_code=404, detail="Claim not found for the given ticket_id.")
        enforce_claim_ownership(claim, current_user)
    if claim is None:
        claim = Claim(ticket_id=f"CLAIM-{uuid.uuid4().hex[:8].upper()}", claimant_id=current_user.id, customer_id=str(current_user.id), input_mode=payload.input_mode, status="draft")
        db.add(claim); db.flush()
    prior_turns = db.query(ConversationTurn).filter(ConversationTurn.claim_id == claim.id).count()
    try:
        result = await process_claimant_turn(db, claim, payload.claim_text, payload.input_mode, prior_turns // 2 + 1)
    except Exception as exc:
        logger.exception("Claim conversation processing failed")
        raise HTTPException(status_code=503, detail=f"Claim processing temporarily unavailable ({type(exc).__name__}).")
    return {**_claim_payload(claim), "message": result.get("next_question") or result.get("message", "")}


@router.post("/{ticket_id}/text-turn")
async def claim_text_turn(ticket_id: str, payload: TextTurnRequest, request: Request, db: Session = Depends(get_db)):
    current_user = _resolve_user(request, db)
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim: raise HTTPException(status_code=404, detail="Claim not found for the given ticket_id.")
    enforce_claim_ownership(claim, current_user)
    prior_turns = db.query(ConversationTurn).filter(ConversationTurn.claim_id == claim.id).count()
    try:
        result = await process_claimant_turn(db, claim, payload.text, "text", prior_turns // 2 + 1)
    except Exception as exc:
        logger.exception("Text turn processing failed")
        raise HTTPException(status_code=503, detail=f"Claim processing temporarily unavailable ({type(exc).__name__}).")
    return {**_claim_payload(claim), "agent_message": result.get("next_question") or result.get("message", "")}


def _verification_failure_message(reason: str) -> str:
    return {
        "policy_not_found": "I couldn't find that policy number. Please double-check it.",
        "policy_not_linked": "Please link this policy to your account before filing a claim.",
        "ownership_mismatch": "That policy isn't linked to your account.",
        "insurance_type_mismatch": "That policy type doesn't match this claim.",
        "policy_inactive": "That policy is currently inactive.",
        "policy_not_active_on_event_date": "The policy wasn't active on the incident date.",
        "missing_event_date": "I need the incident date to verify the policy.",
        "invalid_event_date": "I couldn't understand that incident date.",
        "no_policy_id": "I need your policy number to verify the claim.",
    }.get(reason, "I couldn't verify the policy. A claims specialist will need to review it.")


@router.post("/{ticket_id}/verify")
def verify_claim(ticket_id: str, request: Request, db: Session = Depends(get_db)):
    current_user = _resolve_user(request, db)
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim: raise HTTPException(status_code=404, detail="Claim not found for the given ticket_id.")
    enforce_claim_ownership(claim, current_user)
    state = dict(claim.pipeline_state or {})
    missing = state.get("missing_fields", [])
    if missing: raise HTTPException(status_code=400, detail=f"Cannot verify claim: missing mandatory fields {missing}.")
    extracted = state.get("extracted_data", {})
    verification = verify_policy_for_claim(policy_id=extracted.get("policy_id"), event_date_str=extracted.get("event_date"), claimant_user_id=str(current_user.id), insurance_type=extracted.get("insurance_type"), db=db, claim_id=claim.id)
    if verification["valid"]:
        claim.status = "verified"; claim.conversation_status = "verified"
    else:
        claim.status = "verification_failed"; claim.conversation_status = "verification_failed"
    state["policy_verification"] = verification; claim.pipeline_state = state
    db.commit()
    return {**_claim_payload(claim), "policy_verification": verification, "message": "Claim details verified." if verification["valid"] else _verification_failure_message(verification.get("reason", ""))}


@router.post("/{ticket_id}/confirm")
async def confirm_claim(ticket_id: str, request: Request, payload: Optional[ClaimConfirmRequest] = None, db: Session = Depends(get_db)):
    current_user = _resolve_user(request, db)
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim: raise HTTPException(status_code=404, detail="Claim not found for the given ticket_id.")
    enforce_claim_ownership(claim, current_user)
    state = dict(claim.pipeline_state or {}); extracted = dict(state.get("extracted_data") or {})
    if not state.get("confirmed"):
        raise HTTPException(status_code=400, detail="Please confirm the claim details in the conversation before submitting.")
    missing = state.get("missing_fields") or []
    if missing: raise HTTPException(status_code=400, detail=f"Cannot submit claim: missing mandatory fields {missing}.")
    verification = verify_policy_for_claim(policy_id=extracted.get("policy_id"), event_date_str=extracted.get("event_date"), claimant_user_id=str(current_user.id), insurance_type=extracted.get("insurance_type"), db=db, claim_id=claim.id)
    if not verification.get("valid"):
        state["policy_verification"] = verification; claim.pipeline_state = state; db.commit()
        raise HTTPException(status_code=400, detail=f"Claim verification failed: {_verification_failure_message(verification.get('reason', ''))}")
    claim.status = "submitted"; claim.conversation_status = "confirmed"; state["policy_verification"] = verification; claim.pipeline_state = state
    db.commit()
    return {**_claim_payload(claim), "policy_verification": verification, "message": f"Claim #{ticket_id} has been verified, confirmed, and submitted."}


@router.patch("/{ticket_id}")
def update_claim_details(ticket_id: str, payload: UpdateClaimRequest, request: Request, db: Session = Depends(get_db)):
    current_user = _resolve_user(request, db)
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim: raise HTTPException(status_code=404, detail="Claim not found for the given ticket_id.")
    enforce_claim_ownership(claim, current_user)
    state = dict(claim.pipeline_state or {}); extracted = dict(state.get("extracted_data") or {})
    if payload.extracted_data: extracted.update(payload.extracted_data)
    for field in ("policy_id", "insurance_type", "event_date", "event_description", "event_location", "estimated_claim_amount"):
        value = getattr(payload, field)
        if value is not None: extracted[field] = value
    claim.pipeline_state = {**state, "extracted_data": extracted}; claim.insurance_type = extracted.get("insurance_type"); claim.event_description = extracted.get("event_description"); claim.event_location = extracted.get("event_location"); claim.estimated_claim_amount = extracted.get("estimated_claim_amount")
    if extracted.get("event_date"):
        from datetime import datetime
        try: claim.event_date = datetime.strptime(str(extracted["event_date"]), "%Y-%m-%d").date()
        except ValueError: pass
    db.commit(); db.refresh(claim)
    return _claim_payload(claim)


@router.post("/message/{ticket_id}")
async def send_claim_message(ticket_id: str, payload: Dict[str, Any], request: Request, db: Session = Depends(get_db)):
    text = payload.get("message") or payload.get("text") or ""
    return await claim_text_turn(ticket_id, TextTurnRequest(text=text), request, db)
