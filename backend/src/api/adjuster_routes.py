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
from src.agents.llm_factory import get_configured_llm
from src.knowledge.retriever import KnowledgeRetriever

router=APIRouter(prefix="/api/v1/adjuster",tags=["Adjuster"])

def _guard(user: User=Depends(get_current_user)):
    if user.role not in {"ADJUSTER","ADMIN"}:
        raise HTTPException(status_code=403,detail="Adjuster access required.")
    return user

def _auto_assign_pending(claims:list[Claim], db:Session):
    changed=False
    for c in claims:
        state=dict(c.pipeline_state or {})
        if state.get("assigned_adjuster_id") or c.status not in {"submitted","pending_adjuster"}:
            continue
        if not (state.get("confirmed") and (state.get("policy_verification") or {}).get("valid") and not state.get("dynamic_missing")):
            continue
        spec=(c.insurance_type or "").lower()
        a=db.query(Adjuster).filter(Adjuster.is_active==True,Adjuster.specialization==spec).order_by(Adjuster.claims_assigned.asc(),Adjuster.name.asc()).first()
        if not a:
            a=db.query(Adjuster).filter(Adjuster.is_active==True).order_by(Adjuster.claims_assigned.asc(),Adjuster.name.asc()).first()
        if a:
            a.claims_assigned=(a.claims_assigned or 0)+1
            state["assigned_adjuster_id"]=str(a.id); state["assigned_adjuster_name"]=a.name
            c.pipeline_state=state; c.status="pending_adjuster"; changed=True
    if changed: db.commit()

def _can_access_claim(c: Claim, user: User) -> bool:
    if user.role == "ADMIN":
        return True
    return str((c.pipeline_state or {}).get("assigned_adjuster_id")) == str(user.id)

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
    claims=q.order_by(Claim.updated_at.desc()).all()
    _auto_assign_pending(claims, db)
    if user.role=="ADJUSTER":
        adjuster=db.query(Adjuster).filter(Adjuster.email==user.email).first()
        claims=[c for c in claims if adjuster and str((c.pipeline_state or {}).get("assigned_adjuster_id"))==str(adjuster.id)]
    return {"items":[_item(c) for c in claims],"total":len(claims)}

@router.get("/claims/{ticket_id}")
def claim_file(ticket_id:str,user:User=Depends(_guard),db:Session=Depends(get_db)):
    c=db.query(Claim).filter(Claim.ticket_id==ticket_id).first()
    if not c: raise HTTPException(status_code=404,detail="Claim not found.")
    if not _can_access_claim(c, user): raise HTTPException(status_code=403, detail="This claim is not assigned to you.")
    state=dict(c.pipeline_state or {})
    turns=db.query(ConversationTurn).filter(ConversationTurn.claim_id==c.id).order_by(ConversationTurn.turn_number,ConversationTurn.created_at).all()
    return {"claim":_item(c),"extracted_data":state.get("extracted_data",{}),
            "conversation":[{"speaker":"Claimant" if t.speaker in {"user","claimant"} else "Agent","text":t.text,"turn":t.turn_number} for t in turns],
            "requirements":state.get("dynamic_requirements",[]),"missing_requirements":state.get("dynamic_missing",[]),"missing_evidence":state.get("missing_evidence",[]),
            "evidence":state.get("evidence",[]),"policy_verification":state.get("policy_verification",{}),
            "knowledge_sources":state.get("knowledge_sources",[]),"copilot":state.get("copilot",{})}

@router.patch("/claims/{ticket_id}")
def update_claim(ticket_id:str,payload:ClaimUpdate,user:User=Depends(_guard),db:Session=Depends(get_db)):
    c=db.query(Claim).filter(Claim.ticket_id==ticket_id).first()
    if not c: raise HTTPException(status_code=404,detail="Claim not found.")
    if not _can_access_claim(c, user): raise HTTPException(status_code=403, detail="This claim is not assigned to you.")
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

@router.get("/claims/{ticket_id}/evidence/{evidence_id}/url")
def evidence_url(ticket_id:str,evidence_id:str,user:User=Depends(require_role(["ADJUSTER","ADMIN"])),db:Session=Depends(get_db)):
    claim=db.query(Claim).filter(Claim.ticket_id==ticket_id).first()
    if not claim: raise HTTPException(status_code=404,detail="Claim not found.")
    if not _can_access_claim(claim,user): raise HTTPException(status_code=403,detail="This claim is not assigned to you.")
    state=dict(claim.pipeline_state or {})
    item=next((e for e in state.get("evidence",[]) if str(e.get("id"))==evidence_id),None)
    if not item or not item.get("s3_key"): raise HTTPException(status_code=404,detail="Evidence object not found.")
    from src.storage.s3 import presigned_get
    return {"url":presigned_get(item["s3_key"]),"expires_in":900}

@router.get("/claims/{ticket_id}/copilot")
def copilot(ticket_id:str,user:User=Depends(_guard),db:Session=Depends(get_db)):
    c=db.query(Claim).filter(Claim.ticket_id==ticket_id).first()
    if not c: raise HTTPException(status_code=404,detail="Claim not found.")
    if not _can_access_claim(c, user): raise HTTPException(status_code=403, detail="This claim is not assigned to you.")
    state=dict(c.pipeline_state or {})
    data=state.get("extracted_data") or {}
    context=KnowledgeRetriever().retrieve(
        insurance_type=c.insurance_type or "",
        policy_number=data.get("policy_id"),
        incident_date=c.event_date,
        query=c.event_description or "",
    )
    if not state.get("copilot"):
        prompt=(
            "Act as an insurance adjuster copilot. Give advisory analysis only; never make the final legal or coverage decision. "
            "Use only claim facts and retrieved evidence. State uncertainty when evidence is insufficient. "
            f"Claim facts: {data}\nIncident: {c.event_description}\n"
            f"Retrieved policy evidence: {context.get('policy', [])}\n"
            f"Retrieved regulatory evidence: {context.get('regulations', [])}"
        )
        try:
            result=get_configured_llm().invoke(prompt)
            text=getattr(result,"content",str(result)).strip()
            if text:
                state["copilot"]={"summary":text,"coverage_observations":[],"evidence_gaps":[]}
                state["knowledge_sources"]=[*context.get("policy",[]),*context.get("regulations",[])]
                c.pipeline_state=state
                db.commit()
        except Exception:
            return {"ticket_id":ticket_id,"analysis":None,"status":"unavailable","error":"AI provider is temporarily unavailable. Retry Copilot shortly.","sources":[*context.get("policy",[]),*context.get("regulations",[])]}
    return {"ticket_id":ticket_id,"analysis":state.get("copilot"),"status":"ready" if state.get("copilot") else "unavailable","sources":state.get("knowledge_sources",[])}
