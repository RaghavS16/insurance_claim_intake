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
from src.database.models import Claim, Document, ConversationTurn, User
from src.agents.graph import build_conversation_graph, build_evaluation_graph
from src.agents.evaluation import DOCUMENT_REQUIREMENTS
from src.api.voice_ws import process_claimant_turn
from src.utils.authorization import enforce_claim_ownership
from src.utils.validators import sanitize_filename
from src.utils.logger import app_logger

logger = app_logger
router = APIRouter(prefix="/api/v1/claims", tags=["Claims"])

# File upload constraints
MAX_UPLOAD_SIZE_BYTES = settings.MAX_UPLOAD_SIZE_BYTES
MIN_UPLOAD_SIZE_BYTES = 100
ALLOWED_MIME_TYPES = {
    "image/jpeg", "image/png", "image/webp", "image/gif",
    "application/pdf",
}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf"}


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
    """Confirm collected claim details and submit structured claim."""
    current_user = _resolve_user(request, db)
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found for the given ticket_id.")
    enforce_claim_ownership(claim, current_user)

    state = dict(getattr(claim, "pipeline_state", None) or {})

    # Check for missing mandatory fields
    missing = state.get("missing_fields", [])
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot confirm claim: missing mandatory fields {missing}. Complete intake first.",
        )

    # Idempotency check: if already evaluated, return existing result
    if claim.status == "evaluated" and claim.final_decision is not None:
        return {
            "ticket_id": claim.ticket_id,
            "status": claim.status,
            "final_decision": claim.final_decision,
            "closure_status": claim.closure_status,
            "coverage_eligible": state.get("coverage_eligible"),
            "deductible_amount": state.get("deductible_amount"),
            "payout_amount": state.get("payout_amount"),
            "assigned_adjuster": state.get("assigned_adjuster"),
            "response_message": state.get("response_message"),
            "spoken_response": state.get("spoken_response"),
            "fraud_score": claim.fraud_score,
            "fraud_flags": claim.fraud_flags or [],
            "_cached": True,
        }

    # Fetch uploaded document types
    docs = db.query(Document).filter(Document.claim_id == claim.id).all()
    uploaded_doc_types = [d.document_type for d in docs]

    # Set to submitted stage before running evaluation
    claim.conversation_status = "submitted"  # type: ignore
    db.commit()

    eval_input = {
        **state,
        "ticket_id": ticket_id,
        "confirmed": True,
        "conversation_status": "submitted",
        "uploaded_documents": uploaded_doc_types,
    }

    try:
        eval_graph = build_evaluation_graph(db=db)
        eval_result = eval_graph.invoke(eval_input)
    except Exception as exc:
        logger.exception("Evaluation pipeline failed for claim %s", ticket_id)
        raise HTTPException(
            status_code=500,
            detail="Claim evaluation failed. Please try again or contact support.",
        )

    # Persist evaluation outcomes
    claim.status = "evaluated"  # type: ignore
    claim.conversation_status = "completed"  # type: ignore
    eval_result["conversation_status"] = "completed"
    if eval_result.get("final_decision") is not None:
        claim.final_decision = eval_result["final_decision"]
        claim.final_decision = eval_result["final_decision"]  # type: ignore
    if eval_result.get("closure_status") is not None:
        claim.closure_status = eval_result["closure_status"]  # type: ignore
    if eval_result.get("fraud_score") is not None:
        claim.fraud_score = eval_result["fraud_score"]  # type: ignore
    claim.fraud_flags = eval_result.get("fraud_flags", [])  # type: ignore
    claim.pipeline_state = dict(eval_result)  # type: ignore

    adj = eval_result.get("assigned_adjuster")
    if adj and adj.get("id") not in (None, "UNASSIGNED", "ADJ-DEFAULT"):
        claim.assigned_adjuster_id = adj.get("id")  # type: ignore

    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to persist evaluation results for claim %s", ticket_id)
        raise HTTPException(status_code=500, detail="Failed to save evaluation results.")

    return {
        "ticket_id": claim.ticket_id,
        "status": claim.status,
        "final_decision": claim.final_decision,
        "closure_status": claim.closure_status,
        "coverage_eligible": eval_result.get("coverage_eligible"),
        "deductible_amount": eval_result.get("deductible_amount"),
        "payout_amount": eval_result.get("payout_amount"),
        "assigned_adjuster": eval_result.get("assigned_adjuster"),
        "response_message": eval_result.get("response_message"),
        "spoken_response": eval_result.get("spoken_response"),
        "fraud_score": claim.fraud_score,
        "fraud_flags": eval_result.get("fraud_flags"),
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
        "final_decision": claim.final_decision,
        "closure_status": claim.closure_status,
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
            "final_decision": c.final_decision,
            "closure_status": c.closure_status,
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
# Document Upload
# ---------------------------------------------------------------------------
@router.post("/{ticket_id}/documents")
async def upload_document(
    ticket_id: str,
    request: Request,
    document_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload supporting claim evidence document with actual file-to-disk persistence."""
    current_user = _resolve_user(request, db)
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found for the given ticket_id.")
    enforce_claim_ownership(claim, current_user)

    # Read file content with size check
    content = await file.read()
    if len(content) < MIN_UPLOAD_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="Uploaded file is empty or too small.")
    if len(content) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds {MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)}MB limit.",
        )

    # Validate document type
    ctype = str((claim.pipeline_state or {}).get("extracted_data", {}).get("claim_type") or claim.claim_type or "motor")
    valid_doc_types = DOCUMENT_REQUIREMENTS.get(ctype, ["damage_photo", "repair_estimate", "medical_bill", "boarding_pass", "incident_report"])
    all_valid_types = set(valid_doc_types) | {"damage_photo", "repair_estimate", "fir", "medical_bill", "boarding_pass", "incident_report"}
    if document_type not in all_valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid document_type '{document_type}' for claim type '{ctype}'. Allowed: {sorted(all_valid_types)}",
        )

    # Validate file extension and MIME type
    original_filename = file.filename or "unnamed"
    ext = os.path.splitext(original_filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file extension '{ext}'.")
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported MIME type '{file.content_type}'.")

    # Sanitize filename and write to disk
    safe_filename = sanitize_filename(original_filename)
    doc_id = str(uuid.uuid4())
    upload_dir = Path(settings.UPLOAD_DIR) / ticket_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / f"{doc_id}{ext}"

    try:
        file_path.write_bytes(content)
    except Exception:
        logger.exception("Failed to write uploaded file to disk")
        raise HTTPException(status_code=500, detail="File upload failed. Please try again.")

    doc_record = Document(
        id=doc_id,
        claim_id=claim.id,
        document_type=document_type,
        original_filename=safe_filename,
        file_path=str(file_path),
        mime_type=file.content_type,
        file_size_bytes=len(content),
    )
    db.add(doc_record)
    try:
        db.commit()
    except Exception:
        db.rollback()
        file_path.unlink(missing_ok=True)
        logger.exception("Failed to persist document record")
        raise HTTPException(status_code=500, detail="Document record creation failed.")

    return {
        "document_id": doc_id,
        "document_type": document_type,
        "filename": safe_filename,
        "file_size_bytes": len(content),
        "status": "uploaded",
    }


@router.get("/{ticket_id}/documents")
def list_claim_documents(
    ticket_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """List uploaded documents for a claim."""
    current_user = _resolve_user(request, db)
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found for the given ticket_id.")
    enforce_claim_ownership(claim, current_user)

    docs = db.query(Document).filter(Document.claim_id == claim.id).all()
    return [
        {
            "document_id": str(d.id),
            "document_type": d.document_type,
            "filename": d.original_filename,
            "file_size_bytes": d.file_size_bytes,
            "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
        }
        for d in docs
    ]


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
