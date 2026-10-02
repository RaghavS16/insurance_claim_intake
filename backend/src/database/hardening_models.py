"""Normalized production claim workflow models."""
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import uuid
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column
from src.database.models import Base, _UUID, _JSONB

def _now(): return datetime.now(timezone.utc)
def _uuid(): return str(uuid.uuid4())

class ClaimAssignment(Base):
    __tablename__="claim_assignments"
    __table_args__=(Index("ix_claim_assignments_active","claim_id","is_active"),Index("ix_claim_assignments_adjuster","adjuster_id","is_active"))
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    claim_id: Mapped[str]=_UUID(ForeignKey("claims.id",ondelete="CASCADE"),nullable=False)
    adjuster_id: Mapped[str]=_UUID(ForeignKey("adjusters.id",ondelete="RESTRICT"),nullable=False)
    assigned_by: Mapped[Optional[str]]=_UUID(ForeignKey("users.id",ondelete="SET NULL"))
    reason: Mapped[Optional[str]]=mapped_column(Text)
    is_active: Mapped[bool]=mapped_column(Boolean,nullable=False,default=True)
    assigned_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=_now)
    unassigned_at: Mapped[Optional[datetime]]=mapped_column(DateTime(timezone=True))

class ClaimRequirement(Base):
    __tablename__="claim_requirements"
    __table_args__=(UniqueConstraint("claim_id","requirement_key",name="uq_claim_requirement_key"),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    claim_id: Mapped[str]=mapped_column(ForeignKey("claims.id",ondelete="CASCADE"),nullable=False)
    requirement_key: Mapped[str]=mapped_column(String(150),nullable=False)
    label: Mapped[str]=mapped_column(String(500),nullable=False)
    question_hint: Mapped[Optional[str]]=mapped_column(Text)
    status: Mapped[str]=mapped_column(String(40),nullable=False,default="unknown",index=True)
    required: Mapped[bool]=mapped_column(Boolean,nullable=False,default=True)
    evidence_type: Mapped[Optional[str]]=mapped_column(String(100))
    condition_json: Mapped[Dict[str,Any]]=mapped_column(JSON,nullable=False,default=dict)
    provenance_json: Mapped[Dict[str,Any]]=mapped_column(JSON,nullable=False,default=dict)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=_now)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=_now,onupdate=_now)

class ClaimEvidence(Base):
    __tablename__="claim_evidence"
    __table_args__=(Index("ix_claim_evidence_claim","claim_id"),Index("ix_claim_evidence_status","status"))
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    claim_id: Mapped[str]=mapped_column(ForeignKey("claims.id",ondelete="CASCADE"),nullable=False)
    uploaded_by: Mapped[Optional[str]]=_UUID(ForeignKey("users.id",ondelete="SET NULL"))
    requirement_id: Mapped[Optional[str]]=mapped_column(ForeignKey("claim_requirements.id",ondelete="SET NULL"))
    object_key: Mapped[str]=mapped_column(String(1000),nullable=False,unique=True)
    original_filename: Mapped[str]=mapped_column(String(500),nullable=False)
    content_type: Mapped[str]=mapped_column(String(200),nullable=False)
    size_bytes: Mapped[int]=mapped_column(Integer,nullable=False)
    sha256: Mapped[Optional[str]]=mapped_column(String(64),index=True)
    status: Mapped[str]=mapped_column(String(40),nullable=False,default="uploaded")
    document_type: Mapped[Optional[str]]=mapped_column(String(100))
    verification_status: Mapped[str]=mapped_column(String(40),nullable=False,default="REVIEW_REQUIRED",index=True)
    verification_confidence: Mapped[Optional[float]]=mapped_column()
    detected_document_type: Mapped[Optional[str]]=mapped_column(String(150))
    requested_evidence_type: Mapped[Optional[str]]=mapped_column(String(150))
    request_id: Mapped[Optional[str]]=mapped_column(String(36),ForeignKey("claim_evidence_requests.id",ondelete="SET NULL"),nullable=True)
    analysis_json: Mapped[Dict[str,Any]]=mapped_column(JSON,nullable=False,default=dict)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=_now)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=_now,onupdate=_now)

class ClaimEvidenceRequest(Base):
    __tablename__="claim_evidence_requests"
    __table_args__=(Index("ix_claim_evidence_requests_claim","claim_id"), Index("ix_claim_evidence_requests_status","status"))
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    claim_id: Mapped[str]=_UUID(ForeignKey("claims.id",ondelete="CASCADE"),nullable=False)
    adjuster_id: Mapped[str]=_UUID(ForeignKey("adjusters.id",ondelete="RESTRICT"),nullable=False)
    request_text: Mapped[str]=mapped_column(Text,nullable=False)
    status: Mapped[str]=mapped_column(String(40),nullable=False,default="open")
    response_note: Mapped[Optional[str]]=mapped_column(Text)
    requested_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=_now)
    responded_at: Mapped[Optional[datetime]]=mapped_column(DateTime(timezone=True))

class ClaimDecision(Base):
    __tablename__="claim_decisions"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    claim_id: Mapped[str]=mapped_column(ForeignKey("claims.id",ondelete="CASCADE"),nullable=False,index=True)
    adjuster_id: Mapped[str]=mapped_column(ForeignKey("adjusters.id",ondelete="RESTRICT"),nullable=False)
    decision: Mapped[str]=mapped_column(String(40),nullable=False)
    rationale: Mapped[str]=mapped_column(Text,nullable=False)
    approved_amount: Mapped[Optional[float]]=mapped_column(Numeric)
    ai_recommendation_json: Mapped[Dict[str,Any]]=mapped_column(JSON,nullable=False,default=dict)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=_now)

class ClaimNote(Base):
    __tablename__="claim_notes"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    claim_id: Mapped[str]=mapped_column(ForeignKey("claims.id",ondelete="CASCADE"),nullable=False,index=True)
    author_user_id: Mapped[str]=mapped_column(ForeignKey("users.id",ondelete="RESTRICT"),nullable=False)
    note: Mapped[str]=mapped_column(Text,nullable=False)
    visibility: Mapped[str]=mapped_column(String(30),nullable=False,default="internal")
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=_now)

class ClaimAuditEvent(Base):
    __tablename__="claim_audit_events"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    claim_id: Mapped[str]=mapped_column(ForeignKey("claims.id",ondelete="CASCADE"),nullable=False,index=True)
    actor_user_id: Mapped[Optional[str]]=_UUID(ForeignKey("users.id",ondelete="SET NULL"))
    event_type: Mapped[str]=mapped_column(String(100),nullable=False,index=True)
    old_value_json: Mapped[Dict[str,Any]]=mapped_column(JSON,nullable=False,default=dict)
    new_value_json: Mapped[Dict[str,Any]]=mapped_column(JSON,nullable=False,default=dict)
    reason: Mapped[Optional[str]]=mapped_column(Text)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=_now)

class CopilotAnalysis(Base):
    __tablename__="copilot_analyses"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    claim_id: Mapped[str]=mapped_column(ForeignKey("claims.id",ondelete="CASCADE"),nullable=False,index=True)
    claim_version: Mapped[int]=mapped_column(Integer,nullable=False,default=1)
    knowledge_version: Mapped[str]=mapped_column(String(200),nullable=False,default="unknown")
    model: Mapped[str]=mapped_column(String(200),nullable=False)
    prompt_version: Mapped[str]=mapped_column(String(100),nullable=False,default="v1")
    result_json: Mapped[Dict[str,Any]]=mapped_column(JSON,nullable=False,default=dict)
    citations_json: Mapped[list[dict[str,Any]]]=mapped_column(JSON,nullable=False,default=list)
    stale: Mapped[bool]=mapped_column(Boolean,nullable=False,default=False,index=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=_now)


class ClaimFact(Base):
    """Canonical claim fact with explicit provenance and lifecycle state."""
    __tablename__ = "claim_facts"
    __table_args__ = (
        UniqueConstraint("claim_id", "fact_key", name="uq_claim_fact_key"),
        Index("ix_claim_facts_claim", "claim_id"),
        Index("ix_claim_facts_state", "state"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    claim_id: Mapped[str] = _UUID(ForeignKey("claims.id", ondelete="CASCADE"), nullable=False)
    fact_key: Mapped[str] = mapped_column(String(150), nullable=False)
    value_json: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    state: Mapped[str] = mapped_column(String(40), nullable=False, default="PROPOSED")
    source_type: Mapped[str] = mapped_column(String(60), nullable=False)
    source_id: Mapped[Optional[str]] = mapped_column(String(150))
    confidence: Mapped[Optional[float]] = mapped_column()
    provenance_json: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class ClaimException(Base):
    """Durable exception/hold requiring human or deterministic resolution."""
    __tablename__ = "claim_exceptions"
    __table_args__ = (
        Index("ix_claim_exceptions_claim", "claim_id", "blocking", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    claim_id: Mapped[str] = _UUID(ForeignKey("claims.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(30), nullable=False, default="medium")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(60), nullable=False, default="SYSTEM_RULE")
    source_id: Mapped[Optional[str]] = mapped_column(String(150))
    blocking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open")
    resolution_json: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class ClaimSubmission(Base):
    """Exactly-once submission record for an accepted claim."""
    __tablename__ = "claim_submissions"
    __table_args__ = (
        UniqueConstraint("claim_id", name="uq_claim_submission_claim"),
        UniqueConstraint("idempotency_key", name="uq_claim_submission_idempotency"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    claim_id: Mapped[str] = _UUID(ForeignKey("claims.id", ondelete="CASCADE"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="accepted")
    submitted_by: Mapped[Optional[str]] = _UUID(ForeignKey("users.id", ondelete="SET NULL"))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    result_json: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class OutboxEvent(Base):
    """Durable transactional event for work that must survive process restarts."""
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("ix_outbox_events_dispatch", "status", "next_attempt_at"),
        UniqueConstraint("idempotency_key", name="uq_outbox_events_idempotency"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(150), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(150), nullable=False)
    payload_json: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, index=True)
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)


class MFAChallenge(Base):
    """Short-lived server-side MFA challenge issued after password verification."""
    __tablename__ = "mfa_challenges"
    __table_args__ = (
        UniqueConstraint("challenge_token_hash", name="uq_mfa_challenge_token_hash"),
        Index("ix_mfa_challenges_user_expires", "user_id", "expires_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = _UUID(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    challenge_token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consumed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)


class MFARecoveryCode(Base):
    """One-time recovery code stored only as a hash."""
    __tablename__ = "mfa_recovery_codes"
    __table_args__ = (
        UniqueConstraint("user_id", "code_hash", name="uq_mfa_recovery_user_code"),
        Index("ix_mfa_recovery_user", "user_id", "consumed"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = _UUID(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    consumed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)


class Tenant(Base):
    """Tenant boundary for all claimant/adjuster data."""
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)


class TenantMembership(Base):
    __tablename__ = "tenant_memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_tenant_membership"),
        Index("ix_tenant_membership_user", "user_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = _UUID(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
