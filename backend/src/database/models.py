"""
SQLAlchemy ORM models for Insurance Claim Intake.
Strictly supports the 6 canonical insurance types:
Health, Senior Health, Home, Travel, Motor, Cyber.
"""
import uuid
from datetime import date, datetime, timezone
from sqlalchemy import (
    Column, String, Boolean, Date, DateTime, Numeric, Float, ForeignKey, Integer, JSON
)
from sqlalchemy.orm import declarative_base

from src.config import settings

_IS_PG = settings.DATABASE_URL.startswith("postgresql")

if _IS_PG:
    from sqlalchemy.dialects.postgresql import UUID as PgUUID, JSONB as PgJSONB

    def _UUID(*args, **kw):
        """Native PostgreSQL UUID column."""
        return Column(PgUUID(as_uuid=True), *args, **kw)

    def _JSONB(*args, **kw):
        """Native PostgreSQL JSONB column."""
        return Column(PgJSONB, *args, **kw)
else:
    # SQLite-compatible fallback for unit tests
    def _UUID(*args, **kw):  # type: ignore[misc]
        """String-based UUID column for SQLite."""
        return Column(String(36), *args, **kw)

    def _JSONB(*args, **kw):  # type: ignore[misc]
        """JSON column for SQLite."""
        return Column(JSON, *args, **kw)

Base = declarative_base()


class User(Base):
    """Registered application user (CLAIMANT or ADJUSTER)."""
    __tablename__ = "users"

    id = _UUID(primary_key=True, default=lambda: str(uuid.uuid4()))
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    phone = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # CLAIMANT | ADJUSTER
    status = Column(String, nullable=False, default="active")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                         onupdate=lambda: datetime.now(timezone.utc))


class Policy(Base):
    """Insurance policy record."""
    __tablename__ = "policies"

    id = _UUID(primary_key=True, default=lambda: str(uuid.uuid4()))
    policy_number = Column(String, unique=True, nullable=False)
    customer_id = _UUID(nullable=False, default=lambda: str(uuid.uuid4()))
    # Strict 6 types: health | senior_health | home | travel | motor | cyber
    policy_type = Column(String, nullable=False)
    coverage_amount = Column(Numeric, nullable=False)
    deductible = Column(Numeric, nullable=False)
    effective_date = Column(Date, nullable=False)
    expiry_date = Column(Date, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Adjuster(Base):
    """Insurance claim adjuster."""
    __tablename__ = "adjusters"

    id = _UUID(primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    # Specialization matching the 6 supported types: health | senior_health | home | travel | motor | cyber
    specialization = Column(String, nullable=False)
    claims_assigned = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)


class Claim(Base):
    """Insurance claim record."""
    __tablename__ = "claims"

    id = _UUID(primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id = Column(String, unique=True, nullable=False)
    claimant_id = _UUID(ForeignKey("users.id"), nullable=True, default=None)
    customer_id = Column(String, nullable=True, default=None)
    policy_id = _UUID(ForeignKey("policies.id"), nullable=True, default=None)
    claim_date = Column(Date, default=date.today)
    event_date = Column(Date)
    # Strict 6 types: health | senior_health | home | travel | motor | cyber
    insurance_type = Column(String)
    input_mode = Column(String, default="text")  # voice | text
    event_description = Column(String)
    estimated_claim_amount = Column(Numeric)
    extraction_confidence = Column(Float)
    validation_status = Column(String)

    # Claim lifecycle status: draft | verified | verification_failed
    status = Column(String, default="draft")

    # Conversational intake lifecycle: not_started | collecting | reviewing | pending_verification | verified | verification_failed
    conversation_status = Column(String, default="not_started")

    # Full structured ClaimState snapshot persisted as JSON between conversational turns
    pipeline_state = _JSONB(default=dict)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                         onupdate=lambda: datetime.now(timezone.utc))


class ConversationTurn(Base):
    """Chronological conversation turns for voice and text claims."""
    __tablename__ = "conversation_turns"

    id = _UUID(primary_key=True, default=lambda: str(uuid.uuid4()))
    claim_id = _UUID(ForeignKey("claims.id"), nullable=False, default=None)
    turn_number = Column(Integer, nullable=False)
    speaker = Column(String, nullable=False)          # "user" | "agent"
    text = Column(String, nullable=False)
    audio_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

