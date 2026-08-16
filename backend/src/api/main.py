import logging
import os
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.database.session import get_db
from src.database.models import Claim, Document, PaymentRequest, Policy
from src.agents.graph import build_intake_graph, build_evaluation_graph
from src.agents.nodes import DOCUMENT_REQUIREMENTS

logger = logging.getLogger(__name__)

app = FastAPI(title="Insurance Claim Intake API")

# ---------------------------------------------------------------------------
# R3-5: CORS origins read from env so Vercel/Railway URLs can be configured
# without a code change.  Falls back to localhost:3000 for local dev.
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

# ---------------------------------------------------------------------------
# Document upload security constants (R3-2)
# ---------------------------------------------------------------------------
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MIN_UPLOAD_SIZE_BYTES = 100               # reject obviously-empty files
ALLOWED_MIME_TYPES = {
    "image/jpeg", "image/png", "image/webp", "image/gif",
    "application/pdf",
}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf"}


@app.get("/")
def root():
    return RedirectResponse(url="/docs")


@app.get("/health")
def health_check():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Stage 1-2: Intake + missing-field loop
# ---------------------------------------------------------------------------

class ClaimIntakeRequest(BaseModel):
    # R3-1: max_length prevents unbounded LLM prompt injection via claim_text.
    claim_text: str = Field(..., min_length=1, max_length=5000)
    input_mode: str = "text"          # "voice" or "text"
    ticket_id: Optional[str] = None   # pass back in on subsequent turns of the field-prompt loop


@app.post("/api/v1/claims/intake")
def intake_claim(request: ClaimIntakeRequest, db: Session = Depends(get_db)):
    """
    Runs extraction + mandatory-field check only. If fields are missing, the
    response tells the frontend what to ask/speak next; the frontend resubmits
    to this same endpoint with the same ticket_id and the additional text
    (e.g. "policy XYZ123") appended to claim_text.

    R1-5: If the claim is already 'evaluated', short-circuit and return the
    current state rather than re-running the extraction graph.
    """
    claim = None
    if request.ticket_id:
        try:
            claim = db.query(Claim).filter(Claim.ticket_id == request.ticket_id).with_for_update().first()
        except Exception:
            claim = db.query(Claim).filter(Claim.ticket_id == request.ticket_id).first()
        if not claim:
            raise HTTPException(status_code=404, detail="ticket_id not found")

    # R1-5: Short-circuit if already evaluated to prevent re-extraction from
    # overwriting confirmed field data.
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

    # R4-4: Wrap graph.invoke() in try/except so any node exception (Ollama
    # down, DB mid-invocation) surfaces as a structured 503 rather than a raw
    # 500 stack trace to the client.
    try:
        graph = build_intake_graph()
        result = graph.invoke(initial_state)
    except Exception as exc:
        logger.exception("intake_claim: graph invocation failed")
        raise HTTPException(
            status_code=503,
            detail=(
                "The claim processing pipeline encountered an error. "
                "Your claim has not been saved. Please try again in a moment. "
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

    # R3-8: Persist extraction_confidence to the DB column (previously always NULL).
    if result.get("extraction_confidence") is not None:
        setattr(claim, "extraction_confidence", float(result["extraction_confidence"]))

    # Map incident_date to the DB column if it was successfully extracted
    incident_date_str = result.get("extracted_data", {}).get("incident_date")
    if incident_date_str:
        try:
            setattr(claim, "incident_date", datetime.strptime(incident_date_str, "%Y-%m-%d").date())
        except ValueError:
            pass  # date stays NULL in DB; fraud_detector will flag it as unparseable

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


# ---------------------------------------------------------------------------
# Stage 3: Documents
# ---------------------------------------------------------------------------

@app.post("/api/v1/claims/{ticket_id}/documents")
def upload_document(
    ticket_id: str,
    document_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="ticket_id not found")

    # R3-2: MIME type validation
    content_type = file.content_type or ""
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File type '{content_type}' is not allowed. "
                f"Accepted types: {sorted(ALLOWED_MIME_TYPES)}. "
                "Please upload a JPEG, PNG, WebP, GIF, or PDF file."
            ),
        )

    # R3-2: File extension validation (second gate against spoofed content-type)
    filename = file.filename or "uploaded_file"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File extension '{ext}' is not allowed. "
                f"Accepted extensions: {sorted(ALLOWED_EXTENSIONS)}."
            ),
        )

    # R3-2: Read entire file to enforce size limits before uploading to S3.
    # This guards against huge uploads at your expense.
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
            detail=f"File too large ({file_size:,} bytes). Maximum allowed: {MAX_UPLOAD_SIZE_BYTES:,} bytes (10 MB).",
        )

    # Re-wrap the bytes as a file-like object for upload_to_s3.
    import io
    file_obj = io.BytesIO(file_bytes)

    claim_type = str(getattr(claim, "claim_type", "") or "")
    valid_types = DOCUMENT_REQUIREMENTS.get(claim_type, [])
    # Basic relevance check (August scope: type-based only; OCR-based content
    # matching for "does this photo actually show a damaged car" is September+)
    if valid_types and document_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=(
                f"'{document_type}' is not a required or recognized document type for "
                f"claim_type '{claim_type}'. Expected one of: {valid_types}. "
                "Please re-upload the correct document."
            ),
        )

    # FIX 1 (clarified): db.flush() here is a precautionary guard for the edge
    # case where claim was just added in the same request (not applicable in
    # this path since upload_document always fetches an existing claim, but
    # harmless and defensive against future refactors).
    db.flush()
    s3_filename = f"{claim.id}/{uuid.uuid4().hex[:8]}_{filename}"

    # R1-7: Wrap S3 upload in try/except so bad credentials or a missing bucket
    # name surfaces as a structured 503 rather than a raw 500 stack trace.
    try:
        from src.utils.s3 import upload_to_s3
        s3_url = upload_to_s3(file_obj, s3_filename)
    except ValueError as exc:
        logger.error("upload_document: S3 configuration error: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Document storage is not configured. Please contact support.",
        )
    except Exception as exc:
        logger.exception("upload_document: S3 upload failed for claim %s", ticket_id)
        raise HTTPException(
            status_code=503,
            detail=(
                "Failed to upload document to storage. "
                "Please try again in a moment."
            ),
        )

    doc = Document(
        claim_id=claim.id,
        document_type=document_type,
        original_filename=filename,
        file_path=s3_url,
        mime_type=content_type,
        file_size_bytes=file_size,
    )
    db.add(doc)

    # keep pipeline_state.documents in sync so the evaluation graph sees it
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
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="ticket_id not found")
    docs = db.query(Document).filter(Document.claim_id == claim.id).all()
    return [
        {
            "document_id": str(d.id),
            "document_type": d.document_type,
            "filename": d.original_filename,
            "uploaded_at": d.uploaded_at,
        }
        for d in docs
    ]


@app.get("/api/v1/document-requirements/{claim_type}")
def document_requirements(claim_type: str):
    required = DOCUMENT_REQUIREMENTS.get(claim_type, [])
    return {
        "claim_type": claim_type,
        "documents_needed": len(required) > 0,
        "required_documents": required,
    }


# ---------------------------------------------------------------------------
# Stage 3 (confirmation) + Stage 4-7: Confirm -> Evaluate -> Decision -> Closure
# ---------------------------------------------------------------------------

class ConfirmRequest(BaseModel):
    confirmed: bool = True


@app.post("/api/v1/claims/{ticket_id}/confirm")
def confirm_and_evaluate(ticket_id: str, request: ConfirmRequest, db: Session = Depends(get_db)):
    """
    Called once the frontend has shown/spoken the extracted fields back to the
    user and the user confirms them. Runs the full evaluation graph.

    R2-7: Idempotency guard — if the claim has already been evaluated, return
    the cached result rather than re-running the graph (which would insert a
    second PaymentRequest row on an approved claim).
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
        return {"ticket_id": ticket_id, "status": "not_confirmed", "message": "Confirmation declined; no changes made."}

    # R2-7: Idempotency guard — return cached evaluation result without re-running
    # the graph or inserting a second PaymentRequest row.
    if getattr(claim, "status", None) == "evaluated":
        logger.info("confirm_and_evaluate: claim %s already evaluated, returning cached result", ticket_id)
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
            "_cached": True,  # signals to the client this is a cached response
        }

    # R2-1: Duplicate claim detection — check for an existing evaluated claim
    # with the same policy_id and incident_date (basic, not ML-based).
    incident_date_str = (state.get("extracted_data") or {}).get("incident_date")
    policy_number = (state.get("extracted_data") or {}).get("policy_id")
    if incident_date_str and policy_number:
        try:
            incident_date_parsed = datetime.strptime(incident_date_str, "%Y-%m-%d").date()
        except ValueError:
            incident_date_parsed = None

        if incident_date_parsed:
            # Look up the policy to get its UUID
            existing_policy = db.query(Policy).filter(Policy.policy_number == policy_number).first()
            if existing_policy:
                duplicate = (
                    db.query(Claim)
                    .filter(
                        Claim.policy_id == existing_policy.id,
                        Claim.incident_date == incident_date_parsed,
                        Claim.status == "evaluated",
                        Claim.ticket_id != ticket_id,  # exclude self
                    )
                    .first()
                )
                if duplicate:
                    logger.warning(
                        "confirm_and_evaluate: potential duplicate claim %s detected "
                        "(existing evaluated claim %s for same policy+date)",
                        ticket_id, duplicate.ticket_id,
                    )
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"A claim for policy {policy_number} with incident date "
                            f"{incident_date_str} already exists (ticket: {duplicate.ticket_id}). "
                            "If you believe this is a separate incident, please contact support."
                        ),
                    )

    state["confirmed"] = True
    state["ticket_id"] = ticket_id

    # R4-4: Wrap graph.invoke() so any node exception surfaces as a 503 not a stack trace.
    try:
        graph = build_evaluation_graph(db)
        result = graph.invoke(state)
    except Exception as exc:
        logger.exception("confirm_and_evaluate: evaluation graph failed for claim %s", ticket_id)
        raise HTTPException(
            status_code=503,
            detail=(
                "The claim evaluation pipeline encountered an error. "
                "Your claim data has been saved — please try confirming again in a moment. "
                f"(Error: {type(exc).__name__})"
            ),
        )

    setattr(claim, "pipeline_state", dict(result))
    setattr(claim, "validation_status", str(result.get("validation_status") or ""))
    setattr(claim, "fraud_score", float(result.get("fraud_score") or 0.0))
    setattr(claim, "fraud_flags", list(result.get("fraud_flags", [])))
    setattr(claim, "final_decision", str(result.get("final_decision") or ""))
    setattr(claim, "closure_status", str(result.get("closure_status") or ""))
    setattr(claim, "status", "evaluated")

    # Map policy_id to DB column if policy details were found
    policy_id = result.get("policy_data", {}).get("id")
    if policy_id:
        setattr(claim, "policy_id", policy_id)

    # Ensure incident_date is mapped in case it wasn't captured in early intake
    incident_date_str2 = result.get("extracted_data", {}).get("incident_date")
    if incident_date_str2:
        try:
            setattr(claim, "incident_date", datetime.strptime(incident_date_str2, "%Y-%m-%d").date())
        except ValueError:
            pass

    # Stub payment logging -- only on approval, never actually disbursed.
    # R2-7: This block is only reached when status != "evaluated" (checked above),
    # so a second /confirm call will short-circuit before inserting a duplicate row.
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


@app.get("/api/v1/claims/{ticket_id}")
def get_claim(ticket_id: str, db: Session = Depends(get_db)):
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="ticket_id not found")
    state = claim.pipeline_state or {}
    return {
        "ticket_id": claim.ticket_id,
        "status": claim.status,
        "final_decision": claim.final_decision,
        "closure_status": claim.closure_status,
        "extracted_data": state.get("extracted_data"),
        "response_message": state.get("response_message"),
    }