"""Authenticated adjuster workbench API."""
from __future__ import annotations
from typing import Any
import json
import re
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func, select
from datetime import datetime, timezone
from src.api.deps import get_current_user, require_role, resolve_bearer_user, get_claim_or_404
from src.config import settings
from src.database.models import Claim, Adjuster, User, ConversationTurn
from src.database.hardening_models import (
    ClaimAssignment, ClaimDecision, ClaimNote, ClaimAuditEvent, CopilotAnalysis,
    ClaimEvidenceRequest, ClaimEvidence, ClaimFact, ClaimRequirement, ClaimException,
)
from src.database.claim_workflow import transition_claim, build_submission_readiness
from src.database.session import get_db
from src.agents.llm_factory import get_configured_llm
from src.knowledge.retriever import KnowledgeRetriever

router = APIRouter(prefix="/api/v1/adjuster", tags=["Adjuster"])

# Shared dependency for endpoints using Depends(); also used by _resolve_adjuster below.
_guard = require_role(["ADJUSTER", "ADMIN"])

def _auto_assign_pending(claims:list[Claim], db:Session):
    changed=False
    for c in claims:
        state=dict(c.pipeline_state or {})
        if c.status not in {"submitted","pending_adjuster"}:
            continue
        active = db.query(ClaimAssignment).filter(
            ClaimAssignment.claim_id == c.id, ClaimAssignment.is_active.is_(True)
        ).first()
        if active:
            continue
        readiness = build_submission_readiness(db, c, state.get("policy_verification") or {})
        if not readiness.get("ready"):
            continue
        spec=(c.insurance_type or "").lower()
        a=db.query(Adjuster).filter(Adjuster.is_active==True,Adjuster.specialization==spec).order_by(Adjuster.claims_assigned.asc(),Adjuster.name.asc()).first()
        if not a:
            a=db.query(Adjuster).filter(Adjuster.is_active==True).order_by(Adjuster.claims_assigned.asc(),Adjuster.name.asc()).first()
        if a:
            a.claims_assigned=(a.claims_assigned or 0)+1
            db.add(ClaimAssignment(tenant_id=str(c.tenant_id), claim_id=c.id, adjuster_id=a.id, assigned_by=None, reason="readiness_then_specialization_then_load"))
            state["assigned_adjuster_id"]=str(a.id)
            state["assigned_adjuster_name"]=a.name
            c.pipeline_state=state
            if c.status == "submitted":
                c.status="pending_adjuster"
            changed=True
    if changed:
        db.commit()

def _can_access_claim(c: Claim, user: User, db: Session | None = None) -> bool:
    if user.role == "ADMIN":
        return True
    assigned_adj_id = str((c.pipeline_state or {}).get("assigned_adjuster_id") or "")
    if assigned_adj_id and assigned_adj_id in {str(user.id)}:
        return True
    if db is not None:
        adjuster = db.query(Adjuster).filter(Adjuster.email == user.email).first()
        if adjuster:
            if assigned_adj_id and assigned_adj_id == str(adjuster.id):
                return True
            if db.query(ClaimAssignment).filter(
                ClaimAssignment.claim_id == c.id,
                ClaimAssignment.adjuster_id == adjuster.id,
            ).first():
                return True
        if db.query(ClaimAssignment).filter(
            ClaimAssignment.claim_id == c.id,
            ClaimAssignment.adjuster_id == user.id,
        ).first():
            return True
    return False



def _resolve_adjuster(request: Request, db: Session) -> User:
    """Authenticate caller and assert ADJUSTER or ADMIN role."""
    return resolve_bearer_user(request, db, ["ADJUSTER", "ADMIN"])

def _ensure_assigned_adjuster(claim: Claim, user: User, db: Session) -> Adjuster:
    assigned_id = (claim.pipeline_state or {}).get("assigned_adjuster_id")
    if user.role == "ADMIN":
        a = db.query(Adjuster).filter(Adjuster.id == assigned_id).first() if assigned_id else None
        if not a:
            a = db.query(Adjuster).first()
        if a: return a
    adj = db.query(Adjuster).filter(Adjuster.email == user.email).first()
    if adj and (str(assigned_id) in {str(adj.id), str(user.id)}):
        return adj
    if adj and db.query(ClaimAssignment).filter(ClaimAssignment.claim_id == claim.id, ClaimAssignment.adjuster_id == adj.id).first():
        return adj
    if str(assigned_id) == str(user.id):
        a = db.query(Adjuster).filter(Adjuster.id == user.id).first()
        if a: return a
    if adj:
        return adj
    raise HTTPException(status_code=403, detail="This claim is not assigned to you.")

class ClaimUpdate(BaseModel):
    status: str|None=None
    priority: str|None=None
    note: str|None=Field(None,max_length=4000)

def _item(c: Claim, adjuster: Adjuster|None=None, db: Session|None=None)->dict[str,Any]:
    state=dict(c.pipeline_state or {})
    facts, requirements, evidence, exceptions, readiness = {}, [], [], [], {}
    if db is not None:
        facts = {str(row.fact_key): {"value": (row.value_json or {}).get("value"), "state": row.state, "source_type": row.source_type, "confidence": row.confidence, "version": row.version}
                 for row in db.query(ClaimFact).filter(ClaimFact.claim_id == c.id).all()}
        requirements = [{"key": row.requirement_key, "label": row.label, "status": row.status, "required": row.required, "evidence_type": row.evidence_type, "provenance": row.provenance_json or {}}
                        for row in db.query(ClaimRequirement).filter(ClaimRequirement.claim_id == c.id).all()]
        evidence = [{"id": str(row.id), "name": row.original_filename, "status": row.status, "verification_status": row.verification_status, "verification_confidence": row.verification_confidence, "requirement_id": str(row.requirement_id) if row.requirement_id else None}
                    for row in db.query(ClaimEvidence).filter(ClaimEvidence.claim_id == c.id).all()]
        exceptions = [{"id": str(row.id), "event_type": row.event_type, "severity": row.severity, "reason": row.reason, "blocking": row.blocking, "status": row.status}
                     for row in db.query(ClaimException).filter(ClaimException.claim_id == c.id, ClaimException.status == "open").all()]
        readiness = build_submission_readiness(db, c, state.get("policy_verification") or {})
    return {
        "ticket_id":c.ticket_id, "status":c.status, "insurance_type":c.insurance_type,
        "event_date":c.event_date.isoformat() if c.event_date else None, "event_location":c.event_location,
        "estimated_claim_amount":float(c.estimated_claim_amount) if c.estimated_claim_amount is not None else None,
        "priority":state.get("priority","normal"), "assigned_adjuster_id":state.get("assigned_adjuster_id"),
        "assigned_adjuster_name":adjuster.name if adjuster else state.get("assigned_adjuster_name"),
        "claimant_confirmed":bool(state.get("confirmed")),
        "policy_verified":bool((state.get("policy_verification") or {}).get("valid")),
        "dynamic_requirements_complete":not bool(state.get("dynamic_missing")),
        "facts": facts, "requirements": requirements, "evidence": evidence,
        "open_exceptions": exceptions, "submission_readiness": readiness,
        "updated_at":c.updated_at.isoformat() if c.updated_at else None,
    }

def _format_audit_row(r: ClaimAuditEvent) -> dict[str, Any]:
    """Serialise a ClaimAuditEvent to a response dict."""
    return {
        "id": r.id,
        "event_type": r.event_type,
        "actor_user_id": r.actor_user_id,
        "old_value": r.old_value_json,
        "new_value": r.new_value_json,
        "reason": r.reason,
        "created_at": r.created_at.isoformat(),
    }

@router.get("/queue")
def queue(status: str | None = None, user: User = Depends(_guard), db: Session = Depends(get_db)):
    valid_queue_statuses = [
        "submitted",
        "pending_adjuster",
        "assigned",
        "under_review",
        "pending_evidence",
        "approved",
        "partially_approved",
        "rejected",
        "escalated",
        "closed",
    ]
    if status and status.lower() != "all":
        q = db.query(Claim).filter(Claim.status == status.lower())
    else:
        q = db.query(Claim).filter(Claim.status.in_(valid_queue_statuses))

    claims = q.order_by(Claim.updated_at.desc()).all()
    if user.role == "ADJUSTER":
        adjuster = db.query(Adjuster).filter(Adjuster.email == user.email).first()
        assigned_ids = set()
        if adjuster:
            assigned_ids = {
                str(x.claim_id)
                for x in db.query(ClaimAssignment).filter(
                    ClaimAssignment.adjuster_id == adjuster.id
                ).all()
            }
        claims = [
            c
            for c in claims
            if str(c.id) in assigned_ids
            or (adjuster and str((c.pipeline_state or {}).get("assigned_adjuster_id")) in {str(adjuster.id), str(user.id)})
            or str((c.pipeline_state or {}).get("assigned_adjuster_id")) == str(user.id)
        ]
    return {"items": [_item(c, db=db) for c in claims], "total": len(claims)}

@router.get("/claims/{ticket_id}")
def claim_file(ticket_id: str, user: User = Depends(_guard), db: Session = Depends(get_db)):
    c = get_claim_or_404(db, ticket_id)
    if not _can_access_claim(c, user, db): raise HTTPException(status_code=403, detail="This claim is not assigned to you.")
    state=dict(c.pipeline_state or {})
    turns=db.query(ConversationTurn).filter(ConversationTurn.claim_id==c.id).order_by(ConversationTurn.turn_number,ConversationTurn.created_at).all()
    package = state.get("submission_package")
    if not package:
        from src.agents.submission_synthesizer import synthesize_claims_package
        package = synthesize_claims_package(state, db, c)
    return {
        "claim": _item(c, db=db),
        "extracted_data": state.get("extracted_data", {}),
        "conversation": [{"speaker": "Claimant" if t.speaker in {"user", "claimant"} else "Agent", "text": t.text, "turn": t.turn_number, "timestamp": t.created_at.isoformat() if t.created_at else None} for t in turns],
        "requirements": state.get("dynamic_requirements", []),
        "missing_requirements": state.get("dynamic_missing", []),
        "missing_evidence": state.get("missing_evidence", []),
        "evidence": state.get("evidence", []),
        "policy_verification": state.get("policy_verification", {}),
        "knowledge_sources": state.get("knowledge_sources", []),
        "copilot": state.get("copilot", {}),
        "copilot_chat": state.get("copilot_chat", []),
        "submission_package": package,
        "conversation_phase": state.get("conversation_phase", "1_baseline"),
        "gap_analysis": state.get("gap_analysis", {}),
    }

@router.post("/claims/{ticket_id}/exceptions/{exception_id}/resolve")
def resolve_exception(ticket_id: str, exception_id: str, request: Request, user: User = Depends(_guard), db: Session = Depends(get_db)):
    claim = get_claim_or_404(db, ticket_id)
    current_user = _resolve_adjuster(request, db)
    _ensure_assigned_adjuster(claim, current_user, db)
    row = db.query(ClaimException).filter(ClaimException.id == exception_id, ClaimException.claim_id == claim.id, ClaimException.status == "open").first()
    if not row:
        raise HTTPException(status_code=404, detail="Open claim exception not found.")
    row.status = "resolved"
    row.resolved_at = datetime.now(timezone.utc)
    row.resolution_json = {"resolved_by": str(current_user.id), "resolved_at": row.resolved_at.isoformat()}
    db.add(ClaimAuditEvent(tenant_id=str(claim.tenant_id), claim_id=str(claim.id), actor_user_id=str(current_user.id), event_type="exception_resolved",
                           new_value_json={"exception_id": str(row.id)}, reason="Adjuster resolved blocking exception"))
    db.commit()
    return {"success": True, "exception_id": str(row.id), "status": row.status}

@router.get("/claims/{ticket_id}/package")
def get_claim_package(ticket_id: str, user: User = Depends(_guard), db: Session = Depends(get_db)):
    c = get_claim_or_404(db, ticket_id)
    if not _can_access_claim(c, user, db): raise HTTPException(status_code=403, detail="This claim is not assigned to you.")
    state = dict(c.pipeline_state or {})
    package = state.get("submission_package")
    if not package:
        from src.agents.submission_synthesizer import synthesize_claims_package
        package = synthesize_claims_package(state, db, c)
    return package

@router.patch("/claims/{ticket_id}")
def update_claim(ticket_id: str, payload: ClaimUpdate, user: User = Depends(_guard), db: Session = Depends(get_db)):
    c = get_claim_or_404(db, ticket_id)
    if not _can_access_claim(c, user, db): raise HTTPException(status_code=403, detail="This claim is not assigned to you.")
    state=dict(c.pipeline_state or {})
    if payload.priority:
        if payload.priority not in {"low","normal","high","urgent"}:
            raise HTTPException(status_code=400, detail="Invalid priority.")
        state["priority"]=payload.priority
    if payload.note:
        db.add(ClaimNote(tenant_id=str(c.tenant_id), claim_id=str(c.id), author_user_id=str(user.id), note=payload.note, visibility="internal"))
    if payload.status:
        try:
            transition_claim(db, c, payload.status, str(user.id), "adjuster workflow update")
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
    c.pipeline_state=state
    db.add(ClaimAuditEvent(tenant_id=str(c.tenant_id), claim_id=str(c.id), actor_user_id=str(user.id), event_type="claim_updated",
                           new_value_json={"priority":state.get("priority"),"status":c.status}))
    db.commit(); db.refresh(c)
    return _item(c)

@router.post("/claims/{ticket_id}/assign")
def assign_claim(ticket_id: str, user: User = Depends(_guard), db: Session = Depends(get_db)):
    c = get_claim_or_404(db, ticket_id)
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
def evidence_url(ticket_id: str, evidence_id: str, user: User = Depends(_guard), db: Session = Depends(get_db)):
    claim = get_claim_or_404(db, ticket_id)
    if not _can_access_claim(claim,user,db): raise HTTPException(status_code=403,detail="This claim is not assigned to you.")
    state=dict(claim.pipeline_state or {})
    item=next((e for e in state.get("evidence",[]) if str(e.get("id"))==evidence_id),None)
    if not item or not item.get("s3_key"): raise HTTPException(status_code=404,detail="Evidence object not found.")
    from src.storage.s3 import presigned_get
    return {"url":presigned_get(item["s3_key"]),"expires_in":900}

@router.get("/claims/{ticket_id}/copilot")
def copilot(ticket_id: str, user: User = Depends(_guard), db: Session = Depends(get_db)):
    c = get_claim_or_404(db, ticket_id)
    if not _can_access_claim(c, user, db):
        raise HTTPException(status_code=403, detail="This claim is not assigned to you.")
    state = dict(c.pipeline_state or {})
    data = state.get("extracted_data") or {}
    context = {}
    try:
        context = KnowledgeRetriever().retrieve(
            insurance_type=c.insurance_type or "",
            policy_number=data.get("policy_id"),
            incident_date=c.event_date,
            query=c.event_description or "",
            claim_facts=data,
        )
    except Exception as exc:
        logger = __import__("logging").getLogger(__name__)
        logger.warning("Knowledge retrieval non-fatal error: %s", exc)

    requirements = context.get("requirements") or state.get("dynamic_requirements") or []
    evidence = state.get("evidence") or []
    missing = state.get("dynamic_missing") or []
    missing_evidence = state.get("missing_evidence") or []
    requests = [
        _request_payload(row, db)
        for row in db.query(ClaimEvidenceRequest)
        .filter(ClaimEvidenceRequest.claim_id == c.id)
        .order_by(ClaimEvidenceRequest.requested_at.desc())
        .all()
    ]
    source_rows = [*context.get("policy", []), *context.get("regulations", [])]

    prompt = f"""You are an insurance adjuster AI copilot and claim decision-support analyst.
Analyze this specific claim in detail and provide a full decision-support report along with actionable suggestions.
Use all supplied claim facts, evidence state, mandatory requirements, and retrieved policy/regulatory sources.
Every policy, coverage, deadline, exclusion, regulatory, or required-evidence statement must be grounded in the supplied retrieved sources. Do not invent or infer unsupported policy terms.
If mandatory evidence or authoritative policy verification is missing, do not treat that as an approval-ready condition; surface the missing basis and use REQUEST_EVIDENCE or ESCALATE as appropriate.
Keep the final claim decision with the human adjuster. Your role is evidence-grounded analysis, consistency checking, uncertainty identification, and actionable support.

Return a valid JSON object with EXACTLY this structure:
{{
  "executive_summary": "Comprehensive incident and claim summary with initial coverage evaluation",
  "decision_recommendation": "APPROVE | PARTIAL_APPROVE | REQUEST_EVIDENCE | REJECT | ESCALATE",
  "recommended_payout_amount": <numeric estimated approved payout amount or null>,
  "confidence_score": <float between 0.0 and 1.0, e.g. 0.85>,
  "decision_rationale": "Clear, grounded justification for this decision recommendation",
  "actionable_suggestions": [
    "Specific, prioritized suggestions for the adjuster (e.g. key verification points, clauses to cite, recommended follow-up questions or evidence to request)"
  ],
  "coverage_observations": [
    "Coverage observations grounded in policy type, limits, deductibles, and incident facts"
  ],
  "mandatory_requirements": [
    {{"label": "...", "status": "complete|missing|review", "condition": "..."}}
  ],
  "evidence_assessment": [
    "Assessment of what submitted evidence establishes, quality of evidence, and what remains missing"
  ],
  "risk_flags": [
    "Potential risk factors, inconsistencies, timing anomalies, or red flags"
  ],
  "regulatory_considerations": [
    "Applicable regulatory, compliance, or turnaround standards (IRDAI, fair settlement practices)"
  ],
  "decision_considerations": [
    "Key factors and trade-offs the adjuster should weigh before deciding"
  ],
  "recommended_next_steps": [
    "Specific sequence of follow-up steps"
  ],
  "uncertainties": [
    "Aspects that cannot yet be concluded with certainty"
  ]
}}
CLAIM FACTS:
{json.dumps(data, ensure_ascii=False, default=str)}
CLAIM STATUS: {c.status}
ESTIMATED AMOUNT: {c.estimated_claim_amount}
POLICY VERIFICATION:
{json.dumps(state.get("policy_verification") or {}, ensure_ascii=False, default=str)}
MANDATORY REQUIREMENTS:
{json.dumps(requirements, ensure_ascii=False, default=str)}
MISSING INFORMATION:
{json.dumps(missing, ensure_ascii=False, default=str)}
MISSING EVIDENCE:
{json.dumps(missing_evidence, ensure_ascii=False, default=str)}
SUBMITTED EVIDENCE:
{json.dumps(evidence, ensure_ascii=False, default=str)}
OPEN/RESPONDED ADJUSTER REQUESTS:
{json.dumps(requests, ensure_ascii=False, default=str)}
RETRIEVED POLICY/REGULATORY KNOWLEDGE:
{json.dumps(source_rows, ensure_ascii=False, default=str)}
"""

    try:
        result = get_configured_llm().invoke(prompt)
        raw = getattr(result, "content", str(result))
        parsed = None
        try:
            parsed = json.loads(raw)
        except Exception:
            match = re.search(r"\{.*\}", str(raw), re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            raise ValueError("Copilot returned an invalid report.")
        parsed.setdefault("executive_summary", "")
        parsed.setdefault("decision_recommendation", "REQUEST_EVIDENCE" if missing_evidence else "APPROVE")
        parsed.setdefault("recommended_payout_amount", float(c.estimated_claim_amount) if c.estimated_claim_amount is not None else None)
        parsed.setdefault("confidence_score", 0.85)
        parsed.setdefault("decision_rationale", "")
        parsed.setdefault("actionable_suggestions", [])
        parsed.setdefault("coverage_observations", [])
        parsed.setdefault("mandatory_requirements", [])
        parsed.setdefault("evidence_assessment", [])
        parsed.setdefault("risk_flags", [])
        parsed.setdefault("regulatory_considerations", [])
        parsed.setdefault("decision_considerations", [])
        parsed.setdefault("recommended_next_steps", [])
        parsed.setdefault("uncertainties", [])

        state["copilot"] = parsed
        state["knowledge_sources"] = source_rows

        # If copilot chat has no messages yet, seed it with a helpful assistant message
        existing_chat = list(state.get("copilot_chat") or [])
        if not existing_chat:
            rec = parsed.get("decision_recommendation", "REVIEW").replace("_", " ").title()
            payout = parsed.get("recommended_payout_amount")
            payout_str = f" · Suggested Payout: ₹{payout:,.2f}" if payout is not None else ""
            suggs = parsed.get("actionable_suggestions", [])
            sugg_bullets = "\n".join(f"• {s}" for s in suggs[:3]) if suggs else "• Review verified claim facts and submitted evidence against policy guidelines."
            welcome_msg = (
                f"Hello! I have completed my decision analysis for Claim #{ticket_id}.\n\n"
                f"**Preliminary Recommendation:** {rec}{payout_str}\n\n"
                f"**Key Suggestions for You:**\n{sugg_bullets}\n\n"
                f"Feel free to ask me questions regarding coverage terms, evidence validity, claim inconsistencies, or request draft evidence text for the claimant."
            )
            existing_chat = [
                {
                    "id": str(uuid.uuid4()),
                    "speaker": "copilot",
                    "message": welcome_msg,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            ]
        state["copilot_chat"] = existing_chat
        c.pipeline_state = state
        db.add(CopilotAnalysis(
            claim_id=str(c.id),
            claim_version=1,
            knowledge_version="retrieval-current",
            model=settings.CLOUD_LLM_MODEL,
            prompt_version="v3",
            result_json=parsed,
            citations_json=source_rows,
        ))
        db.commit()
        return {"ticket_id": ticket_id, "analysis": parsed, "status": "ready", "sources": source_rows, "chat": state["copilot_chat"]}
    except Exception as exc:
        logger = __import__("logging").getLogger(__name__)
        logger.warning("Copilot report unavailable for %s: %s", ticket_id, exc)
        return {
            "ticket_id": ticket_id,
            "analysis": None,
            "status": "unavailable",
            "error": "AI provider is temporarily unavailable. Retry Copilot shortly.",
            "sources": source_rows,
            "chat": state.get("copilot_chat") or [],
        }

class CopilotChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)

@router.post("/claims/{ticket_id}/copilot/chat")
def copilot_chat(ticket_id: str, payload: CopilotChatRequest, user: User = Depends(_guard), db: Session = Depends(get_db)):
    c = get_claim_or_404(db, ticket_id)
    if not _can_access_claim(c, user, db):
        raise HTTPException(status_code=403, detail="This claim is not assigned to you.")
    state = dict(c.pipeline_state or {})
    context = {}
    try:
        context = KnowledgeRetriever().retrieve(
            insurance_type=c.insurance_type or "",
            policy_number=(state.get("extracted_data") or {}).get("policy_id"),
            incident_date=c.event_date,
            query=c.event_description or "",
            claim_facts=state.get("extracted_data") or {},
        )
    except Exception as exc:
        logger = __import__("logging").getLogger(__name__)
        logger.warning("Knowledge retrieval non-fatal error: %s", exc)

    full_history = list(state.get("copilot_chat") or [])
    recent_history = full_history[-8:]
    source_rows = [*context.get("policy", []), *context.get("regulations", [])]

    prompt = f"""You are the insurance adjuster's interactive AI Copilot Chatbot for Claim #{ticket_id}.
You are the adjuster-side AI Copilot chatbot. You support the assigned human adjuster only; you are not the claimant chatbot and must never address the claimant as though you were the claimant-facing assistant. You act as an experienced, sharp, and helpful claim adjudication advisor.
You are discussing this specific claim with the assigned adjuster.

Claim Context:
- Status: {c.status}
- Insurance Type: {c.insurance_type}
- Event Date: {c.event_date}
- Estimated Amount: {c.estimated_claim_amount}
- Facts: {json.dumps(state.get("extracted_data") or {}, ensure_ascii=False, default=str)}
- Evidence Items: {json.dumps(state.get("evidence") or [], ensure_ascii=False, default=str)}
- Missing Requirements: {json.dumps(state.get("missing_evidence") or state.get("dynamic_missing") or [], ensure_ascii=False, default=str)}
- Initial Decision Report: {json.dumps(state.get("copilot") or {}, ensure_ascii=False, default=str)}
- Knowledge & Regulations: {json.dumps(source_rows, ensure_ascii=False, default=str)}

Recent Conversation History:
{json.dumps(recent_history, ensure_ascii=False, default=str)}

Adjuster's Question/Message:
{payload.message}

Instructions:
- Provide clear, direct, and actionable advice tailored to this claim.
- If the adjuster asks for draft evidence request text or communication with the claimant, provide ready-to-copy drafts.
- If asked about payout, deductibles, or policy clauses, explain the rationale clearly based on the claim facts.
- Use professional yet approachable tone formatted with clear markdown (bullet points, bold text).
"""
    try:
        result = get_configured_llm().invoke(prompt)
        answer = getattr(result, "content", str(result)).strip()
        if not answer:
            raise ValueError("Empty Copilot response.")
    except Exception as exc:
        logger = __import__("logging").getLogger(__name__)
        logger.warning("Copilot chat invocation failed: %s", exc)
        raise HTTPException(status_code=503, detail="AI provider is temporarily unavailable. Retry Copilot chat shortly.")

    user_msg = {
        "id": str(uuid.uuid4()),
        "speaker": "adjuster",
        "message": payload.message,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    bot_msg = {
        "id": str(uuid.uuid4()),
        "speaker": "copilot",
        "message": answer,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    chat = full_history + [user_msg, bot_msg]
    state["copilot_chat"] = chat
    c.pipeline_state = state
    db.commit()
    return {"ticket_id": ticket_id, "answer": answer, "chat": chat, "sources": source_rows}



class EvidenceRequestCreate(BaseModel):
    request_text: str = Field(..., min_length=5, max_length=4000)

def _request_payload(row: ClaimEvidenceRequest, db: Session) -> dict[str, Any]:
    evidence = db.query(ClaimEvidence).filter(ClaimEvidence.request_id == row.id).order_by(ClaimEvidence.created_at.desc()).first()
    return {
        "id": str(row.id),
        "claim_id": str(row.claim_id),
        "adjuster_id": str(row.adjuster_id),
        "request_text": row.request_text,
        "status": row.status,
        "response_note": row.response_note,
        "requested_at": row.requested_at.isoformat() if row.requested_at else None,
        "responded_at": row.responded_at.isoformat() if row.responded_at else None,
        "response_evidence": {
            "id": str(evidence.id),
            "name": evidence.original_filename,
            "verification_status": evidence.verification_status,
        } if evidence else None,
    }

@router.post("/claims/{ticket_id}/evidence-requests")
def create_evidence_request(ticket_id: str, payload: EvidenceRequestCreate, user: User = Depends(_guard), db: Session = Depends(get_db)):
    c = get_claim_or_404(db, ticket_id)
    adjuster = _ensure_assigned_adjuster(c, user, db)
    if c.status in {"approved", "partially_approved", "rejected", "closed"}:
        raise HTTPException(status_code=409, detail="Evidence cannot be requested after a final claim outcome.")
    row = ClaimEvidenceRequest(tenant_id=str(c.tenant_id), claim_id=str(c.id), adjuster_id=str(adjuster.id), request_text=payload.request_text.strip(), status="open")
    db.add(row)
    if c.status in {"submitted", "assigned", "under_review"}:
        transition_claim(db, c, "pending_evidence", str(user.id), "adjuster requested additional evidence")
    db.add(ClaimAuditEvent(
        claim_id=str(c.id), actor_user_id=str(user.id), event_type="evidence_requested",
        new_value_json={"request_id": str(row.id), "request_text": row.request_text}, reason=row.request_text
    ))
    db.commit()
    db.refresh(row)
    return _request_payload(row, db)

@router.get("/claims/{ticket_id}/evidence-requests")
def list_evidence_requests(ticket_id: str, user: User = Depends(_guard), db: Session = Depends(get_db)):
    c = get_claim_or_404(db, ticket_id)
    _ensure_assigned_adjuster(c, user, db)
    rows = db.query(ClaimEvidenceRequest).filter(ClaimEvidenceRequest.claim_id == c.id).order_by(ClaimEvidenceRequest.requested_at.desc()).all()
    return [_request_payload(row, db) for row in rows]

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
    claim = get_claim_or_404(db, ticket_id)
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
    claim = get_claim_or_404(db, ticket_id)
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
        tenant_id=str(c.tenant_id),
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
    claim = get_claim_or_404(db, ticket_id)
    _ensure_assigned_adjuster(claim, current_user, db)
    note = ClaimNote(tenant_id=str(claim.tenant_id), claim_id=str(claim.id), author_user_id=str(current_user.id),
                     note=payload.note, visibility=payload.visibility)
    db.add(note)
    db.add(ClaimAuditEvent(tenant_id=str(claim.tenant_id), claim_id=str(claim.id), actor_user_id=str(current_user.id),
                           event_type="note_added", new_value_json={"note_id": note.id}))
    db.commit()
    return {"id": note.id, "created_at": note.created_at.isoformat(), "visibility": note.visibility}

@router.get("/claims/{ticket_id}/audit")
def get_claim_audit(ticket_id: str, request: Request, db: Session = Depends(get_db)):
    current_user = _resolve_adjuster(request, db)
    claim = get_claim_or_404(db, ticket_id)
    _ensure_assigned_adjuster(claim, current_user, db)
    rows = db.query(ClaimAuditEvent).filter(ClaimAuditEvent.claim_id == claim.id).order_by(ClaimAuditEvent.created_at.asc()).all()
    return [_format_audit_row(r) for r in rows]
