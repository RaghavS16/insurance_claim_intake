"""Transactional claim workflow primitives and audit helpers."""
from __future__ import annotations
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from src.database.models import Claim, Adjuster
from src.database.hardening_models import ClaimAssignment, ClaimAuditEvent, ClaimRequirement, ClaimEvidence, ClaimException, ClaimFact, ClaimSubmission

ALLOWED_TRANSITIONS = {
    "draft": {"pending_confirmation", "pending_verification", "verified", "verification_failed", "escalated"},
    "pending_confirmation": {"draft", "pending_verification", "verified", "verification_failed", "escalated"},
    "pending_verification": {"draft", "verified", "verification_failed", "escalated"},
    "verified": {"pending_evidence", "submitted", "assigned", "under_review", "escalated"},
    "pending_evidence": {"verified", "submitted", "assigned", "under_review", "approved", "partially_approved", "rejected", "escalated"},
    "submitted": {"assigned", "under_review", "pending_evidence", "approved", "partially_approved", "rejected", "escalated"},
    "pending_adjuster": {"assigned", "under_review", "pending_evidence", "approved", "partially_approved", "rejected", "escalated"},
    "assigned": {"under_review", "pending_evidence", "approved", "partially_approved", "rejected", "escalated"},
    "under_review": {"pending_evidence", "approved", "partially_approved", "rejected", "escalated"},
    "approved": {"closed", "under_review"},
    "partially_approved": {"closed", "under_review"},
    "rejected": {"closed", "under_review"},
    "escalated": {"under_review", "approved", "rejected", "closed"},
    "closed": set(),
    "verification_failed": {"draft", "pending_verification", "verified", "closed"},
}

def transition_claim(db: Session, claim: Claim, new_status: str, actor_user_id: str | None = None, reason: str | None = None) -> Claim:
    old = claim.status
    if new_status == old:
        return claim
    if new_status not in ALLOWED_TRANSITIONS.get(old, set()):
        raise ValueError(f"Invalid claim transition: {old} -> {new_status}")
    claim.status = new_status
    db.add(ClaimAuditEvent(
        claim_id=claim.id, actor_user_id=actor_user_id, event_type="status_changed",
        old_value_json={"status": old}, new_value_json={"status": new_status}, reason=reason,
    ))
    return claim

def assign_claim(db: Session, claim: Claim, actor_user_id: str | None = None) -> Adjuster:
    active = db.execute(select(ClaimAssignment).where(
        ClaimAssignment.claim_id == claim.id, ClaimAssignment.is_active.is_(True)
    )).scalar_one_or_none()
    if active:
        raise ValueError("Claim already has an active assignment")
    candidates = list(db.execute(
        select(Adjuster).where(Adjuster.is_active.is_(True)).order_by(
            Adjuster.claims_assigned.asc(), Adjuster.id.asc()
        )
    ).scalars())
    if not candidates:
        raise ValueError("No active adjuster is available")
    chosen = next((a for a in candidates if a.specialization == claim.insurance_type), candidates[0])
    db.execute(update(Adjuster).where(Adjuster.id == chosen.id).values(
        claims_assigned=Adjuster.claims_assigned + 1
    ))
    db.add(ClaimAssignment(
        claim_id=claim.id, adjuster_id=chosen.id, assigned_by=actor_user_id,
        reason="specialization_then_load",
    ))
    db.add(ClaimAuditEvent(
        claim_id=claim.id, actor_user_id=actor_user_id, event_type="assigned",
        new_value_json={"adjuster_id": chosen.id, "reason": "specialization_then_load"},
    ))
    return chosen


def build_submission_readiness(db: Session, claim: Claim, policy_verification: dict | None = None) -> dict:
    """Return deterministic readiness from durable requirements, evidence and exceptions."""
    from src.domain.readiness import build_readiness
    requirements = db.query(ClaimRequirement).filter(ClaimRequirement.claim_id == claim.id).all()
    evidence = db.query(ClaimEvidence).filter(ClaimEvidence.claim_id == claim.id).all()
    exceptions = db.query(ClaimException).filter(
        ClaimException.claim_id == claim.id,
        ClaimException.status == "open",
    ).all()
    return build_readiness(
        requirements=requirements,
        policy_verification=policy_verification,
        evidence_rows=evidence,
        exceptions=exceptions,
    )


def transition_claim_if_allowed(\n    db: Session,\n    claim: Claim,\n    new_status: str,\n    *,\n    actor_user_id: str | None = None,\n    reason: str | None = None,\n) -> Claim:\n    """Explicit named wrapper used by service code to make transitions auditable."""\n    return transition_claim(db, claim, new_status, actor_user_id, reason)\n

def persist_canonical_facts(
    db: Session,
    claim: Claim,
    facts: dict,
    *,
    source_type: str = "CLAIMANT",
    source_id: str | None = None,
    confidence: float | None = None,
) -> None:
    """Upsert canonical facts while retaining provenance in the normalized store."""
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    rows = {
        row.fact_key: row
        for row in db.query(ClaimFact).filter(ClaimFact.claim_id == claim.id).all()
    }
    for key, value in (facts or {}).items():
        if value in (None, "", "UNKNOWN"):
            continue
        row = rows.get(str(key))
        if row is None:
            row = ClaimFact(
                claim_id=str(claim.id),
                fact_key=str(key),
                value_json={"value": value},
                state="PROPOSED",
                source_type=source_type,
                source_id=source_id,
                confidence=confidence,
                provenance_json={"source_type": source_type, "source_id": source_id},
            )
            db.add(row)
            rows[str(key)] = row
        else:
            old_value = (row.value_json or {}).get("value")
            if old_value != value:
                row.version = int(row.version or 1) + 1
            row.value_json = {"value": value}
            row.source_type = source_type
            row.source_id = source_id
            row.confidence = confidence
            row.provenance_json = {
                **(row.provenance_json or {}),
                "source_type": source_type,
                "source_id": source_id,
                "updated_at": now.isoformat(),
            }
            row.updated_at = now
        row.state = "ACCEPTED" if source_type == "POLICY_DB" else "PROPOSED"


def record_exception(
    db: Session,
    claim: Claim,
    *,
    event_type: str,
    reason: str,
    severity: str = "medium",
    blocking: bool = True,
    source_type: str = "SYSTEM_RULE",
    source_id: str | None = None,
) -> ClaimException:
    existing = db.query(ClaimException).filter(
        ClaimException.claim_id == claim.id,
        ClaimException.event_type == event_type,
        ClaimException.status == "open",
    ).first()
    if existing:
        existing.reason = reason
        existing.severity = severity
        existing.blocking = blocking
        return existing
    row = ClaimException(
        claim_id=str(claim.id),
        event_type=event_type,
        reason=reason,
        severity=severity,
        blocking=blocking,
        source_type=source_type,
        source_id=source_id,
    )
    db.add(row)
    return row


def sync_claim_requirements(db: Session, claim: Claim, requirements: list[dict]) -> None:
    """Synchronize the current policy-derived manifest into durable requirement rows."""
    rows = {
        row.requirement_key: row
        for row in db.query(ClaimRequirement).filter(ClaimRequirement.claim_id == claim.id).all()
    }
    active_keys = set()
    outstanding_info = {
        str(x.get("key")) for x in (claim.pipeline_state or {}).get("dynamic_missing", []) if x.get("key")
    }
    outstanding_evidence = {
        str(x.get("key")) for x in (claim.pipeline_state or {}).get("missing_evidence", []) if x.get("key")
    }
    pending_review = {
        str(x.get("key")) for x in (claim.pipeline_state or {}).get("pending_evidence_review", []) if x.get("key")
    }
    for req in requirements or []:
        key = str(req.get("key") or "").strip()
        if not key:
            continue
        active_keys.add(key)
        row = rows.get(key)
        if row is None:
            row = ClaimRequirement(
                claim_id=str(claim.id),
                requirement_key=key,
                label=str(req.get("label") or key),
                question_hint=req.get("question_hint"),
                required=bool(req.get("required", True)),
                evidence_type=req.get("evidence_type"),
                condition_json={"condition": req.get("condition")},
                provenance_json=req.get("provenance") or {},
            )
            db.add(row)
            rows[key] = row
        else:
            row.label = str(req.get("label") or row.label)
            row.question_hint = req.get("question_hint") or row.question_hint
            row.required = bool(req.get("required", row.required))
            row.evidence_type = req.get("evidence_type") or row.evidence_type
            row.condition_json = {"condition": req.get("condition")}
            row.provenance_json = req.get("provenance") or row.provenance_json
        if key in outstanding_evidence:
            row.status = "evidence_required"
        elif key in pending_review:
            row.status = "review_required"
        elif key in outstanding_info:
            row.status = "information_required"
        else:
            row.status = "satisfied"
    if requirements:
        for key, row in rows.items():
            if key not in active_keys:
                row.status = "superseded"
