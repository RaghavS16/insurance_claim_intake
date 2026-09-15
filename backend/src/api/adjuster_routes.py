"""Authenticated adjuster workbench API."""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func, select
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

def _can_access_claim(c: Claim, user: User, db: Session | None = None) -> bool:
    if user.role == "ADMIN":
        return True
    if db is not None and db.query(ClaimAssignment).filter(
        ClaimAssignment.claim_id == c.id,
        ClaimAssignment.adjuster_id == user.id,
        ClaimAssignment.is_active.is_(True),
    ).first():
        return True
    return str((c.pipeline_state or {}).get("assigned_adjuster_id")) == str(user.id)



def _resolve_adjuster(request: Request, db: Session) -> User:
    from fastapi.security import HTTPAuthorizationCredentials
    header=request.headers.get("authorization", "")
    credentials=None
    if header.lower().startswith("bearer "):
        credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=header[7:])
    user=get_current_user(request=request, credentials=credentials, db=db)
    if user.role not in {"ADJUSTER", "ADMIN"}:
        raise HTTPException(status_code=403, detail="Adjuster access required.")
    return user

def _ensure_assigned_adjuster(claim: Claim, user: User, db: Session) -> Adjuster:
    assigned_id=(claim.pipeline_state or {}).get("assigned_adjuster_id")
    if user.role == "ADMIN":
        a=db.query(Adjuster).filter(Adjuster.id == assigned_id).first()
        if a: return a
    if str(assigned_id) != str(user.id):
        raise HTTPException(status_code=403, detail="This claim is not assigned to you.")
    a=db.query(Adjuster).filter(Adjuster.id == user.id).first()
    if not a: raise HTTPException(status_code=403, detail="Adjuster profile not found.")
    return a

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
    q=db.query(Claim).filter(Claim.status.in_(["submitted","assigned","under_review","pending_evidence"]))
    claims=q.order_by(Claim.updated_at.desc()).all()
    if user.role=="ADJUSTER":
        adjuster=db.query(Adjuster).filter(Adjuster.email==user.email).first()
        claims=[c for c in claims if adjuster and str((c.pipeline_state or {}).get("assigned_adjuster_id"))==str(adjuster.id)]
    return {"items":[_item(c) for c in claims],"total":len(claims)}

@router.get("/claims/{ticket_id}")
def claim_file(ticket_id:str,user:User=Depends(_guard),db:Session=Depends(get_db)):
    c=db.query(Claim).filter(Claim.ticket_id==ticket_id).first()
    if not c: raise HTTPException(status_code=404,detail="Claim not found.")
    if not _can_access_claim(c, user, db): raise HTTPException(status_code=403, detail="This claim is not assigned to you.")
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
    if not _can_access_claim(c, user, db): raise HTTPException(status_code=403, detail="This claim is not assigned to you.")
    state=dict(c.pipeline_state or {})
    if payload.priority:
        if payload.priority not in {"low","normal","high","urgent"}:
            raise HTTPException(status_code=400, detail="Invalid priority.")
        state["priority"]=payload.priority
    if payload.note:
        db.add(ClaimNote(claim_id=str(c.id), author_user_id=str(user.id), note=payload.note, visibility="internal"))
    if payload.status:
        try:
            transition_claim(db, c, payload.status, str(user.id), "adjuster workflow update")
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
    c.pipeline_state=state
    db.add(ClaimAuditEvent(claim_id=str(c.id), actor_user_id=str(user.id), event_type="claim_updated",
                           new_value_json={"priority":state.get("priority"),"status":c.status}))
    db.commit(); db.refresh(c)
    return _item(c)

@router.post("/claims/{ticket_id}/assign")
def assign_claim(ticket_id:str,user:User=Depends(_guard),db:Session=Depends(get_db)):
    c=db.query(Claim).filter(Claim.ticket_id==ticket_id).first()
    if not c: raise HTTPException(status_code=404,detail="Claim not found.")
    active=db.query(ClaimAssignment).filter(ClaimAssignment.claim_id==c.id,ClaimAssignment.is_active.is_(True)).first()
    if active:
        aa=db.query(Adjuster).filter(Adjuster.id==active.adjuster_id).first()
        return {"success":True,"already_assigned":True,"claim":_item(c,aa)}
    from src.database.claim_workflow import assign_claim as assign_claim_tx
    try:
        aa=assign_claim_tx(db,c,str(user.id))
        if c.status=="submitted": transition_claim(db,c,"assigned",str(user.id),"manual assignment")
        state=dict(c.pipeline_state or {}); state["assigned_adjuster_id"]=str(aa.id); state["assigned_adjuster_name"]=aa.name; c.pipeline_state=state
        db.commit()
    except ValueError as exc:
        db.rollback(); raise HTTPException(status_code=409,detail=str(exc))
    return {"success":True,"already_assigned":False,"claim":_item(c,aa)}

@router.get("/claims/{ticket_id}/evidence/{evidence_id}/url")
def evidence_url(ticket_id:str,evidence_id:str,user:User=Depends(_guard),db:Session=Depends(get_db)):
    claim=db.query(Claim).filter(Claim.ticket_id==ticket_id).first()
    if not claim: raise HTTPException(status_code=404,detail="Claim not found.")
    if not _can_access_claim(claim,user,db): raise HTTPException(status_code=403,detail="This claim is not assigned to you.")
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


# Production workflow endpoints: decisions, notes, audit and normalized assignments.
from pydantic import BaseModel, Field
from src.database.hardening_models import ClaimAssignment, ClaimDecision, ClaimNote, ClaimAuditEvent
from src.database.claim_workflow import transition_claim

class DecisionRequest(BaseModel):
    decision: str = Field(..., pattern="^(approve|partial_approve|reject|request_evidence|escalate)$")
    rationale: str = Field(..., min_length=10, max_length=10000)
    approved_amount: float | None = Field(None, ge=0)

class NoteRequest(BaseModel):
    note: str = Field(..., min_length=1, max_length=10000)
    visibility: str = Field("internal", pattern="^(internal|claimant)$")

@router.get("/claims/{ticket_id}/assignment")
def get_normalized_assignment(ticket_id: str, request: Request, db: Session = Depends(get_db)):
    current_user = _resolve_adjuster(request, db)
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found.")
    _ensure_assigned_adjuster(claim, current_user, db)
    a = db.execute(select(ClaimAssignment).where(
        ClaimAssignment.claim_id == claim.id, ClaimAssignment.is_active.is_(True)
    )).scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="No active assignment exists.")
    return {"id": a.id, "claim_id": a.claim_id, "adjuster_id": a.adjuster_id,
            "assigned_at": a.assigned_at.isoformat(), "reason": a.reason}

@router.post("/claims/{ticket_id}/decision")
def record_decision(ticket_id: str, payload: DecisionRequest, request: Request, db: Session = Depends(get_db)):
    current_user = _resolve_adjuster(request, db)
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found.")
    adjuster = _ensure_assigned_adjuster(claim, current_user, db)
    decision_map = {
        "approve": "approved", "partial_approve": "partially_approved",
        "reject": "rejected", "request_evidence": "pending_evidence", "escalate": "escalated",
    }
    target = decision_map[payload.decision]
    try:
        transition_claim(db, claim, target, str(current_user.id), payload.rationale)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    row = ClaimDecision(
        claim_id=str(claim.id), adjuster_id=str(adjuster.id), decision=payload.decision,
        rationale=payload.rationale, approved_amount=payload.approved_amount,
        ai_recommendation_json=(claim.pipeline_state or {}).get("copilot") or {},
    )
    db.add(row)
    db.add(ClaimAuditEvent(
        claim_id=str(claim.id), actor_user_id=str(current_user.id), event_type="decision_recorded",
        new_value_json={"decision": payload.decision, "approved_amount": payload.approved_amount},
        reason=payload.rationale,
    ))
    db.commit()
    return {"decision_id": row.id, "claim_id": claim.ticket_id, "decision": payload.decision,
            "status": claim.status, "rationale": payload.rationale}

@router.post("/claims/{ticket_id}/notes")
def add_claim_note(ticket_id: str, payload: NoteRequest, request: Request, db: Session = Depends(get_db)):
    current_user = _resolve_adjuster(request, db)
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found.")
    _ensure_assigned_adjuster(claim, current_user, db)
    note = ClaimNote(claim_id=str(claim.id), author_user_id=str(current_user.id),
                     note=payload.note, visibility=payload.visibility)
    db.add(note)
    db.add(ClaimAuditEvent(claim_id=str(claim.id), actor_user_id=str(current_user.id),
                           event_type="note_added", new_value_json={"note_id": note.id}))
    db.commit()
    return {"id": note.id, "created_at": note.created_at.isoformat(), "visibility": note.visibility}

@router.get("/claims/{ticket_id}/audit")
def get_claim_audit(ticket_id: str, request: Request, db: Session = Depends(get_db)):
    current_user = _resolve_adjuster(request, db)
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found.")
    _ensure_assigned_adjuster(claim, current_user, db)
    rows = db.query(ClaimAuditEvent).filter(ClaimAuditEvent.claim_id == claim.id).order_by(ClaimAuditEvent.created_at.asc()).all()
    return [{"id": r.id, "event_type": r.event_type, "actor_user_id": r.actor_user_id,
             "old_value": r.old_value_json, "new_value": r.new_value_json,
             "reason": r.reason, "created_at": r.created_at.isoformat()} for r in rows]
