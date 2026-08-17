"""
FastAPI application for Insurance Claim Intake and Conversation Management.

Phase 1 Core Features:
- Voice & text claim intake endpoints
- Voice session initialization and WebSocket audio streaming
- Turn-by-turn conversational state updates
- Structured claim extraction and confirmation
- Chronological conversation history persistence
- Health check and standardized error responses
"""
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.config import settings
from src.database.session import get_db, engine, SessionLocal
from src.database.models import Base, Claim, Document, Policy, Adjuster, ConversationTurn
from src.agents.graph import build_conversation_graph, build_evaluation_graph
from src.agents.evaluation import DOCUMENT_REQUIREMENTS
from src.api.voice_ws import router as voice_router
from src.utils.logger import app_logger

logger = app_logger


def _init_db_and_seeds():
    """Ensure database schema is created and seed initial canonical records if empty."""
    try:
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        # Seed policies if empty
        if db.query(Policy).first() is None:
            canonical_policies = [
                ("MOT-5521", "motor", 500000, 5000, date(2024, 1, 1), date(2030, 12, 31), True),
                ("XYZ123", "motor", 500000, 10000, date(2024, 1, 1), date(2030, 12, 31), True),
                ("HOME456", "home", 1000000, 10000, date(2025, 3, 1), date(2026, 2, 28), True),
                ("HLT-7789", "health", 800000, 2000, date(2024, 6, 1), date(2026, 5, 31), True),
                ("SNR-9912", "senior_health", 600000, 3000, date(2024, 1, 1), date(2027, 12, 31), True),
                ("TRV-3301", "travel", 200000, 1000, date(2025, 1, 1), date(2025, 12, 31), True),
                ("CYB-8820", "cyber", 1500000, 15000, date(2024, 1, 1), date(2026, 12, 31), True),
            ]
            for pnum, ptype, cov, ded, eff, exp, active in canonical_policies:
                db.add(Policy(
                    id=str(uuid.uuid4()),
                    policy_number=pnum,
                    customer_id=str(uuid.uuid4()),
                    policy_type=ptype,
                    coverage_amount=cov,
                    deductible=ded,
                    effective_date=eff,
                    expiry_date=exp,
                    is_active=active,
                ))

            canonical_adjusters = [
                ("motor", "Priya Sharma", "priya.motor@insure.co"),
                ("home", "Rohan Mehta", "rohan.home@insure.co"),
                ("health", "Dr. Anita Roy", "anita.health@insure.co"),
                ("senior_health", "Dr. V. Rao", "rao.senior@insure.co"),
                ("travel", "Vikram Sen", "vikram.travel@insure.co"),
                ("cyber", "Neha Kapoor", "neha.cyber@insure.co"),
            ]
            for spec, name, email in canonical_adjusters:
                db.add(Adjuster(
                    id=str(uuid.uuid4()),
                    name=name,
                    email=email,
                    specialization=spec,
                    claims_assigned=0,
                    is_active=True,
                ))
            db.commit()
            logger.info("Database schema initialized and canonical policies seeded.")
        db.close()
    except Exception as exc:
        logger.warning("Database schema check notice: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_db_and_seeds()
    yield


app = FastAPI(
    title="Insurance Claim Intake Voice Agent API",
    description="Conversational voice-first insurance claim intake service (Phase 1)",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS Configuration
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(voice_router)


# ---------------------------------------------------------------------------
# Exception Handlers
# ---------------------------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return API-safe JSON for request validation errors."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors(), "message": "Invalid request payload."},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions and return safe 500 error."""
    logger.exception("Unhandled server exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred. Please try again later."},
    )


# ---------------------------------------------------------------------------
# Health & Root
# ---------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/health")
def health_check():
    """Health check endpoint for container probes and monitoring."""
    return {"status": "ok", "environment": settings.ENVIRONMENT}


# ---------------------------------------------------------------------------
# Phase 1: Intake & Conversational Field Collection
# ---------------------------------------------------------------------------

class ClaimIntakeRequest(BaseModel):
    claim_text: str = Field(..., min_length=1, max_length=5000, description="User utterance or input text")
    input_mode: str = Field("text", description="'voice' or 'text'")
    ticket_id: Optional[str] = Field(None, description="Existing claim ticket ID for subsequent turns")


class ClaimConfirmRequest(BaseModel):
    confirmed: bool = Field(True, description="True to confirm and submit claim")


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
    return {
        "ticket_id": ticket_id,
        "initial_message": "Please tell me what happened. You can describe the incident in your own words, and I'll collect the details I need.",
    }


@app.post("/api/v1/claims/intake")
def intake_claim(request: ClaimIntakeRequest, db: Session = Depends(get_db)):
    """
    Process user claim utterance, extract mandatory fields, and evaluate missing fields.
    If fields are missing, returns next question prompt for claimant.
    """
    claim = None
    if request.ticket_id:
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

    ticket_id = request.ticket_id or (claim.ticket_id if claim else f"CLAIM-{uuid.uuid4().hex[:8].upper()}")
    prior_state: Dict[str, Any] = dict(getattr(claim, "pipeline_state", None) or {})

    initial_state = {
        **prior_state,
        "claim_text": request.claim_text,
        "input_mode": request.input_mode,
        "ticket_id": ticket_id,
    }

    try:
        graph = build_conversation_graph()
        result = graph.invoke(initial_state)
    except Exception as exc:
        logger.exception("intake_claim: conversation graph invocation failed")
        raise HTTPException(
            status_code=503,
            detail=(
                "The claim processing pipeline encountered an error. "
                "Please try again in a moment. "
                f"(Error: {type(exc).__name__})"
            ),
        )

    if claim is None:
        claim = Claim(ticket_id=ticket_id, input_mode=request.input_mode, status="draft")
        db.add(claim)
        db.flush()

    setattr(claim, "pipeline_state", dict(result))
    setattr(claim, "claim_type", result.get("extracted_data", {}).get("claim_type"))
    setattr(claim, "description", result.get("extracted_data", {}).get("damage_description"))
    setattr(claim, "claimed_amount", result.get("extracted_data", {}).get("claimed_amount"))
    setattr(claim, "conversation_status", result.get("conversation_status", "collecting"))

    if result.get("extraction_confidence") is not None:
        setattr(claim, "extraction_confidence", float(result["extraction_confidence"]))

    incident_date_str = result.get("extracted_data", {}).get("incident_date")
    if incident_date_str:
        try:
            setattr(claim, "incident_date", datetime.strptime(incident_date_str, "%Y-%m-%d").date())
        except ValueError:
            pass

    # Persist turns in conversation_turns table
    prior_turns = db.query(ConversationTurn).filter(ConversationTurn.claim_id == claim.id).count()
    turn_num = prior_turns + 1
    db.add(ConversationTurn(claim_id=claim.id, turn_number=turn_num, speaker="user", text=request.claim_text))
    agent_msg = result.get("next_question") or result.get("message", "")
    if agent_msg:
        db.add(ConversationTurn(claim_id=claim.id, turn_number=turn_num, speaker="agent", text=agent_msg))

    db.commit()

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


@app.post("/api/v1/claims/{ticket_id}/confirm")
def confirm_claim(ticket_id: str, request: ClaimConfirmRequest = ClaimConfirmRequest(), db: Session = Depends(get_db)):
    """
    Confirm collected claim details and submit structured claim.
    """
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="ticket_id not found")

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

    eval_input = {
        **state,
        "ticket_id": ticket_id,
        "confirmed": True,
        "uploaded_documents": uploaded_doc_types,
    }

    try:
        eval_graph = build_evaluation_graph(db=db)
        eval_result = eval_graph.invoke(eval_input)
    except Exception as exc:
        logger.exception("Evaluation pipeline failed for claim %s", ticket_id)
        raise HTTPException(status_code=500, detail=f"Claim evaluation failed: {exc}")

    # Persist evaluation outcomes — use setattr to satisfy the type-checker on Column types
    setattr(claim, "status", "evaluated")
    setattr(claim, "conversation_status", "intake_complete")
    if eval_result.get("final_decision") is not None:
        setattr(claim, "final_decision", eval_result["final_decision"])
    if eval_result.get("closure_status") is not None:
        setattr(claim, "closure_status", eval_result["closure_status"])
    if eval_result.get("fraud_score") is not None:
        setattr(claim, "fraud_score", eval_result["fraud_score"])
    claim.fraud_flags = eval_result.get("fraud_flags", [])  # type: ignore[assignment]
    setattr(claim, "pipeline_state", dict(eval_result))

    adj = eval_result.get("assigned_adjuster")
    if adj and adj.get("id") not in (None, "UNASSIGNED", "ADJ-DEFAULT"):
        claim.assigned_adjuster_id = adj.get("id")

    db.commit()

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
        "fraud_flags": claim.fraud_flags,
    }


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
    Retrieve current status and structured state of a claim.
    """
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="ticket_id not found")
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
# Phase 2 Compatible Document Upload Endpoint
# ---------------------------------------------------------------------------
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MIN_UPLOAD_SIZE_BYTES = 100               # Reject empty files
ALLOWED_MIME_TYPES = {
    "image/jpeg", "image/png", "image/webp", "image/gif",
    "application/pdf",
}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf"}


@app.post("/api/v1/claims/{ticket_id}/documents")
async def upload_document(
    ticket_id: str,
    document_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Upload supporting claim evidence document (Phase 2 compatibility).
    """
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="ticket_id not found")

    content = await file.read()
    if len(content) < MIN_UPLOAD_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(content) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds 10MB limit.")

    ctype = str((claim.pipeline_state or {}).get("extracted_data", {}).get("claim_type") or claim.claim_type or "motor")
    valid_doc_types = DOCUMENT_REQUIREMENTS.get(ctype, ["damage_photo", "repair_estimate", "medical_bill", "boarding_pass", "incident_report"])
    if document_type not in valid_doc_types and document_type not in ("damage_photo", "repair_estimate", "fir", "medical_bill", "boarding_pass", "incident_report"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid document_type '{document_type}' for claim type '{ctype}'. Allowed: {valid_doc_types}",
        )

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS or file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file format '{file.content_type}'.")

    doc_id = str(uuid.uuid4())
    doc_record = Document(
        id=doc_id,
        claim_id=claim.id,
        document_type=document_type,
        original_filename=file.filename,
        file_path=f"uploads/{ticket_id}/{doc_id}{ext}",
        mime_type=file.content_type,
        file_size_bytes=len(content),
    )
    db.add(doc_record)
    db.commit()

    return {
        "document_id": doc_id,
        "document_type": document_type,
        "filename": file.filename,
        "file_size_bytes": len(content),
        "status": "uploaded",
    }


@app.get("/api/v1/claims/{ticket_id}/documents")
def list_claim_documents(ticket_id: str, db: Session = Depends(get_db)):
    """List uploaded documents for a claim."""
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="ticket_id not found")
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