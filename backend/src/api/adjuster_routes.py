"""Authenticated adjuster workbench API."""
from __future__ import annotations

import asyncio
from typing import Any
import json
import re
import uuid
import hashlib
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy import func, select
from datetime import datetime, timezone
from src.api.deps import require_role, resolve_bearer_user, get_claim_or_404, serialize_evidence_request as _request_payload
from src.config import settings
from src.database.models import Claim, Adjuster, User, ConversationTurn, Policy
from src.database.hardening_models import (
    ClaimAssignment, ClaimDecision, ClaimNote, ClaimAuditEvent, CopilotAnalysis,
    ClaimEvidenceRequest, ClaimEvidence, ClaimFact, ClaimRequirement, ClaimException,
)
from src.database.claim_workflow import transition_claim, build_submission_readiness
from src.database.session import get_db
from src.agents.llm_factory import get_configured_llm
from src.knowledge.retriever import KnowledgeRetriever
from src.services.ai_governance import tenant_ai_guard
from src.services.audit import append_system_audit

router = APIRouter(prefix="/api/v1/adjuster", tags=["Adjuster"])

# Shared dependency for endpoints using Depends(); also used by _resolve_adjuster below.
_guard = require_role(["ADJUSTER", "ADMIN"])

def _can_access_claim(c: Claim, user: User, db: Session | None = None) -> bool:
    claim_tenant = str(getattr(c, "tenant_id", "") or "").strip()
    user_tenant = str(getattr(user, "tenant_id", "") or "").strip()
    if not claim_tenant or not user_tenant or claim_tenant != user_tenant:
        return False
    if user.role == "ADMIN":
        return True

    assigned_adj_id = str((c.pipeline_state or {}).get("assigned_adjuster_id") or "")
    if assigned_adj_id and assigned_adj_id in {str(user.id)}:
        return True

    adj_ids = {str(user.id)}
    if db is not None:
        adjuster = db.query(Adjuster).filter(
            (Adjuster.user_id == user.id) | (Adjuster.id == user.id),
            Adjuster.tenant_id == c.tenant_id,
        ).first()
        if adjuster:
            adj_ids.add(str(adjuster.id))
            if assigned_adj_id and assigned_adj_id == str(adjuster.id):
                return True
            if db.query(ClaimAssignment).filter(
                ClaimAssignment.claim_id == c.id,
                ClaimAssignment.tenant_id == c.tenant_id,
                ClaimAssignment.adjuster_id == adjuster.id,
                ClaimAssignment.is_active.is_(True),
            ).first():
                return True
        if db.query(ClaimAssignment).filter(
            ClaimAssignment.claim_id == c.id,
            ClaimAssignment.tenant_id == c.tenant_id,
            ClaimAssignment.adjuster_id == user.id,
            ClaimAssignment.is_active.is_(True),
        ).first():
            return True

    # If assigned to another adjuster in pipeline_state, deny
    if assigned_adj_id and assigned_adj_id not in adj_ids:
        return False

    if not assigned_adj_id and getattr(c, "status", None) in {"submitted", "verified", "pending_adjuster", "assigned"}:
        return True
    return False



def _resolve_adjuster(request: Request, db: Session) -> User:
    """Authenticate caller and assert ADJUSTER or ADMIN role."""
    return resolve_bearer_user(request, db, ["ADJUSTER", "ADMIN"])

def _ensure_assigned_adjuster(claim: Claim, user: User, db: Session) -> Adjuster:
    assigned_id = (claim.pipeline_state or {}).get("assigned_adjuster_id")
    if user.role == "ADMIN":
        a = db.query(Adjuster).filter(Adjuster.id == assigned_id, Adjuster.tenant_id == claim.tenant_id).first() if assigned_id else None
        if not a:
            a = db.query(Adjuster).filter(Adjuster.tenant_id == claim.tenant_id).first()
        if a: return a
    adj = db.query(Adjuster).filter(Adjuster.user_id == user.id, Adjuster.tenant_id == claim.tenant_id).first()
    if not adj:
        adj = db.query(Adjuster).filter(Adjuster.id == user.id, Adjuster.tenant_id == claim.tenant_id).first()
    if adj:
        assigned_str = str(assigned_id) if assigned_id else ""
        if assigned_str and (assigned_str in {str(adj.id), str(user.id)}):
            return adj
        if db.query(ClaimAssignment).filter(
            ClaimAssignment.claim_id == claim.id,
            ClaimAssignment.tenant_id == claim.tenant_id,
            ClaimAssignment.adjuster_id == adj.id
        ).first():
            return adj
    if str(assigned_id) == str(user.id):
        a = db.query(Adjuster).filter(
            Adjuster.id == user.id,
            Adjuster.tenant_id == claim.tenant_id,
            Adjuster.is_active.is_(True),
        ).first()
        if a:
            return a
    raise HTTPException(status_code=403, detail="This claim is not assigned to you.")

class ClaimUpdate(BaseModel):
    status: str|None=None
    priority: str|None=None
    note: str|None=Field(None,max_length=4000)

def _item(c: Claim, adjuster: Adjuster|None=None, db: Session|None=None)->dict[str,Any]:
    state=dict(c.pipeline_state or {})
    facts, requirements, evidence, exceptions, readiness = {}, [], [], [], {}
    if db is not None:
        facts = {row.fact_key: {"value": (row.value_json or {}).get("value"), "state": row.state, "source_type": row.source_type, "confidence": row.confidence, "version": row.version}
                 for row in db.query(ClaimFact).filter(ClaimFact.claim_id == c.id, ClaimFact.tenant_id == c.tenant_id).all()}
        requirements = [{"key": row.requirement_key, "label": row.label, "status": row.status, "required": row.required, "evidence_type": row.evidence_type, "provenance": row.provenance_json or {}}
                        for row in db.query(ClaimRequirement).filter(ClaimRequirement.claim_id == c.id, ClaimRequirement.tenant_id == c.tenant_id).all()]
        evidence = [{"id": row.id, "name": row.original_filename, "status": row.status, "verification_status": row.verification_status, "verification_confidence": row.verification_confidence, "requirement_id": row.requirement_id}
                    for row in db.query(ClaimEvidence).filter(ClaimEvidence.claim_id == c.id, ClaimEvidence.tenant_id == c.tenant_id).all()]
        exceptions = [{"id": row.id, "event_type": row.event_type, "severity": row.severity, "reason": row.reason, "blocking": row.blocking, "status": row.status}
                     for row in db.query(ClaimException).filter(ClaimException.claim_id == c.id, ClaimException.tenant_id == c.tenant_id, ClaimException.status == "open").all()]
        readiness = build_submission_readiness(db, c, state.get("policy_verification") or {})

    policyholder = None
    if c.policy_id and db is not None:
        p = db.query(Policy).filter(Policy.id == c.policy_id).first()
        if p and p.policyholder_name:
            policyholder = p.policyholder_name
    if not policyholder:
        policyholder = (state.get("extracted_data") or {}).get("policyholder_name")
    if not policyholder and db is not None:
        pol_num = (state.get("extracted_data") or {}).get("policy_id")
        if pol_num:
            p = db.query(Policy).filter(Policy.policy_number == str(pol_num).strip().upper(), Policy.tenant_id == c.tenant_id).first()
            if p and p.policyholder_name:
                policyholder = p.policyholder_name
    if not policyholder and c.customer_id and db is not None:
        u = db.query(User).filter(User.id == c.customer_id).first()
        if u and u.full_name:
            policyholder = u.full_name

    return {
        "id": str(c.id),
        "ticket_id": c.ticket_id,
        "status": c.status,
        "insurance_type": c.insurance_type,
        "policyholder_name": policyholder or "Claimant",
        "customer_id": policyholder or "Claimant",
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "event_date": c.event_date.isoformat() if c.event_date else None,
        "event_location": c.event_location,
        "estimated_claim_amount": float(c.estimated_claim_amount) if c.estimated_claim_amount is not None else None,
        "priority": state.get("priority", "normal"),
        "assigned_adjuster_id": state.get("assigned_adjuster_id"),
        "assigned_adjuster_name": adjuster.name if adjuster else state.get("assigned_adjuster_name"),
        "claimant_confirmed": bool(state.get("confirmed")),
        "final_submission_confirmed": bool(state.get("final_submission_confirmed")),
        "policy_verified": bool((state.get("policy_verification") or {}).get("valid")),
        "dynamic_requirements_complete": not bool(state.get("dynamic_missing")),
        "facts": facts,
        "requirements": requirements,
        "evidence": evidence,
        "open_exceptions": exceptions,
        "submission_readiness": readiness,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
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

def _get_adjuster_relevant_claims(
    db: Session,
    user: User,
    tenant_id: str,
    statuses: list[str] | None = None,
    scope: str = "assigned",
) -> tuple[list[Claim], set[str]]:
    """
    Returns (relevant_claims, assigned_claim_ids) for the given user (Adjuster or Admin).
    Ensures strict type-safety across UUIDs/strings and consistency between Dashboard and Queue.
    When scope == 'assigned' (default), adjusters receive ONLY claims assigned to them.
    When scope == 'unassigned', adjusters receive unassigned claims awaiting adjudication.
    Admins retain oversight across the tenant.
    """
    q = db.query(Claim).filter(Claim.tenant_id == tenant_id)
    if statuses:
        q = q.filter(Claim.status.in_(statuses))
    all_claims = q.order_by(Claim.updated_at.desc()).all()

    if user.role == "ADMIN":
        assigned_ids = {str(c.id) for c in all_claims}
        if scope == "unassigned":
            # For admin inspecting unassigned claims
            active_assigned_ids = {
                str(row.claim_id)
                for row in db.query(ClaimAssignment.claim_id).filter(
                    ClaimAssignment.tenant_id == tenant_id,
                    ClaimAssignment.is_active.is_(True),
                ).all()
            }
            unassigned_claims = [
                c for c in all_claims
                if str(c.id) not in active_assigned_ids and not (c.pipeline_state or {}).get("assigned_adjuster_id")
            ]
            return unassigned_claims, assigned_ids
        return all_claims, assigned_ids

    adj_ids = {str(user.id)}
    adjusters = db.query(Adjuster).filter(
        (Adjuster.user_id == user.id) | (Adjuster.id == user.id),
        Adjuster.tenant_id == tenant_id,
        Adjuster.is_active.is_(True),
    ).all()
    for a in adjusters:
        adj_ids.add(str(a.id))

    # Active assignments for THIS adjuster in the DB
    my_assigned_claim_ids = {
        str(row.claim_id)
        for row in db.query(ClaimAssignment.claim_id).filter(
            ClaimAssignment.adjuster_id.in_(list(adj_ids)),
            ClaimAssignment.tenant_id == tenant_id,
            ClaimAssignment.is_active.is_(True),
        ).all()
    }

    # Active assignments for OTHER adjusters in the DB
    other_assigned_claim_ids = {
        str(row.claim_id)
        for row in db.query(ClaimAssignment.claim_id).filter(
            ~ClaimAssignment.adjuster_id.in_(list(adj_ids)),
            ClaimAssignment.tenant_id == tenant_id,
            ClaimAssignment.is_active.is_(True),
        ).all()
    }

    relevant_claims = []
    assigned_claim_ids = set()

    for c in all_claims:
        cid_str = str(c.id)
        assigned_to_state = str((c.pipeline_state or {}).get("assigned_adjuster_id") or "")

        # Is this claim assigned to THIS adjuster?
        is_assigned_to_me = (cid_str in my_assigned_claim_ids) or (
            bool(assigned_to_state) and (assigned_to_state in adj_ids) and (cid_str not in other_assigned_claim_ids)
        )

        # Is this claim assigned to ANOTHER adjuster?
        is_assigned_to_other = (cid_str in other_assigned_claim_ids) or (
            bool(assigned_to_state) and (assigned_to_state not in adj_ids) and (cid_str not in my_assigned_claim_ids)
        )

        # Is this claim unassigned?
        is_unassigned = not is_assigned_to_me and not is_assigned_to_other

        if is_assigned_to_me:
            assigned_claim_ids.add(cid_str)

        if scope == "assigned":
            if is_assigned_to_me:
                relevant_claims.append(c)
        elif scope == "unassigned":
            if is_unassigned:
                relevant_claims.append(c)
        elif scope == "all":
            if is_assigned_to_me:
                relevant_claims.append(c)

    return relevant_claims, assigned_claim_ids

@router.get("/dashboard")
def dashboard(user: User = Depends(_guard), db: Session = Depends(get_db)):
    """Return adjuster-facing operational metrics and recent assigned claims."""
    tenant_id = str(user.tenant_id or "")
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context is required.")

    total_filed = db.query(func.count(Claim.id)).filter(
        Claim.tenant_id == tenant_id,
        Claim.status.in_({
            "submitted", "verified", "pending_adjuster", "assigned", "under_review",
            "pending_evidence", "approved", "partially_approved",
            "rejected", "escalated", "closed",
        }),
    ).scalar() or 0
    total_users = db.query(func.count(User.id)).filter(
        User.tenant_id == tenant_id,
        User.status == "active",
    ).scalar() or 0

    assigned_claims, assigned_ids = _get_adjuster_relevant_claims(db, user, tenant_id, scope="assigned")

    now = datetime.now(timezone.utc)
    sla_hours = int(getattr(settings, "CLAIM_SLA_HOURS", 72))
    active_statuses = {"submitted", "verified", "pending_adjuster", "assigned", "under_review", "pending_evidence", "escalated"}
    under_review = sum(1 for c in assigned_claims if c.status == "under_review")
    pending_evidence = sum(1 for c in assigned_claims if c.status == "pending_evidence")
    sla_breached = 0
    for c in assigned_claims:
        updated = c.updated_at
        updated_utc = updated.replace(tzinfo=timezone.utc) if updated and updated.tzinfo is None else updated
        age_hours = (now - updated_utc).total_seconds() / 3600.0 if updated_utc else 0.0
        if age_hours > sla_hours and c.status in active_statuses:
            sla_breached += 1

    recent = []
    for c in assigned_claims[:8]:
        item = _item(c, db=db)
        updated = c.updated_at
        updated_utc = updated.replace(tzinfo=timezone.utc) if updated and updated.tzinfo is None else updated
        age_hours = round(max(0.0, (now - updated_utc).total_seconds() / 3600.0), 2) if updated_utc else 0.0
        item.update({
            "age_hours": age_hours,
            "sla_hours": sla_hours,
            "sla_breached": age_hours > sla_hours and c.status in active_statuses,
        })
        recent.append(item)

    return {
        "total_filed_claims": int(total_filed),
        "total_users": int(total_users),
        "assigned_to_me": len(assigned_ids) if user.role == "ADJUSTER" else len(assigned_claims),
        "under_review": under_review,
        "pending_evidence": pending_evidence,
        "sla_breached": sla_breached,
        "queue_total": len(assigned_claims),
        "recent_claims": recent,
    }

@router.get("/queue")
def queue(
    status: str | None = None,
    scope: str = "assigned",
    user: User = Depends(_guard),
    db: Session = Depends(get_db),
):
    """Return tenant-scoped claims with SLA/aging metadata, scoped to caller's assignment or unassigned pool."""
    valid_queue_statuses = [
        "submitted", "verified", "pending_adjuster", "assigned", "under_review",
        "pending_evidence", "approved", "partially_approved", "rejected", "escalated", "closed",
    ]
    requested = status.lower() if status else "all"
    if requested != "all" and requested not in valid_queue_statuses:
        raise HTTPException(status_code=400, detail="Invalid queue status.")
    statuses = valid_queue_statuses if requested == "all" else [requested]

    valid_scopes = {"assigned", "unassigned", "all"}
    scope_clean = scope.lower().strip() if scope else "assigned"
    if scope_clean not in valid_scopes:
        scope_clean = "assigned"

    claims, _ = _get_adjuster_relevant_claims(db, user, user.tenant_id, statuses, scope=scope_clean)

    now = datetime.now(timezone.utc)
    sla_hours = int(getattr(settings, "CLAIM_SLA_HOURS", 72))
    items = []
    for claim in claims:
        updated = claim.updated_at
        updated_utc = updated.replace(tzinfo=timezone.utc) if updated and updated.tzinfo is None else updated
        age_hours = round(max(0.0, (now - updated_utc).total_seconds() / 3600.0), 2) if updated_utc else 0.0
        item = _item(claim, db=db)
        item.update({
            "age_hours": age_hours,
            "sla_hours": sla_hours,
            "sla_breached": age_hours > sla_hours and claim.status not in {"approved","rejected","closed"},
            "next_action": (
                "review_evidence" if claim.status == "pending_evidence"
                else "make_decision" if claim.status == "under_review"
                else "open_claim"
            ),
        })
        items.append(item)
    return {
        "items": items,
        "total": len(items),
        "queue_counts": {s: sum(1 for claim in claims if claim.status == s) for s in valid_queue_statuses},
    }


@router.get("/next-claim")
def next_claim(user: User = Depends(_guard), db: Session = Depends(get_db)):
    """Return the oldest active assignment for deterministic next-claim processing."""
    if user.role != "ADJUSTER":
        raise HTTPException(status_code=403, detail="Next-claim workflow is for adjusters.")
    adjuster = db.query(Adjuster).filter(
        Adjuster.user_id == user.id,
        Adjuster.tenant_id == user.tenant_id,
        Adjuster.is_active.is_(True),
    ).first()
    if not adjuster:
        raise HTTPException(status_code=403, detail="Active adjuster profile not found.")
    assignment = db.query(ClaimAssignment).filter(
        ClaimAssignment.adjuster_id == adjuster.id,
        ClaimAssignment.tenant_id == user.tenant_id,
        ClaimAssignment.is_active.is_(True),
    ).order_by(ClaimAssignment.assigned_at.asc()).first()
    if not assignment:
        return {"claim": None}
    claim = db.query(Claim).filter(
        Claim.id == assignment.claim_id,
        Claim.tenant_id == user.tenant_id,
    ).first()
    return {"claim": _item(claim, adjuster, db) if claim else None}


@router.get("/claims/{ticket_id}")
def claim_file(ticket_id: str, request: Request, user: User = Depends(_guard), db: Session = Depends(get_db)):
    c = get_claim_or_404(db, ticket_id)
    if str(c.tenant_id) != str(user.tenant_id):
        raise HTTPException(status_code=404, detail="Claim not found.")
    if not _can_access_claim(c, user, db): raise HTTPException(status_code=403, detail="This claim is not assigned to you.")

    etag = f'"{hashlib.sha256(f"{c.updated_at}_{c.status}".encode("utf-8")).hexdigest()[:16]}"'
    if_none_match = request.headers.get("if-none-match")
    if if_none_match and if_none_match.strip() == etag:
        return Response(status_code=304, headers={"ETag": etag})
    state=dict(c.pipeline_state or {})
    turns=db.query(ConversationTurn).filter(ConversationTurn.claim_id==c.id).order_by(ConversationTurn.turn_number,ConversationTurn.created_at).all()
    package = state.get("submission_package")
    if not package:
        from src.agents.submission_synthesizer import synthesize_claims_package
        package = synthesize_claims_package(state, db, c)
    extracted = state.get("extracted_data", {})
    policy_number = extracted.get("policy_id")
    policy = db.query(Policy).filter(
        Policy.tenant_id == user.tenant_id,
        Policy.policy_number == str(policy_number or "").strip().upper(),
    ).first() if policy_number else None
    policy_payload = None
    if policy:
        policy_payload = {
            "id": str(policy.id),
            "policy_number": policy.policy_number,
            "policy_type": policy.policy_type,
            "coverage_amount": float(policy.coverage_amount or 0),
            "deductible": float(policy.deductible or 0),
            "effective_date": policy.effective_date.isoformat() if policy.effective_date else None,
            "expiry_date": policy.expiry_date.isoformat() if policy.expiry_date else None,
            "is_active": bool(policy.is_active),
            "policyholder_name": policy.policyholder_name,
        }

    # Query notes for claim
    note_rows = (
        db.query(ClaimNote)
        .filter(ClaimNote.claim_id == c.id, ClaimNote.tenant_id == c.tenant_id)
        .order_by(ClaimNote.created_at.desc())
        .all()
    )
    notes_payload = []
    for n in note_rows:
        author_name = getattr(n, "author_role", None)
        if not author_name and getattr(n, "author_user_id", None):
            try:
                au = db.query(User).filter(User.id == n.author_user_id).first()
                if au:
                    author_name = au.full_name or au.email
            except Exception:
                author_name = None
        notes_payload.append({
            "id": str(n.id),
            "author": author_name or "Adjuster",
            "note": n.note,
            "visibility": n.visibility,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        })

    # Query evidence requests
    req_rows = (
        db.query(ClaimEvidenceRequest)
        .filter(ClaimEvidenceRequest.claim_id == c.id, ClaimEvidenceRequest.tenant_id == c.tenant_id)
        .order_by(ClaimEvidenceRequest.requested_at.desc())
        .all()
    )
    evidence_requests_payload = [_request_payload(r, db) for r in req_rows]

    # Merge DB ClaimEvidence rows missing from pipeline_state["evidence"]
    evidence_list = list(state.get("evidence") or [])
    existing_keys = {e.get("s3_key") or e.get("object_key") or str(e.get("id")) for e in evidence_list}
    db_evidences = (
        db.query(ClaimEvidence)
        .filter(ClaimEvidence.claim_id == c.id, ClaimEvidence.tenant_id == c.tenant_id)
        .all()
    )
    for dbev in db_evidences:
        obj_key = getattr(dbev, "object_key", None) or getattr(dbev, "s3_key", None)
        if obj_key not in existing_keys and str(dbev.id) not in existing_keys:
            analysis = getattr(dbev, "analysis_json", None) or {}
            ver_block = analysis.get("verification") if isinstance(analysis.get("verification"), dict) else analysis
            evidence_list.append({
                "id": str(dbev.id),
                "name": getattr(dbev, "original_filename", None) or getattr(dbev, "filename", "evidence"),
                "s3_uri": getattr(dbev, "s3_uri", None) or obj_key,
                "s3_key": obj_key,
                "content_type": dbev.content_type,
                "size": getattr(dbev, "size_bytes", None) or getattr(dbev, "file_size_bytes", None),
                "status": dbev.status,
                "verification_status": dbev.verification_status,
                "verification_confidence": dbev.verification_confidence,
                "detected_document_type": dbev.detected_document_type,
                "extracted_fields": getattr(dbev, "extracted_fields", None) or (ver_block.get("extracted_fields") if isinstance(ver_block, dict) else {}) or {},
                "verification_reason": getattr(dbev, "verification_reason", None) or (ver_block.get("reason") if isinstance(ver_block, dict) else None),
                "request_id": str(dbev.request_id) if getattr(dbev, "request_id", None) else None,
                "created_at": dbev.created_at.isoformat() if getattr(dbev, "created_at", None) else None,
            })
            if obj_key:
                existing_keys.add(obj_key)
            existing_keys.add(str(dbev.id))

    payload = {
        "claim": _item(c, db=db),
        "extracted_data": extracted,
        "extracted_fields": state.get("extracted_fields", []),
        "policy": policy_payload,
        "conversation": [{"speaker": "Claimant" if t.speaker in {"user", "claimant"} else "Agent", "text": t.text, "turn": t.turn_number, "timestamp": t.created_at.isoformat() if t.created_at else None} for t in turns],
        "requirements": state.get("dynamic_requirements", []),
        "missing_requirements": state.get("dynamic_missing", []),
        "missing_evidence": state.get("missing_evidence", []),
        "evidence": evidence_list,
        "notes": notes_payload,
        "evidence_requests": evidence_requests_payload,
        "policy_verification": state.get("policy_verification", {}),
        "knowledge_sources": state.get("knowledge_sources", []),
        "copilot": state.get("copilot", {}),
        "copilot_chat": state.get("copilot_chat", []),
        "submission_package": package,
        "conversation_phase": state.get("conversation_phase", "source_of_truth_intake"),
        "gap_analysis": state.get("gap_analysis", {}),
    }
    return JSONResponse(content=jsonable_encoder(payload), headers={"ETag": etag})

@router.post("/claims/{ticket_id}/exceptions/{exception_id}/resolve")
def resolve_exception(ticket_id: str, exception_id: str, request: Request, user: User = Depends(_guard), db: Session = Depends(get_db)):
    claim = get_claim_or_404(db, ticket_id)
    if str(claim.tenant_id) != str(user.tenant_id):
        raise HTTPException(status_code=404, detail="Claim not found.")
    current_user = _resolve_adjuster(request, db)
    _ensure_assigned_adjuster(claim, current_user, db)
    row = db.query(ClaimException).filter(ClaimException.id == exception_id, ClaimException.claim_id == claim.id, ClaimException.tenant_id == claim.tenant_id, ClaimException.status == "open").first()
    if not row:
        raise HTTPException(status_code=404, detail="Open claim exception not found.")
    now = datetime.now(timezone.utc)
    row.status = "resolved"
    row.resolved_at = now
    row.resolution_json = {"resolved_by": current_user.id, "resolved_at": now.isoformat()}
    db.add(ClaimAuditEvent(claim_id=claim.id, tenant_id=claim.tenant_id or "", actor_user_id=current_user.id, event_type="exception_resolved",
                           new_value_json={"exception_id": row.id}, reason="Adjuster resolved blocking exception"))
    db.commit()
    return {"success": True, "exception_id": row.id, "status": row.status}

@router.get("/claims/{ticket_id}/evidence/{evidence_id}/url")
def get_evidence_url(ticket_id: str, evidence_id: str, user: User = Depends(_guard), db: Session = Depends(get_db)):
    c = get_claim_or_404(db, ticket_id)
    if not _can_access_claim(c, user, db):
        raise HTTPException(status_code=403, detail="This claim is not assigned to you.")
    state = dict(c.pipeline_state or {})
    evidence_list = state.get("evidence", [])
    ev = next((e for e in evidence_list if str(e.get("id")) == str(evidence_id)), None)
    if not ev:
        row = db.query(ClaimEvidence).filter(ClaimEvidence.id == evidence_id, ClaimEvidence.claim_id == c.id).first()
        if row:
            key = getattr(row, "object_key", None) or getattr(row, "s3_key", None) or getattr(row, "s3_uri", None)
        else:
            raise HTTPException(status_code=404, detail="Evidence item not found")
    else:
        key = ev.get("s3_key") or ev.get("object_key") or ev.get("s3_uri")
    if not key:
        raise HTTPException(status_code=404, detail="Evidence object key not found.")

    if not settings.S3_BUCKET:
        return {"url": f"/api/v1/adjuster/claims/{ticket_id}/evidence/{evidence_id}/download", "expires_in": 900}
    from src.storage.s3 import presigned_get
    return {"url": presigned_get(key), "expires_in": 900}

evidence_url = get_evidence_url

@router.get("/claims/{ticket_id}/evidence/{evidence_id}/download")
def download_claim_evidence_file(ticket_id: str, evidence_id: str, request: Request, db: Session = Depends(get_db)):
    user = _resolve_adjuster(request, db)
    c = get_claim_or_404(db, ticket_id)
    if not _can_access_claim(c, user, db):
        raise HTTPException(status_code=403, detail="This claim is not assigned to you.")
    state = dict(c.pipeline_state or {})
    evidence_list = state.get("evidence", [])
    ev = next((e for e in evidence_list if str(e.get("id")) == str(evidence_id)), None)
    filename = "evidence"
    if not ev:
        row = db.query(ClaimEvidence).filter(ClaimEvidence.id == evidence_id, ClaimEvidence.claim_id == c.id).first()
        if not row:
            raise HTTPException(status_code=404, detail="Evidence item not found")
        key = getattr(row, "object_key", None) or getattr(row, "s3_key", None) or getattr(row, "s3_uri", None)
        filename = getattr(row, "original_filename", None) or getattr(row, "filename", None) or filename
    else:
        key = ev.get("s3_key") or ev.get("object_key") or ev.get("s3_uri")
        filename = ev.get("original_filename") or ev.get("name") or filename

    if not key:
        raise HTTPException(status_code=404, detail="File not found")

    from src.storage.s3 import get_bytes
    from fastapi.responses import Response
    from src.utils.file_security import get_safe_media_type, build_attachment_headers
    try:
        data = get_bytes(key)
        safe_media_type = get_safe_media_type(filename)
        headers = build_attachment_headers(filename)
        return Response(content=data, media_type=safe_media_type, headers=headers)
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")

download_evidence = download_claim_evidence_file

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
        db.add(ClaimNote(claim_id=c.id, tenant_id=c.tenant_id or "", author_user_id=user.id, note=payload.note, visibility="internal"))
    if payload.status:
        try:
            transition_claim(db, c, payload.status, user.id, "adjuster workflow update")
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
    c.pipeline_state=state
    db.add(ClaimAuditEvent(claim_id=c.id, tenant_id=c.tenant_id or "", actor_user_id=user.id, event_type="claim_updated",
                           new_value_json={"priority":state.get("priority"),"status":c.status}))
    db.commit(); db.refresh(c)
    return _item(c)

@router.post("/claims/{ticket_id}/assign")
def assign_claim(ticket_id: str, user: User = Depends(_guard), db: Session = Depends(get_db)):
    c = get_claim_or_404(db, ticket_id)
    # Enforce the tenant boundary before reading or mutating assignment state.
    if str(c.tenant_id or "") != str(user.tenant_id or ""):
        raise HTTPException(status_code=404, detail="Claim not found.")
    active=db.query(ClaimAssignment).filter(ClaimAssignment.claim_id==c.id,ClaimAssignment.tenant_id==c.tenant_id,ClaimAssignment.is_active.is_(True)).first()
    if active:
        aa=db.query(Adjuster).filter(Adjuster.id==active.adjuster_id,Adjuster.tenant_id==c.tenant_id).first()
        return {"success":True,"already_assigned":True,"claim":_item(c,aa)}
    from src.database.claim_workflow import assign_claim as assign_claim_tx
    try:
        aa=assign_claim_tx(db,c,user.id)
        if c.status=="submitted": transition_claim(db,c,"assigned",user.id,"manual assignment")
        state=dict(c.pipeline_state or {}); state["assigned_adjuster_id"]=aa.id; state["assigned_adjuster_name"]=aa.name; c.pipeline_state=state
        db.commit()
    except ValueError as exc:
        db.rollback(); raise HTTPException(status_code=409,detail=str(exc))
    return {"success":True,"already_assigned":False,"claim":_item(c,aa)}

# Consolidated evidence URL & download endpoints defined above

def _run_deterministic_copilot_prechecks(
    c: Claim,
    state: dict[str, Any],
    policy_row: Optional[Policy],
    evidence_rows: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
    missing_evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    """AWS AgentCore 4-Phase deterministic pre-check, fraud scoring rubric, and IRDAI SLA audit."""
    data = state.get("extracted_data") or {}
    claim_amount = float(c.estimated_claim_amount) if c.estimated_claim_amount is not None else 0.0
    deductible = float(policy_row.deductible) if policy_row and policy_row.deductible is not None else 0.0
    coverage_limit = float(policy_row.coverage_amount) if policy_row and policy_row.coverage_amount is not None else 0.0
    ins_type = c.insurance_type or data.get("insurance_type") or (policy_row.policy_type if policy_row else "general")

    # Phase 1: Zero-Token Policy Pre-Check
    policy_active = bool(policy_row and policy_row.is_active)
    incident_date = c.event_date
    policy_dates_valid = True
    days_since_inception = 999
    if policy_row and policy_row.effective_date and incident_date:
        policy_dates_valid = (policy_row.effective_date <= incident_date <= policy_row.expiry_date)
        days_since_inception = (incident_date - policy_row.effective_date).days

    days_to_report = 0
    if incident_date and c.claim_date:
        days_to_report = (c.claim_date - incident_date).days

    # Phase 2: Quantified Fraud & Risk Rubric (0.00 to 1.00)
    risk_flags = []
    fraud_score = 0.10

    if days_since_inception < 30:
        fraud_score += 0.25
        risk_flags.append(f"Early-claim timing anomaly: Incident occurred within {days_since_inception} days of policy inception (waiting period audit required).")

    if coverage_limit > 0 and claim_amount >= (0.85 * coverage_limit):
        fraud_score += 0.15
        risk_flags.append(f"High limit utilization: Claimed amount (₹{claim_amount:,.2f}) is >=85% of total coverage limit (₹{coverage_limit:,.2f}).")

    if days_to_report > 7:
        fraud_score += 0.15
        risk_flags.append(f"Delayed intimation: Claim reported {days_to_report} days after incident date (IRDAI condonation review applicable).")

    narrative = str(c.event_description or "").lower()
    has_theft = "theft" in narrative or "stolen" in narrative
    has_cyber = ins_type == "cyber" or any(w in narrative for w in ("phishing", "unauthorized", "upi", "ransomware"))
    has_injury = any(w in narrative for w in ("injury", "hospital", "third-party", "third party"))

    if (has_theft or has_cyber or has_injury) and not any("fir" in str(e.get("category", "")).lower() or "fir" in str(e.get("filename", "")).lower() for e in evidence_rows):
        fraud_score += 0.20
        risk_flags.append("Statutory authority intimation pending: Police FIR / NCRP acknowledgement copy not yet submitted.")

    low_conf = [e for e in evidence_rows if float(e.get("verification_confidence") or 1.0) < 0.70]
    if low_conf:
        fraud_score += 0.20
        risk_flags.append(f"{len(low_conf)} evidence document(s) have low verification confidence (<70%) or require physical surveyor verification.")

    if policy_active and policy_dates_valid and not missing_evidence and len(evidence_rows) >= 2:
        fraud_score = max(0.05, fraud_score - 0.10)

    fraud_score = max(0.05, min(1.0, round(fraud_score, 2)))

    # IRDAI Statutory SLA Mandates
    sla_mandates = []
    if ins_type == "motor":
        sla_mandates.append("Surveyor Allocation: Within 24 hours of claim intimation (IRDAI Master Circular 2024).")
        sla_mandates.append("Surveyor Report: Within 15 days of appointment.")
        sla_mandates.append("Settlement Offer: Within 7 days of surveyor report receipt.")
        sla_mandates.append("Compulsory Deductible: Rs 1,000 (engines <= 1500cc) / Rs 2,000 (engines > 1500cc).")
    elif ins_type in ("health", "senior_health", "senior_citizen_health"):
        sla_mandates.append("Cashless Pre-Authorization Decision: Within 1 hour of request (IRDAI 2024).")
        sla_mandates.append("Cashless Final Discharge Authorization: Within 3 hours of discharge summary submission.")
        sla_mandates.append("Reimbursement Claim Settlement: Within 15 days of last document submission.")
        sla_mandates.append("Delayed Settlement Penalty: Insurer liable to pay interest at Bank Rate + 2% for delayed days.")
        sla_mandates.append("IRDAI Non-Rejection Rule: No claim shall be rejected for want of documents; all missing items must be called for in one go.")
    elif ins_type == "home":
        sla_mandates.append("Surveyor Allocation: Within 48 hours for standard property claims.")
        sla_mandates.append("Underinsurance Waiver: Underinsurance up to 15% is waived under Bharat Griha Raksha.")
        sla_mandates.append("Settlement Offer: Within 7 days of survey report receipt.")
    elif ins_type == "cyber":
        sla_mandates.append("Reporting Window: Report to Bank & NCRP (1930) within 72 hours of discovery.")
        sla_mandates.append("RBI Zero Liability: Customer has zero liability if unauthorized electronic transaction reported within 3 working days.")
    else:
        sla_mandates.append("IRDAI Fair Claims Handling: All missing document requirements must be notified to claimant in a single notice.")

    # Phase 3: Strict Precedence Decision Rules
    if not policy_active or not policy_dates_valid:
        rec = "REJECT"
        rationale = f"Policy inactive or incident date ({incident_date}) falls outside policy term ({policy_row.effective_date if policy_row else 'N/A'} to {policy_row.expiry_date if policy_row else 'N/A'})."
        payout = 0.0
    elif fraud_score >= 0.70:
        rec = "ESCALATE"
        rationale = f"High fraud/risk score ({fraud_score:.2f}) triggered by timing anomalies, high utilization, or unverified documents. Escalated to Special Investigation Unit (SIU)."
        payout = None
    elif missing_evidence:
        rec = "REQUEST_EVIDENCE"
        req_names = [str(m.get("label") or m.get("key")) for m in missing_evidence]
        rationale = f"Mandatory evidence is incomplete ({len(missing_evidence)} required document(s) pending: {', '.join(req_names)}). Per IRDAI rules, request all missing items in one consolidated notice."
        payout = None
    elif claim_amount >= 500000 or (fraud_score >= 0.45):
        rec = "ESCALATE"
        rationale = f"High-value claim (₹{claim_amount:,.2f}) or moderate risk score ({fraud_score:.2f}) requires Senior Claims Manager / Legal sign-off."
        payout = max(0.0, min(claim_amount, coverage_limit) - deductible)
    elif coverage_limit > 0 and claim_amount > coverage_limit:
        rec = "PARTIAL_APPROVE"
        payout = max(0.0, coverage_limit - deductible)
        rationale = f"Claim amount (₹{claim_amount:,.2f}) exceeds policy coverage limit (₹{coverage_limit:,.2f}). Approved up to policy cap less deductible (₹{deductible:,.2f})."
    else:
        rec = "APPROVE"
        payout = max(0.0, claim_amount - deductible)
        rationale = f"Clean, verified claim within coverage limit (₹{coverage_limit:,.2f}). All mandatory evidence verified. Net payout calculated after ₹{deductible:,.2f} deductible."

    citations = []
    for s in source_rows[:5]:
        s_id = str(s.get("chunk_id") or s.get("document_id") or s.get("id") or "")
        label = str(s.get("citation_label") or s.get("source_name") or "Policy Document")
        if s_id:
            citations.append({"source_id": s_id, "claim": f"Grounded in {label}"})

    return {
        "executive_summary": f"Incident Analysis for Claim #{c.ticket_id} ({ins_type.replace('_', ' ').title()}). Incident date: {incident_date}. Claimed: ₹{claim_amount:,.2f}. Policy status: {'Active' if policy_active else 'Inactive'}. Verified evidence documents: {len(evidence_rows)}. Fraud risk score: {fraud_score:.2f}.",
        "decision_recommendation": rec,
        "recommended_payout_amount": payout,
        "confidence_score": 0.88,
        "decision_rationale": rationale,
        "fraud_score": fraud_score,
        "actionable_suggestions": [
            f"Review preliminary decision ({rec}) against surveyor / repair invoices.",
            f"Adhere to statutory IRDAI timeline ({sla_mandates[0] if sla_mandates else 'settle within 15 days'}).",
            "Verify bank NEFT details prior to final payout authorization."
        ],
        "coverage_observations": [
            f"Policy Type: {ins_type.replace('_', ' ').title()}",
            f"Coverage Limit: ₹{coverage_limit:,.2f}",
            f"Applicable Deductible: ₹{deductible:,.2f}",
            f"Net Estimated Payable: ₹{payout:,.2f}" if payout is not None else "Payable amount pending evidence review",
        ],
        "mandatory_requirements": [
            {"label": str(m.get("label") or m.get("key")), "status": "missing", "condition": str(m.get("condition") or "")}
            for m in missing_evidence
        ],
        "evidence_assessment": [
            f"Submitted {len(evidence_rows)} supporting document(s).",
            f"Mandatory evidence outstanding: {len(missing_evidence)} document(s).",
        ],
        "risk_flags": risk_flags if risk_flags else ["No elevated risk factors detected; standard claim adjudication applies."],
        "regulatory_considerations": sla_mandates,
        "decision_considerations": [
            "Weigh repair estimate against surveyor depreciation schedule.",
            "Confirm no concurrent policy or duplicate intimation exists.",
        ],
        "recommended_next_steps": [
            "Issue formal claimant notification with decision or request for missing evidence.",
            "Record final human adjudication notes in claim audit log.",
        ],
        "uncertainties": [
            "Final approved amount depends on surveyor physical assessment." if not payout else "No material coverage uncertainties identified."
        ],
        "citations": citations,
    }

@router.get("/claims/{ticket_id}/copilot")
async def copilot(ticket_id: str, refresh: bool = False, user: User = Depends(_guard), db: Session = Depends(get_db)):
    c = get_claim_or_404(db, ticket_id)
    if not _can_access_claim(c, user, db):
        raise HTTPException(status_code=403, detail="This claim is not assigned to you.")
    state = dict(c.pipeline_state or {})
    cached_copilot = state.get("copilot")
    cached_version = state.get("copilot_state_version")
    if not refresh and cached_copilot and cached_version == getattr(c, "state_version", 1):
        return {
            "ticket_id": ticket_id,
            "analysis": cached_copilot,
            "status": "ready",
            "sources": state.get("knowledge_sources") or [],
            "chat": state.get("copilot_chat") or [],
            "cached": True,
        }
    data = state.get("extracted_data") or {}

    # Context Resolution: Resolve linked Policy row
    policy_row = None
    if c.policy_id:
        policy_row = db.query(Policy).filter(Policy.id == c.policy_id).first()
    elif data.get("policy_id"):
        policy_row = db.query(Policy).filter(Policy.policy_number == data["policy_id"]).first()

    resolved_ins_type = c.insurance_type or data.get("insurance_type") or (policy_row.policy_type if policy_row else None)
    if not resolved_ins_type and c.event_description:
        from src.knowledge.retriever import infer_insurance_type_from_query
        resolved_ins_type = infer_insurance_type_from_query(c.event_description)
    resolved_policy_num = data.get("policy_id") or (policy_row.policy_number if policy_row else None)

    context = {}
    try:
        context = KnowledgeRetriever().retrieve(
            insurance_type=resolved_ins_type or "",
            policy_number=resolved_policy_num,
            incident_date=c.event_date,
            query=c.event_description or "",
            claim_facts=data,
            tenant_id=user.tenant_id or "",
        )
    except Exception as exc:
        logger = __import__("logging").getLogger(__name__)
        logger.warning("Knowledge retrieval non-fatal error: %s", exc)

    requirements = context.get("requirements") or state.get("dynamic_requirements") or []
    evidence_db = db.query(ClaimEvidence).filter(ClaimEvidence.claim_id == c.id, ClaimEvidence.tenant_id == c.tenant_id).all()
    evidence = [
        {
            "id": str(e.id),
            "filename": e.filename,
            "category": e.detected_document_type or e.category or "document",
            "verification_status": e.verification_status,
            "verification_confidence": e.verification_confidence,
        }
        for e in evidence_db
    ] if evidence_db else list(state.get("evidence") or [])
    missing = state.get("dynamic_missing") or []
    missing_evidence = state.get("missing_evidence") or []
    requests = [
        _request_payload(row, db)
        for row in db.query(ClaimEvidenceRequest)
        .filter(ClaimEvidenceRequest.claim_id == c.id, ClaimEvidenceRequest.tenant_id == c.tenant_id)
        .order_by(ClaimEvidenceRequest.requested_at.desc())
        .all()
    ]
    source_rows = [*context.get("policy", []), *context.get("regulations", [])]

    # Pre-compute Phase 1, Phase 2, Phase 3 deterministic adjudication baseline
    det_baseline = _run_deterministic_copilot_prechecks(c, state, policy_row, evidence, source_rows, missing_evidence)

    prompt = f"""You are an insurance adjuster AI copilot and claim decision-support analyst.
Analyze this specific claim in detail and provide a full decision-support report along with actionable suggestions.
Use all supplied claim facts, evidence state, mandatory requirements, and retrieved policy/regulatory sources.
Every policy, coverage, deadline, exclusion, regulatory, or required-evidence statement must be grounded in the supplied retrieved sources. Do not invent or infer unsupported policy terms.
If mandatory evidence or authoritative policy verification is missing, do not treat that as an approval-ready condition; surface the missing basis and use REQUEST_EVIDENCE or ESCALATE as appropriate.
Keep the final claim decision with the human adjuster. Your role is evidence-grounded analysis, consistency checking, uncertainty identification, and actionable support.

Deterministic Pre-Check Baseline:
- Preliminary Recommendation: {det_baseline.get("decision_recommendation")}
- Suggested Payout: ₹{det_baseline.get("recommended_payout_amount")}
- Fraud Score: {det_baseline.get("fraud_score")}
- Statutory IRDAI SLA: {det_baseline.get("regulatory_considerations")}

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
  ],
  "citations": [
    {{"source_id": "retrieved-source-id", "claim": "Short statement this source supports"}}
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
CITATION RULE: For every policy/regulatory/coverage conclusion, include a citation object with source_id equal to one of the retrieved source chunk IDs (prefer chunk_id, then id/document_id) and a short claim describing what it supports.
"""

    parsed = None
    try:
        estimated_tokens = min(12000, max(512, len(prompt) // 4 + 512))
        async with tenant_ai_guard(
            user.tenant_id or "",
            operation="adjuster_copilot",
            estimated_tokens=estimated_tokens,
        ):
            result = await asyncio.to_thread(get_configured_llm().invoke, prompt)
        raw = getattr(result, "content", str(result))
        try:
            parsed = json.loads(raw)
        except Exception:
            match = re.search(r"\{.*\}", str(raw), re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            raise ValueError("Copilot returned an invalid report.")
        parsed.setdefault("executive_summary", det_baseline["executive_summary"])
        parsed.setdefault("decision_recommendation", det_baseline["decision_recommendation"])
        parsed.setdefault("recommended_payout_amount", det_baseline["recommended_payout_amount"])
        parsed.setdefault("confidence_score", 0.88)
        parsed.setdefault("decision_rationale", det_baseline["decision_rationale"])
        parsed.setdefault("actionable_suggestions", det_baseline["actionable_suggestions"])
        parsed.setdefault("coverage_observations", det_baseline["coverage_observations"])
        parsed.setdefault("mandatory_requirements", det_baseline["mandatory_requirements"])
        parsed.setdefault("evidence_assessment", det_baseline["evidence_assessment"])
        parsed.setdefault("risk_flags", det_baseline["risk_flags"])
        parsed.setdefault("regulatory_considerations", det_baseline["regulatory_considerations"])
        parsed.setdefault("decision_considerations", det_baseline["decision_considerations"])
        parsed.setdefault("recommended_next_steps", det_baseline["recommended_next_steps"])
        parsed.setdefault("uncertainties", det_baseline["uncertainties"])
        citations = parsed.get("citations")
        if not isinstance(citations, list):
            citations = []
        valid_source_ids = {
            str(row.get("chunk_id") or row.get("id") or row.get("document_id"))
            for row in source_rows
            if row.get("chunk_id") or row.get("id") or row.get("document_id")
        }
        normalized_citations = []
        for citation in citations:
            if not isinstance(citation, dict):
                continue
            source_id = str(citation.get("source_id") or "").strip()
            claim_desc = str(citation.get("claim") or "").strip()
            if source_id and claim_desc and source_id in valid_source_ids:
                normalized_citations.append({"source_id": source_id, "claim": claim_desc})
            else:
                for row in source_rows:
                    r_id = str(row.get("chunk_id") or row.get("id") or row.get("document_id") or "")
                    r_lbl = str(row.get("citation_label") or row.get("source_name") or "")
                    if r_id and (source_id.lower() in r_lbl.lower() or r_lbl.lower() in source_id.lower()):
                        normalized_citations.append({"source_id": r_id, "claim": claim_desc or f"Grounded in {r_lbl}"})
                        break

        if source_rows and not normalized_citations:
            normalized_citations = det_baseline.get("citations") or []
        parsed["citations"] = normalized_citations
    except Exception as exc:
        logger = __import__("logging").getLogger(__name__)
        logger.warning("LLM Copilot report synthesis unavailable for %s (%s); utilizing deterministic 4-phase report", ticket_id, exc)
        parsed = det_baseline

    state["copilot"] = parsed
    state["copilot_state_version"] = getattr(c, "state_version", 1)
    state["knowledge_sources"] = source_rows

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
    flag_modified(c, "pipeline_state")
    try:
        db.add(CopilotAnalysis(
            tenant_id=c.tenant_id or "",
            claim_id=c.id,
            claim_version=1,
            knowledge_version="retrieval-current",
            model=getattr(settings, "REASONING_LLM_MODEL", None) or getattr(settings, "CLOUD_LLM_MODEL", "configured"),
            prompt_version="v4",
            result_json=parsed,
            citations_json=source_rows,
        ))
        append_system_audit(
            db,
            tenant_id=c.tenant_id or "",
            actor_user_id=user.id,
            event_type="ai_recommendation",
            resource_type="claim",
            resource_id=c.id,
            action="copilot_analysis",
            payload={
                "model": getattr(settings, "REASONING_LLM_MODEL", "configured"),
                "prompt_version": "v4",
                "citation_count": len(source_rows),
                "recommendation": parsed,
            },
        )
        db.commit()
    except Exception:
        db.rollback()

    return {"ticket_id": ticket_id, "analysis": parsed, "status": "ready", "sources": source_rows, "chat": state["copilot_chat"]}

class CopilotChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)

@router.post("/claims/{ticket_id}/copilot/chat")
async def copilot_chat(ticket_id: str, payload: CopilotChatRequest, user: User = Depends(_guard), db: Session = Depends(get_db)):
    c = get_claim_or_404(db, ticket_id)
    if not _can_access_claim(c, user, db):
        raise HTTPException(status_code=403, detail="This claim is not assigned to you.")
    state = dict(c.pipeline_state or {})
    data = state.get("extracted_data") or {}
    policy_row = None
    if c.policy_id:
        policy_row = db.query(Policy).filter(Policy.id == c.policy_id).first()
    elif data.get("policy_id"):
        policy_row = db.query(Policy).filter(Policy.policy_number == data["policy_id"]).first()

    resolved_ins_type = c.insurance_type or data.get("insurance_type") or (policy_row.policy_type if policy_row else None)
    if not resolved_ins_type and c.event_description:
        from src.knowledge.retriever import infer_insurance_type_from_query
        resolved_ins_type = infer_insurance_type_from_query(c.event_description)
    resolved_policy_num = data.get("policy_id") or (policy_row.policy_number if policy_row else None)

    context = {}
    try:
        context = KnowledgeRetriever().retrieve(
            insurance_type=resolved_ins_type or "",
            policy_number=resolved_policy_num,
            incident_date=c.event_date,
            query=c.event_description or payload.message,
            claim_facts=data,
            tenant_id=user.tenant_id or "",
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
- Insurance Type: {resolved_ins_type or c.insurance_type}
- Event Date: {c.event_date}
- Estimated Amount: {c.estimated_claim_amount}
- Facts: {json.dumps(data, ensure_ascii=False, default=str)}
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
        estimated_tokens = min(12000, max(512, len(prompt) // 4 + 512))
        async with tenant_ai_guard(
            user.tenant_id or "",
            operation="adjuster_copilot_chat",
            estimated_tokens=estimated_tokens,
        ):
            result = await asyncio.to_thread(get_configured_llm().invoke, prompt)
        answer = getattr(result, "content", str(result)).strip()
        if not answer:
            raise ValueError("Empty Copilot response.")
    except Exception as exc:
        logger = __import__("logging").getLogger(__name__)
        logger.warning("Copilot chat invocation failed: %s; synthesizing grounded answer", exc)
        det = _run_deterministic_copilot_prechecks(c, state, policy_row, list(state.get("evidence") or []), source_rows, list(state.get("missing_evidence") or []))
        answer = (
            f"Based on policy terms and IRDAI standards for this claim:\n\n"
            f"• **Recommendation:** {det.get('decision_recommendation')}\n"
            f"• **Rationale:** {det.get('decision_rationale')}\n"
            f"• **Statutory Timeline:** {det.get('regulatory_considerations', ['15 days'])[0]}\n"
            f"• **Action:** {det.get('actionable_suggestions', ['Review submitted evidence against policy guidelines.'])[0]}"
        )

    user_msg = {
        "id": str(uuid.uuid4()),
        "speaker": "adjuster",
        "message": payload.message,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    citation_rows = [
        row for row in source_rows
        if row.get("citation_label") or row.get("source_name") or row.get("chunk_id")
    ]
    if citation_rows:
        labels = []
        for row in citation_rows[:4]:
            label = str(row.get("citation_label") or row.get("source_name") or row.get("chunk_id") or "").strip()
            if label and label not in labels:
                labels.append(label)
        if labels and not any(label.lower() in answer.lower() for label in labels):
            answer = f"{answer.rstrip()}\n\nSources: " + "; ".join(labels)
    bot_msg = {
        "id": str(uuid.uuid4()),
        "speaker": "copilot",
        "message": answer,
        "citations": citation_rows,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    chat = full_history + [user_msg, bot_msg]
    state["copilot_chat"] = chat
    c.pipeline_state = state
    flag_modified(c, "pipeline_state")
    db.commit()
    return {"ticket_id": ticket_id, "answer": answer, "chat": chat, "sources": source_rows, "citations": citation_rows}



class EvidenceRequestCreate(BaseModel):
    request_text: str = Field(..., min_length=5, max_length=4000)

@router.post("/claims/{ticket_id}/evidence-requests")
def create_evidence_request(ticket_id: str, payload: EvidenceRequestCreate, user: User = Depends(_guard), db: Session = Depends(get_db)):
    c = get_claim_or_404(db, ticket_id)
    adjuster = _ensure_assigned_adjuster(c, user, db)
    if c.status in {"approved", "partially_approved", "rejected", "closed"}:
        raise HTTPException(status_code=409, detail="Evidence cannot be requested after a final claim outcome.")
    row = ClaimEvidenceRequest(claim_id=c.id, tenant_id=c.tenant_id or "", adjuster_id=adjuster.id, request_text=payload.request_text.strip(), status="open")
    db.add(row)
    if c.status in {"submitted", "assigned", "under_review"}:
        transition_claim(db, c, "pending_evidence", user.id, "adjuster requested additional evidence")
    db.add(ClaimAuditEvent(
        claim_id=c.id,
        tenant_id=c.tenant_id or "", actor_user_id=user.id, event_type="evidence_requested",
        new_value_json={"request_id": row.id, "request_text": row.request_text}, reason=row.request_text
    ))
    db.commit()
    db.refresh(row)
    return _request_payload(row, db)

@router.get("/claims/{ticket_id}/evidence-requests")
def list_evidence_requests(ticket_id: str, user: User = Depends(_guard), db: Session = Depends(get_db)):
    c = get_claim_or_404(db, ticket_id)
    _ensure_assigned_adjuster(c, user, db)
    rows = db.query(ClaimEvidenceRequest).filter(ClaimEvidenceRequest.claim_id == c.id, ClaimEvidenceRequest.tenant_id == c.tenant_id).order_by(ClaimEvidenceRequest.requested_at.desc()).all()
    return [_request_payload(row, db) for row in rows]

class ClaimTransitionRequest(BaseModel):
    status: str
    reason: str = "Adjuster moved claim card in board view"

@router.post("/claims/{ticket_id}/transition")
def transition_claim_status(
    ticket_id: str,
    payload: ClaimTransitionRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    current_user = _resolve_adjuster(request, db)
    claim = get_claim_or_404(db, ticket_id)
    _ensure_assigned_adjuster(claim, current_user, db)
    try:
        transition_claim(db, claim, payload.status, current_user.id, payload.reason)
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ticket_id": claim.ticket_id, "status": claim.status}

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
        transition_claim(db, claim, target, current_user.id, payload.rationale)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    row = ClaimDecision(
        tenant_id=claim.tenant_id or "",
        claim_id=claim.id, adjuster_id=adjuster.id, decision=payload.decision,
        rationale=payload.rationale, approved_amount=payload.approved_amount,
        ai_recommendation_json=(claim.pipeline_state or {}).get("copilot") or {},
    )
    db.add(row)
    db.add(ClaimAuditEvent(
        claim_id=claim.id,
        tenant_id=claim.tenant_id or "", actor_user_id=current_user.id, event_type="decision_recorded",
        new_value_json={"decision": payload.decision, "approved_amount": payload.approved_amount},
        reason=payload.rationale,
    ))
    append_system_audit(
        db,
        tenant_id=claim.tenant_id or "",
        actor_user_id=current_user.id,
        event_type="human_decision",
        resource_type="claim",
        resource_id=claim.id,
        action="record_decision",
        payload={"decision": payload.decision, "approved_amount": payload.approved_amount, "rationale_present": bool(payload.rationale)},
    )
    db.commit()
    return {"decision_id": row.id, "claim_id": claim.ticket_id, "decision": payload.decision,
            "status": claim.status, "rationale": payload.rationale}

@router.post("/claims/{ticket_id}/notes")
def add_claim_note(ticket_id: str, payload: NoteRequest, request: Request, db: Session = Depends(get_db)):
    current_user = _resolve_adjuster(request, db)
    claim = get_claim_or_404(db, ticket_id)
    _ensure_assigned_adjuster(claim, current_user, db)
    note = ClaimNote(claim_id=claim.id, tenant_id=claim.tenant_id or "", author_user_id=current_user.id,
                     note=payload.note, visibility=payload.visibility)
    db.add(note)
    db.add(ClaimAuditEvent(claim_id=claim.id, tenant_id=claim.tenant_id or "", actor_user_id=current_user.id,
                           event_type="note_added", new_value_json={"note_id": note.id}))
    db.commit()
    return {"id": note.id, "created_at": note.created_at.isoformat(), "visibility": note.visibility}

@router.get("/claims/{ticket_id}/audit")
def get_claim_audit(ticket_id: str, request: Request, db: Session = Depends(get_db)):
    current_user = _resolve_adjuster(request, db)
    claim = get_claim_or_404(db, ticket_id)
    _ensure_assigned_adjuster(claim, current_user, db)
    rows = db.query(ClaimAuditEvent).filter(ClaimAuditEvent.claim_id == claim.id, ClaimAuditEvent.tenant_id == claim.tenant_id).order_by(ClaimAuditEvent.created_at.asc()).all()
    return [_format_audit_row(r) for r in rows]
