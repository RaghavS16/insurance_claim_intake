"""
Claim intake and management API routes.

Phase 1 owns the persistent claimant conversation: draft sessions can be
resumed after navigation, browser refresh, or a disconnected voice socket.
"""
import uuid
import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.config import settings
from src.database.session import get_db
from src.database.models import Claim, ConversationTurn, User
from src.api.voice_ws import process_claimant_turn
from src.utils.authorization import enforce_claim_ownership
from src.utils.logger import app_logger
from src.agents.policy_check import verify_policy_for_claim
from src.agents.dynamic_requirements import missing_evidence
from src.database.models import Adjuster
from src.database.hardening_models import ClaimEvidence, ClaimRequirement
from src.evidence.verifier import verify_evidence
from src.storage.s3 import put_bytes
from src.database.claim_workflow import assign_claim, transition_claim
from src.api.deps import get_current_user, resolve_bearer_user

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
    """Resolve the authenticated claimant. Delegates to the shared revocation-aware
    implementation in deps.resolve_bearer_user (supports JWT Bearer + test X-User-ID)."""
    return resolve_bearer_user(request, db, ["CLAIMANT", "ADMIN", "ADJUSTER"])


def _claim_payload(claim: Claim) -> Dict[str, Any]:
    state = dict(getattr(claim, "pipeline_state", None) or {})
    return {
        "id": str(claim.id) if claim.id else None,
        "ticket_id": claim.ticket_id,
        "status": claim.status,
        "conversation_status": claim.conversation_status,
        "insurance_type": claim.insurance_type,
        "event_date": claim.event_date.isoformat() if claim.event_date else None,
        "event_description": claim.event_description,
        "event_location": claim.event_location,
        "estimated_claim_amount": float(claim.estimated_claim_amount) if claim.estimated_claim_amount is not None else None,
        "extracted_data": state.get("extracted_data") or {},
        "missing_fields": state.get("missing_fields") or [],
        "dynamic_requirements": state.get("dynamic_requirements") or [],
        "dynamic_missing": state.get("dynamic_missing") or [],
        "missing_evidence": state.get("missing_evidence") or [],
        "evidence": state.get("evidence") or [],
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


@router.get("")
@router.get("/")
def list_user_claims(request: Request, db: Session = Depends(get_db)):
    """List all claims belonging to the authenticated claimant, newest first."""
    current_user = _resolve_user(request, db)
    claims = (
        db.query(Claim)
        .filter(Claim.claimant_id == current_user.id)
        .order_by(Claim.updated_at.desc())
        .all()
    )
    result = []
    for c in claims:
        payload = _claim_payload(c)
        last_turn = (
            db.query(ConversationTurn)
            .filter(ConversationTurn.claim_id == c.id)
            .order_by(ConversationTurn.turn_number.desc(), ConversationTurn.created_at.desc())
            .first()
        )
        turn_count = db.query(ConversationTurn).filter(ConversationTurn.claim_id == c.id).count()
        payload["last_message"] = last_turn.text if last_turn else None
        payload["last_message_speaker"] = last_turn.speaker if last_turn else None
        payload["turn_count"] = turn_count
        result.append(payload)
    return {"items": result, "total": len(result)}


@router.post("/new-session")
def create_new_claim_session(request: Request, payload: Optional[VoiceSessionRequest] = None, db: Session = Depends(get_db)):
    """Force creation of a brand new claim session regardless of existing drafts."""
    current_user = _resolve_user(request, db)
    ticket_id = f"CLAIM-{uuid.uuid4().hex[:8].upper()}"
    init_extracted: Dict[str, Any] = {}
    if payload and payload.policy_number:
        init_extracted["policy_id"] = payload.policy_number.strip().upper()
    claim = Claim(
        ticket_id=ticket_id,
        claimant_id=current_user.id,
        customer_id=str(current_user.id),
        input_mode="text",
        status="draft",
        conversation_status="collecting",
        pipeline_state={"extracted_data": init_extracted} if init_extracted else {},
    )
    db.add(claim)
    try:
        db.commit()
        db.refresh(claim)
    except Exception:
        db.rollback()
        logger.exception("Failed to create new claim session")
        raise HTTPException(status_code=500, detail="Failed to create claim session.")
    return {
        **_claim_payload(claim),
        "resumed": False,
        "initial_message": "Tell me what happened, in your own words. I'll collect the details as we go.",
        "conversation": [],
    }


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


@router.get("/{ticket_id}/export")
def export_claim_transcript(ticket_id: str, request: Request, db: Session = Depends(get_db)):
    """Export formatted conversation transcript and extracted claim dossier."""
    current_user = _resolve_user(request, db)
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found for the given ticket_id.")
    enforce_claim_ownership(claim, current_user)
    turns = _conversation_payload(db, claim)
    payload = _claim_payload(claim)
    
    formatted_lines = [
        f"=== INSURANCE CLAIM INTAKE DOSSIER ===",
        f"Ticket ID: #{claim.ticket_id}",
        f"Status: {claim.status.upper()}",
        f"Insurance Type: {claim.insurance_type or 'Unspecified'}",
        f"Incident Date: {claim.event_date or 'Unspecified'}",
        f"Incident Location: {claim.event_location or 'Unspecified'}",
        f"Estimated Amount: ₹{claim.estimated_claim_amount:,.2f}" if claim.estimated_claim_amount is not None else "Estimated Amount: Unspecified",
        f"Description: {claim.event_description or 'Unspecified'}",
        f"Created At: {claim.created_at}",
        f"\n=== CONVERSATION TRANSCRIPT ({len(turns)} messages) ===",
    ]
    for t in turns:
        speaker_tag = "CLAIMANT" if t["speaker"] == "user" else "ASSISTANT"
        ts = f" [{t['created_at']}]" if t.get("created_at") else ""
        formatted_lines.append(f"Turn {t['turn']} | {speaker_tag}{ts}:\n{t['text']}\n")
        
    return {
        "claim": payload,
        "turns": turns,
        "formatted_text": "\n".join(formatted_lines),
    }


@router.delete("/{ticket_id}")
def delete_claim(ticket_id: str, request: Request, db: Session = Depends(get_db)):
    """Allow claimant to discard their own draft session."""
    current_user = _resolve_user(request, db)
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found.")
    enforce_claim_ownership(claim, current_user)
    if claim.status not in ("draft", "pending_confirmation"):
        raise HTTPException(status_code=400, detail="Only draft claims can be deleted.")
    
    # Delete associated conversation turns first
    db.query(ConversationTurn).filter(ConversationTurn.claim_id == claim.id).delete()
    db.delete(claim)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to delete claim session.")
    return {"message": f"Claim #{ticket_id} and history removed.", "success": True}


@router.get("/{ticket_id}")
def get_claim(ticket_id: str, request: Request, db: Session = Depends(get_db)):
    current_user = _resolve_user(request, db)
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim: raise HTTPException(status_code=404, detail="Claim not found for the given ticket_id.")
    enforce_claim_ownership(claim, current_user)
    return {**_claim_payload(claim), "conversation": _conversation_payload(db, claim)}


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
    if missing:
        verification = {"valid": False, "reason": "missing_mandatory_fields", "missing_fields": missing}
        claim.status = "verification_failed"
        claim.conversation_status = "verification_failed"
        state["policy_verification"] = verification
        claim.pipeline_state = state
        db.commit()
        return {**_claim_payload(claim), "policy_verification": verification, "message": _verification_failure_message("missing_mandatory_fields")}
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
    dynamic_missing = state.get("dynamic_missing") or []
    if state.get("rag_status") not in {None, "OK", "NO_INSURANCE_TYPE"}:
        raise HTTPException(status_code=503, detail="Claim-specific policy requirements are temporarily unavailable. Please retry before submitting.")
    if missing: raise HTTPException(status_code=400, detail=f"Cannot submit claim: missing mandatory fields {missing}.")
    if dynamic_missing: raise HTTPException(status_code=400, detail="Cannot submit claim: claim-specific information is still incomplete.")
    missing_evidence_items = missing_evidence(state)
    if missing_evidence_items: raise HTTPException(status_code=400, detail="Cannot submit claim: required evidence has not been uploaded.")
    verification = verify_policy_for_claim(policy_id=extracted.get("policy_id"), event_date_str=extracted.get("event_date"), claimant_user_id=str(current_user.id), insurance_type=extracted.get("insurance_type"), db=db, claim_id=claim.id)
    if not verification.get("valid"):
        state["policy_verification"] = verification; claim.pipeline_state = state; db.commit()
        raise HTTPException(status_code=400, detail=f"Claim verification failed: {_verification_failure_message(verification.get('reason', ''))}")
    # Assignment is transactional and recorded as a durable work item.
    state["policy_verification"] = verification
    try:
        if claim.status != "verified":
            transition_claim(db, claim, "verified", str(current_user.id), "claimant confirmation and policy verification")
        assigned = assign_claim(db, claim, str(current_user.id))
        transition_claim(db, claim, "assigned", str(current_user.id), "automatic assignment")
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc))
    state["assigned_adjuster_id"] = str(assigned.id)
    state["assigned_adjuster_name"] = assigned.name
    claim.conversation_status = "confirmed"
    claim.pipeline_state = state
    db.commit()
    return {**_claim_payload(claim), "policy_verification": verification,
            "assigned_adjuster": {"id": str(assigned.id), "name": assigned.name, "specialization": assigned.specialization},
            "message": f"Claim #{ticket_id} has been verified, confirmed, and assigned to {assigned.name}."}




@router.post("/{ticket_id}/evidence")
async def upload_claim_evidence(ticket_id: str, request: Request, file: UploadFile = File(...), evidence_key: Optional[str] = None, db: Session = Depends(get_db)):
    """Store claimant evidence in S3 and verify it against the dynamic requirement.

    Upload presence never satisfies a requirement. The file must be semantically
    verified as the requested evidence before missing_evidence() considers it complete.
    """
    current_user = _resolve_user(request, db)
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found.")
    enforce_claim_ownership(claim, current_user)
    if claim.status not in ("draft", "pending_confirmation", "verified"):
        raise HTTPException(status_code=400, detail="Evidence can only be uploaded while intake is in progress.")
    if not file.filename:
        raise HTTPException(status_code=400, detail="A file is required.")

    allowed = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".doc", ".docx", ".txt"}
    from pathlib import Path
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail="Unsupported evidence format.")
    content = await file.read()
    if len(content) > settings.MAX_EVIDENCE_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Evidence file is too large.")

    state = dict(claim.pipeline_state or {})
    evidence = list(state.get("evidence") or [])
    outstanding = missing_evidence(state)
    if evidence_key:
        requested = next((r for r in outstanding if str(r.get("key")) == str(evidence_key)), None)
        if requested is None:
            raise HTTPException(status_code=400, detail="That evidence requirement is not currently outstanding.")
    elif outstanding:
        requested = outstanding[0]
        evidence_key = requested.get("key")
    else:
        raise HTTPException(status_code=400, detail="There are no outstanding evidence requirements for this claim.")

    # Resolve the durable requirement when available so adjusters can trace evidence
    # back to the exact generated requirement and its provenance.
    requirement_row = None
    try:
        requirement_row = db.query(ClaimRequirement).filter(
            ClaimRequirement.claim_id == claim.id,
            ClaimRequirement.requirement_key == str(evidence_key),
        ).first()
    except Exception:
        logger.debug("Durable claim requirement lookup unavailable for %s", ticket_id)

    claim_context = {
        "ticket_id": claim.ticket_id,
        "insurance_type": state.get("extracted_data", {}).get("insurance_type"),
        "event_date": state.get("extracted_data", {}).get("event_date"),
        "event_location": state.get("extracted_data", {}).get("event_location"),
        "claimant_name": state.get("extracted_data", {}).get("claimant_name"),
        "event_description": state.get("extracted_data", {}).get("event_description"),
    }
    try:
        s3 = put_bytes(
            content,
            prefix=f"{settings.S3_EVIDENCE_PREFIX}/{ticket_id}/evidence",
            filename=file.filename,
            content_type=file.content_type or "application/octet-stream",
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Evidence storage is unavailable: {exc}")

    analysis = await asyncio.to_thread(
        verify_evidence,
        content=content,
        filename=file.filename,
        requested_evidence=requested,
        claim_context=claim_context,
    )
    verification_status = str(analysis.get("verification_status", "REVIEW_REQUIRED")).upper()
    item_id = str(uuid.uuid4())
    item = {
        "id": item_id,
        "name": file.filename,
        "s3_uri": s3["uri"],
        "s3_key": s3["key"],
        "evidence_key": evidence_key,
        "requirement_id": str(requirement_row.id) if requirement_row else None,
        "content_type": file.content_type or "application/octet-stream",
        "size": len(content),
        "status": verification_status.lower(),
        "review": "complete" if verification_status in {"VERIFIED", "REJECTED", "UNREADABLE"} else "pending",
        "verification_status": verification_status,
        "verification_confidence": analysis.get("confidence"),
        "detected_document_type": analysis.get("detected_document_type"),
        "requested_evidence_type": analysis.get("requested_evidence_type") or requested.get("evidence_type"),
        "verification_reason": analysis.get("reason"),
        "claim_consistency": analysis.get("claim_consistency"),
        "consistency_notes": analysis.get("consistency_notes") or [],
        "extracted_fields": analysis.get("extracted_fields") or {},
        "sha256": analysis.get("sha256"),
    }
    evidence.append(item)
    state["evidence"] = evidence
    state["missing_evidence"] = missing_evidence(state)
    state["last_evidence_verification"] = {
        "evidence_id": item_id,
        "requirement_key": evidence_key,
        **analysis,
    }
    claim.pipeline_state = state

    db_evidence = ClaimEvidence(
        id=item_id,
        claim_id=claim.id,
        uploaded_by=current_user.id,
        requirement_id=str(requirement_row.id) if requirement_row else None,
        object_key=s3["key"],
        original_filename=file.filename,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
        sha256=analysis.get("sha256"),
        status=verification_status.lower(),
        document_type=analysis.get("detected_document_type"),
        verification_status=verification_status,
        verification_confidence=analysis.get("confidence"),
        detected_document_type=analysis.get("detected_document_type"),
        requested_evidence_type=analysis.get("requested_evidence_type") or requested.get("evidence_type"),
        analysis_json=analysis,
    )
    db.add(db_evidence)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Evidence verification result could not be persisted.")

    if verification_status == "VERIFIED":
        message = f"Your {requested.get('label') or requested.get('key') or 'evidence'} was verified successfully."
    elif verification_status == "REJECTED":
        message = analysis.get("reason") or "This file does not match the requested evidence. Please upload the correct document."
    elif verification_status == "UNREADABLE":
        message = analysis.get("reason") or "I couldn't read this file reliably. Please upload a clearer copy."
    else:
        message = analysis.get("reason") or "I couldn't verify this evidence automatically. It remains pending review."

    return {
        "success": True,
        "message": message,
        "evidence": item,
        "evidence_items": evidence,
        "missing_evidence": state["missing_evidence"],
    }

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
