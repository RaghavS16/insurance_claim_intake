import uuid
from datetime import date, datetime, timezone
from sqlalchemy import (
    Column, String, Boolean, Date, DateTime, Numeric, Float, ForeignKey, Integer
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Policy(Base):
    __tablename__ = "policies"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_number = Column(String, unique=True, nullable=False)
    customer_id = Column(UUID(as_uuid=True), nullable=False)
    policy_type = Column(String, nullable=False)
    coverage_amount = Column(Numeric, nullable=False)
    deductible = Column(Numeric, nullable=False)
    effective_date = Column(Date, nullable=False)
    expiry_date = Column(Date, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Adjuster(Base):
    __tablename__ = "adjusters"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    specialization = Column(String, nullable=False)
    claims_assigned = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)


class Claim(Base):
    __tablename__ = "claims"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_id = Column(UUID(as_uuid=True), ForeignKey("policies.id"))
    claim_date = Column(Date, default=date.today)
    incident_date = Column(Date)
    claim_type = Column(String)
    input_mode = Column(String, default="text")
    description = Column(String)
    claimed_amount = Column(Numeric)
    extraction_confidence = Column(Float)
    validation_status = Column(String)
    fraud_score = Column(Float)
    fraud_flags = Column(JSONB, default=list)
    assigned_adjuster_id = Column(UUID(as_uuid=True), ForeignKey("adjusters.id"))
    status = Column(String, default="open")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id = Column(UUID(as_uuid=True), ForeignKey("claims.id"))
    action = Column(String, nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    details = Column(JSONB, default=dict)