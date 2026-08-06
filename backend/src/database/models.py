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
    ticket_id = Column(String, unique=True, nullable=False)  # generated at intake, not just at routing
    policy_id = Column(UUID(as_uuid=True), ForeignKey("policies.id"), nullable=True)
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

    # "draft" -> created at intake, still collecting fields/docs/confirmation
    # "evaluated" -> evaluation graph has run and produced a final_decision
    status = Column(String, default="draft")
    final_decision = Column(String)          # need_more_info | need_documents | approved | denied | flagged_for_review | manual_review
    closure_status = Column(String)          # awaiting_user | pending_review | closed

    # Full ClaimState dict persisted as JSON between the intake call and the confirm call,
    # since each API request compiles/invokes the graph fresh (no in-memory session).
    pipeline_state = Column(JSONB, default=dict)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Document(Base):
    __tablename__ = "documents"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id = Column(UUID(as_uuid=True), ForeignKey("claims.id"), nullable=False)
    document_type = Column(String, nullable=False)   # damage_photo, repair_estimate, fir, etc.
    original_filename = Column(String)
    file_path = Column(String, nullable=False)        # local path in August; swap for S3 later without API changes
    mime_type = Column(String)
    file_size_bytes = Column(Integer)

    # OCR / classification fields exist now so September can populate them
    # without another migration; they are simply unused (NULL) in August.
    ocr_text = Column(String, nullable=True)
    extracted_metadata = Column(JSONB, default=dict)
    classification_confidence = Column(Float, nullable=True)

    uploaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class PaymentRequest(Base):
    """
    Stub only. Populated when a claim is auto-approved so the payout amount
    is on record, but no payment gateway is called. Finance/adjuster handles
    disbursement outside this system for the MVP.
    """
    __tablename__ = "payment_requests"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id = Column(UUID(as_uuid=True), ForeignKey("claims.id"), nullable=False)
    claimed_amount = Column(Numeric)
    deductible_amount = Column(Numeric)
    payout_amount = Column(Numeric)
    status = Column(String, default="pending_finance")  # stub status only
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id = Column(UUID(as_uuid=True), ForeignKey("claims.id"))
    action = Column(String, nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    details = Column(JSONB, default=dict)