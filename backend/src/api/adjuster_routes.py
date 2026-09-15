"""Adjuster workbench API: queue, claim file, evidence state and copilot context."""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from src.database.models import Claim, Adjuster
from src.database.session import get_db
from src.api.deps import get_current_user

router = APIRouter(prefix="/api/v1/adjuster", tags=["Adjuster"])

def _require_adjuster(request: Request, db: Session):
    user = get_current_user(request=request, credentials=None, db=db)
    if user.role not in {"ADJUSTER", "ADMIN"}:
        raise HTTPException(status_code=403, detail="Adjuster access required.")
    return user

class ClaimUpdate(BaseModel):
    status: str | None = None
    priority: str | None = None
    note: str | None = Field(None, max_length=4000)

@router.get("/queue")
def queue(request: Request, db: Session = Depends(get_db)):
    user = _require_adjuster(request, db)
    query = db.query(Claim).filter(Claim.status.in_(["submitted", "under_review", "pending_evidence", "pending_adjuster"]))
    if user.role == "ADJUSTER":
        query = query.filter(Claim.pipeline_state.op("->>")("assigned_adjuster_id") == str(user.id)) if False else query
    claims = query.order_by(Claim.updated_at.desc()).all()
    return {"items": [{
        "ticket_id": c.ticket_id,
        "status": c.status,
        "insurance_type": c.insurance_type,
        "event_date": c.event_date.isoformat() if c.event_date else None,
        "event_location": c.event_location,
        "estimated_claim_amount": float(c.estimated_claim_amount) if c.estimated_claim_amount is not None else None,
        "assigned_adjuster_id": (c.pipeline_state or {}).get("assigned_adjuster_id"),
        "priority": (c.pipeline_state or {}).get("priority", "normal"),
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    } for c in claims], "total": len(claims)}

@router.get("/claims/{ticket_id}")
def claim_file(ticket_id: str, request: Request, db: Session = Depends(get_db)):
    _require_adjuster(request, db)
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim: raise HTTPException(status_code=404, detail="Claim not found.")
    state = dict(claim.pipeline_state or {})
    return {
        "claim": {
            "ticket_id": claim.ticket_id, "status": claim.status,
            "insurance_type": claim.insurance_type, "event_date": claim.event_date.isoformat() if claim.event_date else None,
            "event_location": claim.event_location, "event_description": claim.event_description,
            "estimated_claim_amount": float(claim.estimated_claim_amount) if claim.estimated_claim_amount is not None else None,
            "extracted_data": state.get("extracted_data", {}),
        },
        "conversation": state.get("conversation_history", []),
        "requirements": state.get("dynamic_requirements", []),
        "evidence": state.get("evidence", []),
        "copilot": state.get("copilot", {}),
    }

@router.patch("/claims/{ticket_id}")
def update_claim(ticket_id: str, payload: ClaimUpdate, request: Request, db: Session = Depends(get_db)):
    user = _require_adjuster(request, db)
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim: raise HTTPException(status_code=404, detail="Claim not found.")
    state = dict(claim.pipeline_state or {})
    if payload.status: claim.status = payload.status
    if payload.priority: state["priority"] = payload.priority
    if payload.note: state.setdefault("adjuster_notes", []).append({"author_id": str(user.id), "note": payload.note})
    claim.pipeline_state = state
    db.commit()
    return {"success": True, "ticket_id": ticket_id, "status": claim.status, "pipeline_state": state}

@router.get("/claims/{ticket_id}/copilot")
def copilot(ticket_id: str, request: Request, db: Session = Depends(get_db)):
    _require_adjuster(request, db)
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim: raise HTTPException(status_code=404, detail="Claim not found.")
    state = dict(claim.pipeline_state or {})
    return {"ticket_id": ticket_id, "analysis": state.get("copilot", {}), "sources": state.get("knowledge_sources", [])}
