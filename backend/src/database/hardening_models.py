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
    claim_id: Mapped[str]=mapped_column(ForeignKey("claims.id",ondelete="CASCADE"),nullable=False)
    uploaded_by: Mapped[Optional[str]]=_UUID(ForeignKey("users.id",ondelete="SET NULL"))
    requirement_id: Mapped[Optional[str]]=mapped_column(ForeignKey("claim_requirements.id",ondelete="SET NULL"))
    object_key: Mapped[str]=mapped_column(String(1000),nullable=False,unique=True)
    original_filename: Mapped[str]=mapped_column(String(500),nullable=False)
    content_type: Mapped[str]=mapped_column(String(200),nullable=False)
    size_bytes: Mapped[int]=mapped_column(Integer,nullable=False)
    sha256: Mapped[Optional[str]]=mapped_column(String(64),index=True)
    status: Mapped[str]=mapped_column(String(40),nullable=False,default="uploaded",index=True)
    document_type: Mapped[Optional[str]]=mapped_column(String(100))
    verification_status: Mapped[str]=mapped_column(String(40),nullable=False,default="REVIEW_REQUIRED",index=True)
    verification_confidence: Mapped[Optional[float]]=mapped_column()
    detected_document_type: Mapped[Optional[str]]=mapped_column(String(150))
    requested_evidence_type: Mapped[Optional[str]]=mapped_column(String(150))
    analysis_json: Mapped[Dict[str,Any]]=mapped_column(JSON,nullable=False,default=dict)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=_now)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=_now,onupdate=_now)

class ClaimDecision(Base):
    __tablename__="claim_decisions"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=_uuid)
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
    claim_id: Mapped[str]=mapped_column(ForeignKey("claims.id",ondelete="CASCADE"),nullable=False,index=True)
    author_user_id: Mapped[str]=mapped_column(ForeignKey("users.id",ondelete="RESTRICT"),nullable=False)
    note: Mapped[str]=mapped_column(Text,nullable=False)
    visibility: Mapped[str]=mapped_column(String(30),nullable=False,default="internal")
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=_now)

class ClaimAuditEvent(Base):
    __tablename__="claim_audit_events"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=_uuid)
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
    claim_id: Mapped[str]=mapped_column(ForeignKey("claims.id",ondelete="CASCADE"),nullable=False,index=True)
    claim_version: Mapped[int]=mapped_column(Integer,nullable=False,default=1)
    knowledge_version: Mapped[str]=mapped_column(String(200),nullable=False,default="unknown")
    model: Mapped[str]=mapped_column(String(200),nullable=False)
    prompt_version: Mapped[str]=mapped_column(String(100),nullable=False,default="v1")
    result_json: Mapped[Dict[str,Any]]=mapped_column(JSON,nullable=False,default=dict)
    citations_json: Mapped[list[dict[str,Any]]]=mapped_column(JSON,nullable=False,default=list)
    stale: Mapped[bool]=mapped_column(Boolean,nullable=False,default=False,index=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=_now)
