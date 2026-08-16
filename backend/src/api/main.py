"""
FastAPI application for Insurance Claim Intake and Conversation Management.

Features:
- Review 1 Core: Claim intake endpoint, voice session initialization, conversation history
- Review 2 / Review 3: Document uploads, policy confirmation & evaluation pipeline
"""
import io
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.database.session import get_db
from src.database.models import Claim, Document, PaymentRequest, Policy, ConversationTurn
from src.agents.graph import build_intake_graph, build_evaluation_graph
from src.agents.evaluation import DOCUMENT_REQUIREMENTS
from src.api.voice_ws import router as voice_router

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Insurance Claim Intake Voice Agent API",
    description="Conversational insurance claim intake and automated evaluation service",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# CORS Configuration
# ---------------------------------------------------------------------------
_allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS: List[str] = (
    [o.strip() for o in _allowed_origins_env.split(",") if o.strip()]
    if _allowed_origins_env
    else ["http://localhost:3000"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(voice_router)

# Document upload security constraints
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MIN_UPLOAD_SIZE_BYTES = 100               # Reject empty files
ALLOWED_MIME_TYPES = {
    "image/jpeg", "image/png", "image/webp", "image/gif",
    "application/pdf",
}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf"}


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/health")
def health_check():
    """Health check endpoint for container probes and load balancers."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Review 1: Intake & Conversational Field Collection
# ---------------------------------------------------------------------------

class ClaimIntakeRequest(BaseModel):
    claim_text: str = Field(..., min_length=1, max_length=5000, description="User utterance or input text")
    input_mode: str = Field("text", description="'voice' or 'text'")
    ticket_id: Optional[str] = Field(None, description="Existing claim ticket ID for subsequent turns")


@app.post("/api/v1/claims/intake")
def intake_claim(request: ClaimIntakeRequest, db: Session = Depends(get_db)):
    """
    Process user claim utterance, extract mandatory fields, and evaluate missing fields.
    If fields are missing, returns next question prompt for user.
    """
    claim = None
    if request.ticket_id:
        try:
            claim = db.query(Claim).filter(Claim.ticket_id == request.ticket_id).with_for_update().first()
        except Exception:
            claim = db.query(Claim).filter(Claim.ticket_id == request.ticket_id).first()
        if not claim:
            raise HTTPException(status_code=404, detail="ticket_id not found")

    # Short-circuit if already evaluated to prevent overwriting confirmed data
    if claim and getattr(claim, "status", None) in ("evaluated",):
        state = dict(getattr(claim, "pipeline_state", None) or {})
        return {
            "ticket_id": claim.ticket_id,
            "extracted_data": state.get("extracted_data", {}),
            "missing_fields": state.get("missing_fields", []),
            "awaiting_confirmation": state.get("awaiting_confirmation", True),
            "message": "Claim already evaluated. Use GET /api/v1/claims/{ticket_id} to see result.",
        }

    prior_state: Dict[str, Any] = dict(getattr(claim, "pipeline_state", None) or {})

    initial_state = {
        **prior_state,
        "claim_text": request.claim_text,
        "input_mode": request.input_mode,
    }

    try:
        graph = build_intake_graph()
        result = graph.invoke(initial_state)
    except Exception as exc:
        logger.exception("intake_claim: intake graph invocation failed")
        raise HTTPException(
            status_code=503,
            detail=(
                "The claim processing pipeline encountered an error. "
                "Please try again in a moment. "
                f"(Error: {type(exc).__name__})"
            ),
        )

    ticket_id = request.ticket_id or f"CLAIM-{uuid.uuid4().hex[:8].upper()}"

    if claim is None:
        claim = Claim(ticket_id=ticket_id, input_mode=request.input_mode, status="draft")
        db.add(claim)

    setattr(claim, "pipeline_state", dict(result))
    setattr(claim, "claim_type", result.get("extracted_data", {}).get("claim_type"))
    setattr(claim, "description", result.get("extracted_data", {}).get("damage_description"))
    setattr(claim, "claimed_amount", result.get("extracted_data", {}).get("claimed_amount"))

    if result.get("extraction_confidence") is not None:
        setattr(claim, "extraction_confidence", float(result["extraction_confidence"]))

    incident_date_str = result.get("extracted_data", {}).get("incident_date")
    if incident_date_str:
        try:
            setattr(claim, "incident_date", datetime.strptime(incident_date_str, "%Y-%m-%d").date())
        except ValueError:
            pass

    db.commit()

    return {
        "ticket_id": ticket_id,
        "extracted_data": result.get("extracted_data", {}),
        "missing_fields": result.get("missing_fields", []),
        "awaiting_confirmation": result.get("awaiting_confirmation", False),
        "message": (
            "Please provide: " + ", ".join(result.get("missing_fields", []))
            if result.get("missing_fields")
            else "All required details captured. Please review and confirm."
        ),
    }


@app.post("/api/v1/claims/voice-session")
def start_voice_session(db: Session = Depends(get_db)):
    """
    Create a new draft claim session and return ticket_id for WebSocket voice streaming.
    """
    ticket_id = f"CLAIM-{uuid.uuid4().hex[:8].upper()}"
    claim = Claim(
        ticket_id=ticket_id,
        input_mode="voice",
        status="draft",
        conversation_status="not_started",
    )
    db.add(claim)
    db.commit()
    return {"ticket_id": ticket_id}


@app.get("/api/v1/claims/{ticket_id}/conversation")
def get_conversation_history(ticket_id: str, db: Session = Depends(get_db)):
    """
    Fetch the complete chronological conversation turns for a claim.
    """
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="ticket_id not found")

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


@app.get("/api/v1/claims/{ticket_id}")
def get_claim(ticket_id: str, db: Session = Depends(get_db)):
    """
    Retrieve current status and state of a claim.
    """
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="ticket_id not found")
    state = claim.pipeline_state or {}
    return {
        "ticket_id": claim.ticket_id,
        "status": claim.status,
        "conversation_status": claim.conversation_status,
        "final_decision": claim.final_decision,
        "closure_status": claim.closure_status,
        "extracted_data": state.get("extracted_data"),
        "response_message": state.get("response_message"),
    }


@app.get("/api/v1/claims")
def list_claims(db: Session = Depends(get_db)):
    """
    List most recent claims.
    """
    claims = db.query(Claim).order_by(Claim.created_at.desc()).limit(50).all()
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
    return results


# ---------------------------------------------------------------------------
# Review 2 / Review 3: Documents & Evaluation (Isolated)
# ---------------------------------------------------------------------------

@app.post("/api/v1/claims/{ticket_id}/documents")
def upload_document(
    ticket_id: str,
    document_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Upload and register supporting documentation for an existing claim.
    """
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="ticket_id not found")

    content_type = file.content_type or ""
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File type '{content_type}' is not allowed. "
                f"Accepted types: {sorted(ALLOWED_MIME_TYPES)}."
            ),
        )

    filename = file.filename or "uploaded_file"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File extension '{ext}' is not allowed.",
        )

    file_bytes = file.file.read()
    file_size = len(file_bytes)
    if file_size < MIN_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File is too small ({file_size} bytes). Minimum allowed: {MIN_UPLOAD_SIZE_BYTES} bytes.",
        )
    if file_size > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({file_size:,} bytes). Maximum allowed: {MAX_UPLOAD_SIZE_BYTES:,} bytes.",
        )

    file_obj = io.BytesIO(file_bytes)

    claim_type = str(getattr(claim, "claim_type", "") or "")
    valid_types = DOCUMENT_REQUIREMENTS.get(claim_type, [])
    if valid_types and document_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=(
                f"'{document_type}' is not a required document type for '{claim_type}'. "
                f"Expected one of: {valid_types}."
            ),
        )

    db.flush()
    s3_filename = f"{claim.id}/{uuid.uuid4().hex[:8]}_{filename}"

    try:
        from src.utils.s3 import upload_to_s3
        s3_url = upload_to_s3(file_obj, s3_filename)
    except ValueError as exc:
        logger.error("upload_document: S3 config error: %s", exc)
        raise HTTPException(status_code=503, detail="Document storage not configured.")
    except Exception as exc:
        logger.exception("upload_document: S3 upload failed for claim %s", ticket_id)
        raise HTTPException(status_code=503, detail="Failed to upload document to storage.")

    doc = Document(
        claim_id=claim.id,
        document_type=document_type,
        original_filename=filename,
        file_path=s3_url,
        mime_type=content_type,
        file_size_bytes=file_size,
    )
    db.add(doc)

    # Sync documents list in pipeline_state
    state = dict(getattr(claim, "pipeline_state", None) or {})
    docs = list(state.get("documents", []))
    docs.append({"document_type": document_type, "filename": filename, "file_path": s3_url})
    state["documents"] = docs
    setattr(claim, "pipeline_state", dict(state))

    db.commit()
    db.refresh(doc)

    return {
        "document_id": str(doc.id),
        "document_type": doc.document_type,
        "filename": doc.original_filename,
        "status": "uploaded",
    }


@app.get("/api/v1/claims/{ticket_id}/documents")
def list_documents(ticket_id: str, db: Session = Depends(get_db)):
    """List all uploaded documents for a claim ticket."""
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="ticket_id not found")
    docs = db.query(Document).filter(Document.claim_id == claim.id).all()
    return [
        {
            "document_id": str(d.id),
            "document_type": d.document_type,
            "filename": d.original_filename,
            "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
        }
        for d in docs
    ]


@app.get("/api/v1/document-requirements/{claim_type}")
def document_requirements(claim_type: str):
    """Fetch document requirements for a specific claim type."""
    required = DOCUMENT_REQUIREMENTS.get(claim_type.lower(), [])
    return {
        "claim_type": claim_type,
        "documents_needed": len(required) > 0,
        "required_documents": required,
    }


class ConfirmRequest(BaseModel):
    confirmed: bool = True


@app.post("/api/v1/claims/{ticket_id}/confirm")
def confirm_and_evaluate(ticket_id: str, request: ConfirmRequest, db: Session = Depends(get_db)):
    """
    Review 2/3: Confirm collected claim data and trigger evaluation graph.
    """
    try:
        claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).with_for_update().first()
    except Exception:
        claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="ticket_id not found")

    state = claim.pipeline_state or {}

    if state.get("missing_fields"):
        raise HTTPException(status_code=400, detail="Cannot evaluate: mandatory fields still missing.")

    if not request.confirmed:
        return {"ticket_id": ticket_id, "status": "not_confirmed", "message": "Confirmation declined."}

    # Idempotent response if already evaluated
    if getattr(claim, "status", None) == "evaluated":
        logger.info("confirm_and_evaluate: claim %s already evaluated, returning cached state", ticket_id)
        return {
            "ticket_id": ticket_id,
            "final_decision": state.get("final_decision"),
            "closure_status": state.get("closure_status"),
            "response_message": state.get("response_message"),
            "spoken_response": state.get("spoken_response"),
            "extracted_data": state.get("extracted_data"),
            "coverage_eligible": state.get("coverage_eligible"),
            "deductible_amount": state.get("deductible_amount"),
            "payout_amount": state.get("payout_amount"),
            "fraud_score": state.get("fraud_score"),
            "fraud_flags": state.get("fraud_flags"),
            "assigned_adjuster": state.get("assigned_adjuster"),
            "missing_documents": state.get("missing_documents"),
            "audit_log": state.get("audit_log"),
            "_cached": True,
        }

    # Duplicate claim check
    incident_date_str = (state.get("extracted_data") or {}).get("incident_date")
    policy_number = (state.get("extracted_data") or {}).get("policy_id")
    if incident_date_str and policy_number:
        try:
            incident_date_parsed = datetime.strptime(incident_date_str, "%Y-%m-%d").date()
        except ValueError:
            incident_date_parsed = None

        if incident_date_parsed:
            existing_policy = db.query(Policy).filter(Policy.policy_number == str(policy_number).strip().upper()).first()
            if existing_policy:
                duplicate = (
                    db.query(Claim)
                    .filter(
                        Claim.policy_id == existing_policy.id,
                        Claim.incident_date == incident_date_parsed,
                        Claim.status == "evaluated",
                        Claim.ticket_id != ticket_id,
                    )
                    .first()
                )
                if duplicate:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"A claim for policy {policy_number} with incident date "
                            f"{incident_date_str} already exists (ticket: {duplicate.ticket_id})."
                        ),
                    )

    state["confirmed"] = True
    state["ticket_id"] = ticket_id

    try:
        graph = build_evaluation_graph(db)
        result = graph.invoke(state)
    except Exception as exc:
        logger.exception("confirm_and_evaluate: evaluation graph failed for %s", ticket_id)
        raise HTTPException(
            status_code=503,
            detail=f"Claim evaluation pipeline encountered an error: {type(exc).__name__}",
        )

    setattr(claim, "pipeline_state", dict(result))
    setattr(claim, "validation_status", str(result.get("validation_status") or ""))
    setattr(claim, "fraud_score", float(result.get("fraud_score") or 0.0))
    setattr(claim, "fraud_flags", list(result.get("fraud_flags", [])))
    setattr(claim, "final_decision", str(result.get("final_decision") or ""))
    setattr(claim, "closure_status", str(result.get("closure_status") or ""))
    setattr(claim, "status", "evaluated")

    policy_id = result.get("policy_data", {}).get("id")
    if policy_id:
        setattr(claim, "policy_id", policy_id)

    incident_date_str2 = result.get("extracted_data", {}).get("incident_date")
    if incident_date_str2:
        try:
            setattr(claim, "incident_date", datetime.strptime(incident_date_str2, "%Y-%m-%d").date())
        except ValueError:
            pass

    if result.get("final_decision") == "approved":
        db.add(PaymentRequest(
            claim_id=claim.id,
            claimed_amount=result.get("extracted_data", {}).get("claimed_amount"),
            deductible_amount=result.get("deductible_amount"),
            payout_amount=result.get("payout_amount"),
            status="pending_finance",
        ))

    db.commit()

    return {
        "ticket_id": ticket_id,
        "final_decision": result.get("final_decision"),
        "closure_status": result.get("closure_status"),
        "response_message": result.get("response_message"),
        "spoken_response": result.get("spoken_response"),
        "extracted_data": result.get("extracted_data"),
        "coverage_eligible": result.get("coverage_eligible"),
        "deductible_amount": result.get("deductible_amount"),
        "payout_amount": result.get("payout_amount"),
        "fraud_score": result.get("fraud_score"),
        "fraud_flags": result.get("fraud_flags"),
        "assigned_adjuster": result.get("assigned_adjuster"),
        "missing_documents": result.get("missing_documents"),
        "audit_log": result.get("audit_log"),
    }