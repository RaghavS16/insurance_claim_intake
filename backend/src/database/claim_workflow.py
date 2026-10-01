"""Transactional claim workflow primitives and audit helpers."""
from __future__ import annotations
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from src.database.models import Claim, Adjuster
from src.database.hardening_models import ClaimAssignment, ClaimAuditEvent, ClaimRequirement, ClaimEvidence

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


def build_submission_readiness(db: Session, claim: Claim, policy_verification: dict | None = None) -> dict:\n    """Return a deterministic readiness decision from durable workflow records.\n\n    This is intentionally independent from LLM conversation flags.\n    """\n    from src.domain.readiness import build_readiness\n\n    requirements = db.query(ClaimRequirement).filter(ClaimRequirement.claim_id == claim.id).all()\n    evidence = db.query(ClaimEvidence).filter(ClaimEvidence.claim_id == claim.id).all()\n    return build_readiness(\n        requirements=requirements,\n        policy_verification=policy_verification,\n        evidence_rows=evidence,\n        exceptions=[],\n    )\n\n\ndef transition_claim_if_allowed(\n    db: Session,\n    claim: Claim,\n    new_status: str,\n    *,\n    actor_user_id: str | None = None,\n    reason: str | None = None,\n) -> Claim:\n    """Explicit named wrapper used by service code to make transitions auditable."""\n    return transition_claim(db, claim, new_status, actor_user_id, reason)\n