"""Authenticated adjuster workbench API."""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func
from src.api.deps import get_current_user
from src.database.models import Claim, Adjuster, User, ConversationTurn
from src.database.session import get_db

router=APIRouter(prefix="/api/v1/adjuster",tags=["Adjuster"])

def _guard(user: User=Depends(get_current_user)):
    if user.role not in {"ADJUSTER","ADMIN"}:
        raise HTTPException(status_code=403,detail="Adjuster access required.")
    return user

class ClaimUpdate(BaseModel):
    status: str|None=None
    priority: str|None=None
    note: str|None=Field(None,max_length=4000)

def _item(c: Claim, adjuster: Adjuster|None=None)->dict[str,Any]:
    state=dict(c.pipeline_state or {})
    return {
        "ticket_id":c.ticket_id,
        "status":c.status,
        "insurance_type":c.insurance_type,
        "event_date":c.event_date.isoformat() if c.event_date else None,
        "event_location":c.event_location,
        "estimated_claim_amount":float(c.estimated_claim_amount) if c.estimated_claim_amount is not None else None,
        "priority":state.get("priority","normal"),
        "assigned_adjuster_id":state.get("assigned_adjuster_id"),
        "assigned_adjuster_name":adjuster.name if adjuster else state.get("assigned_adjuster_name"),
        "claimant_confirmed":bool(state.get("confirmed")),
        "policy_verified":bool((state.get("policy_verification") or {}).get("valid")),
        "dynamic_requirements_complete":not bool(state.get("dynamic_missing")),
        "updated_at":c.updated_at.isoformat() if c.updated_at else None,
    }

@router.get("/queue")
def queue(user:User=Depends(_guard),db:Session=Depends(get_db)):
    q=db.query(Claim).filter(Claim.status.in_(["submitted","under_review","pending_evidence","pending_adjuster"]))
    if user.role=="ADJUSTER":
        q=q.filter(Claim.pipeline_state.isnot(None))
    claims=q.order_by(Claim.updated_at.desc()).all()
    return {"items":[_item(c) for c in claims],"total":len(claims)}

@router.get("/claims/{ticket_id}")
def claim_file(ticket_id:str,user:User=Depends(_guard),db:Session=Depends(get_db)):
    c=db.query(Claim).filter(Claim.ticket_id==ticket_id).first()
    if not c: raise HTTPException(status_code=404,detail="Claim not found.")
    state=dict(c.pipeline_state or {})
    turns=db.query(ConversationTurn).filter(ConversationTurn.claim_id==c.id).order_by(ConversationTurn.turn_number,ConversationTurn.created_at).all()
    return {"claim":_item(c),"extracted_data":state.get("extracted_data",{}),
            "conversation":[{"speaker":"Claimant" if t.speaker in {"user","claimant"} else "Agent","text":t.text,"turn":t.turn_number} for t in turns],
            "requirements":state.get("dynamic_requirements",[]),"missing_requirements":state.get("dynamic_missing",[]),
            "evidence":state.get("evidence",[]),"policy_verification":state.get("policy_verification",{}),
            "knowledge_sources":state.get("knowledge_sources",[]),"copilot":state.get("copilot",{})}

@router.patch("/claims/{ticket_id}")
def update_claim(ticket_id:str,payload:ClaimUpdate,user:User=Depends(_guard),db:Session=Depends(get_db)):
    c=db.query(Claim).filter(Claim.ticket_id==ticket_id).first()
    if not c: raise HTTPException(status_code=404,detail="Claim not found.")
    state=dict(c.pipeline_state or {})
    if payload.priority: state["priority"]=payload.priority
    if payload.note: state.setdefault("adjuster_notes",[]).append({"author":user.full_name,"note":payload.note})
    if payload.status: c.status=payload.status
    c.pipeline_state=state; db.commit(); db.refresh(c)
    return _item(c)

@router.post("/claims/{ticket_id}/assign")
def assign_claim(ticket_id:str,user:User=Depends(_guard),db:Session=Depends(get_db)):
    c=db.query(Claim).filter(Claim.ticket_id==ticket_id).first()
    if not c: raise HTTPException(status_code=404,detail="Claim not found.")
    state=dict(c.pipeline_state or {})
    if state.get("assigned_adjuster_id"): return {"success":True,"already_assigned":True,"claim":_item(c)}
    spec=(c.insurance_type or "").lower()
    candidates=db.query(Adjuster).filter(Adjuster.is_active==True,Adjuster.specialization==spec).order_by(Adjuster.claims_assigned.asc(),Adjuster.name.asc()).all()
    if not candidates: candidates=db.query(Adjuster).filter(Adjuster.is_active==True).order_by(Adjuster.claims_assigned.asc(),Adjuster.name.asc()).all()
    if not candidates: raise HTTPException(status_code=409,detail="No active adjuster is available.")
    a=candidates[0]; a.claims_assigned=(a.claims_assigned or 0)+1
    state["assigned_adjuster_id"]=str(a.id); state["assigned_adjuster_name"]=a.name
    c.pipeline_state=state; c.status="pending_adjuster"; db.commit()
    return {"success":True,"already_assigned":False,"claim":_item(c,a)}

@router.get("/claims/{ticket_id}/copilot")
def copilot(ticket_id:str,user:User=Depends(_guard),db:Session=Depends(get_db)):
    c=db.query(Claim).filter(Claim.ticket_id==ticket_id).first()
    if not c: raise HTTPException(status_code=404,detail="Claim not found.")
    state=dict(c.pipeline_state or {})
    return {"ticket_id":ticket_id,"analysis":state.get("copilot",{}),"sources":state.get("knowledge_sources",[])}
