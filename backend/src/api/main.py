import os
import uuid
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.database.session import get_db
from src.database.models import Claim, Document, PaymentRequest, Policy
from src.agents.graph import build_intake_graph, build_evaluation_graph
from src.agents.nodes import DOCUMENT_REQUIREMENTS

app = FastAPI(title="Insurance Claim Intake API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STORAGE_DIR = os.getenv("STORAGE_LOCAL_PATH", os.path.join("uploads", "claims_documents"))
os.makedirs(STORAGE_DIR, exist_ok=True)


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
    claim_text: str
    input_mode: str = "text"          # "voice" or "text"
    ticket_id: Optional[str] = None   # pass back in on subsequent turns of the field-prompt loop


@app.post("/api/v1/claims/intake")
def intake_claim(request: ClaimIntakeRequest, db: Session = Depends(get_db)):
    """
    Runs extraction + mandatory-field check only. If fields are missing, the
    response tells the frontend what to ask/speak next; the frontend resubmits
    to this same endpoint with the same ticket_id and the additional text
    (e.g. "policy XYZ123") appended to claim_text.
    """
    claim = None
    if request.ticket_id:
        claim = db.query(Claim).filter(Claim.ticket_id == request.ticket_id).first()
        if not claim:
            raise HTTPException(status_code=404, detail="ticket_id not found")

    prior_state: Dict[str, Any] = dict(getattr(claim, "pipeline_state", None) or {})

    initial_state = {
        **prior_state,
        "claim_text": request.claim_text,
        "input_mode": request.input_mode,
    }

    graph = build_intake_graph()
    result = graph.invoke(initial_state)

    ticket_id = request.ticket_id or f"CLAIM-{uuid.uuid4().hex[:8].upper()}"

    if claim is None:
        claim = Claim(ticket_id=ticket_id, input_mode=request.input_mode, status="draft")
        db.add(claim)

    setattr(claim, "pipeline_state", dict(result))
    setattr(claim, "claim_type", result.get("extracted_data", {}).get("claim_type"))
    setattr(claim, "description", result.get("extracted_data", {}).get("damage_description"))
    setattr(claim, "claimed_amount", result.get("extracted_data", {}).get("claimed_amount"))
    db.commit()

    return {
        "ticket_id": ticket_id,
        "extracted_data": result.get("extracted_data", {}),
        "missing_fields": result.get("missing_fields", []),
        "awaiting_confirmation": result.get("awaiting_confirmation", False),
        # text shown to user AND read aloud (TTS wired up in September)
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

    filename = file.filename or "uploaded_file"
    s3_filename = f"{claim.id}/{uuid.uuid4().hex[:8]}_{filename}"
    
    # Upload to S3
    from src.utils.s3 import upload_to_s3
    s3_url = upload_to_s3(file.file, s3_filename)

    doc = Document(
        claim_id=claim.id,
        document_type=document_type,
        original_filename=filename,
        file_path=s3_url,
        mime_type=file.content_type,
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
    user and the user confirms them. Runs the full evaluation graph:
    policy_validator -> document_requirement_checker -> coverage_checker
    -> fraud_detector -> route_decision -> response_formatter.
    """
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="ticket_id not found")

    state = claim.pipeline_state or {}

    if state.get("missing_fields"):
        raise HTTPException(status_code=400, detail="Cannot evaluate: mandatory fields still missing.")

    if not request.confirmed:
        return {"ticket_id": ticket_id, "status": "not_confirmed", "message": "Confirmation declined; no changes made."}

    state["confirmed"] = True
    state["ticket_id"] = ticket_id

    graph = build_evaluation_graph(db)
    result = graph.invoke(state)
    
    setattr(claim, "pipeline_state", dict(result))
    setattr(claim, "validation_status", str(result.get("validation_status") or ""))
    setattr(claim, "fraud_score", float(result.get("fraud_score") or 0.0))
    setattr(claim, "fraud_flags", list(result.get("fraud_flags", [])))
    setattr(claim, "final_decision", str(result.get("final_decision") or ""))
    setattr(claim, "closure_status", str(result.get("closure_status") or ""))
    setattr(claim, "status", "evaluated")

    # Stub payment logging -- only on approval, never actually disbursed
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