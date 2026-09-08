"""
SQLAlchemy ORM models for Insurance Claim Intake.
Strictly supports the 6 canonical insurance types:
Health, Senior Health, Home, Travel, Motor, Cyber.
"""
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import (
    String, Boolean, Date, DateTime, Numeric, Float, ForeignKey, Integer, JSON
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.config import settings

_IS_PG = settings.DATABASE_URL.startswith("postgresql")

if _IS_PG:
    from sqlalchemy.dialects.postgresql import UUID as PgUUID, JSONB as PgJSONB

    def _UUID(*args, **kw):
        """Native PostgreSQL UUID column."""
        return mapped_column(PgUUID(as_uuid=True), *args, **kw)

    def _JSONB(*args, **kw):
        """Native PostgreSQL JSONB column."""
        return mapped_column(PgJSONB, *args, **kw)
else:
    # SQLite-compatible fallback for unit tests
    def _UUID(*args, **kw):  # type: ignore[misc]
        """String-based UUID column for SQLite."""
        return mapped_column(String(36), *args, **kw)

    def _JSONB(*args, **kw):  # type: ignore[misc]
        """JSON column for SQLite."""
        return mapped_column(JSON, *args, **kw)

class Base(DeclarativeBase):
    pass


class User(Base):
    """Registered application user (CLAIMANT, ADJUSTER, or ADMIN)."""
    __tablename__ = "users"

    id: Mapped[str] = _UUID(primary_key=True, default=lambda: str(uuid.uuid4()))
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)  # CLAIMANT | ADJUSTER | ADMIN
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc),
                         onupdate=lambda: datetime.now(timezone.utc))


class Policy(Base):
    """Insurance policy record."""
    __tablename__ = "policies"

    id: Mapped[str] = _UUID(primary_key=True, default=lambda: str(uuid.uuid4()))
    policy_number: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    customer_id: Mapped[Optional[str]] = _UUID(ForeignKey("users.id"), nullable=True, default=None)
    # Strict 6 types: health | senior_health | home | travel | motor | cyber
    policy_type: Mapped[str] = mapped_column(String, nullable=False)
    coverage_amount: Mapped[float] = mapped_column(Numeric, nullable=False)
    deductible: Mapped[float] = mapped_column(Numeric, nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    policyholder_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    policyholder_dob: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    policyholder_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    policyholder_phone_last4: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    linked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    link_attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class RevokedToken(Base):
    """Blacklisted JWT tokens for server-side revocation / logout."""
    __tablename__ = "revoked_tokens"

    id: Mapped[str] = _UUID(primary_key=True, default=lambda: str(uuid.uuid4()))
    token_jti: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    user_id: Mapped[Optional[str]] = _UUID(ForeignKey("users.id"), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class PolicyLinkAudit(Base):
    """Audit log for policy linking attempts."""
    __tablename__ = "policy_link_audit"

    id: Mapped[str] = _UUID(primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = _UUID(ForeignKey("users.id"), nullable=False)
    policy_number: Mapped[str] = mapped_column(String, nullable=False)
    outcome: Mapped[str] = mapped_column(String, nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class Adjuster(Base):
    """Insurance claim adjuster."""
    __tablename__ = "adjusters"

    id: Mapped[str] = _UUID(primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Specialization matching the 6 supported types: health | senior_health | home | travel | motor | cyber
    specialization: Mapped[str] = mapped_column(String, nullable=False)
    claims_assigned: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Claim(Base):
    """Insurance claim record."""
    __tablename__ = "claims"

    id: Mapped[str] = _UUID(primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    claimant_id: Mapped[Optional[str]] = _UUID(ForeignKey("users.id"), nullable=True, default=None)
    customer_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, default=None)
    policy_id: Mapped[Optional[str]] = _UUID(ForeignKey("policies.id"), nullable=True, default=None)
    claim_date: Mapped[Optional[date]] = mapped_column(Date, default=date.today)
    event_date: Mapped[Optional[date]] = mapped_column(Date)
    # Strict 6 types: health | senior_health | home | travel | motor | cyber
    insurance_type: Mapped[Optional[str]] = mapped_column(String)
    input_mode: Mapped[Optional[str]] = mapped_column(String, default="text")  # voice | text
    event_description: Mapped[Optional[str]] = mapped_column(String)
    estimated_claim_amount: Mapped[Optional[float]] = mapped_column(Numeric)
    extraction_confidence: Mapped[Optional[float]] = mapped_column(Float)
    validation_status: Mapped[Optional[str]] = mapped_column(String)

    # Claim lifecycle status: draft | verified | verification_failed
    status: Mapped[str] = mapped_column(String, default="draft")

    # Conversational intake lifecycle: not_started | collecting | reviewing | pending_verification | verified | verification_failed
    conversation_status: Mapped[str] = mapped_column(String, default="not_started")

    # Full structured ClaimState snapshot persisted as JSON between conversational turns
    pipeline_state: Mapped[Dict[str, Any]] = _JSONB(default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc),
                         onupdate=lambda: datetime.now(timezone.utc))


class PasswordResetOTP(Base):
    """One-time password record for forgot-password email verification."""
    __tablename__ = "password_reset_otps"

    id: Mapped[str] = _UUID(primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = _UUID(ForeignKey("users.id"), nullable=False)
    otp_hash: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)  # True once used to reset password
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class ConversationTurn(Base):
    """Chronological conversation turns for voice and text claims."""
    __tablename__ = "conversation_turns"

    id: Mapped[str] = _UUID(primary_key=True, default=lambda: str(uuid.uuid4()))
    claim_id: Mapped[str] = _UUID(ForeignKey("claims.id"), nullable=False, default=None)
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[str] = mapped_column(String, nullable=False)          # "user" | "agent"
    text: Mapped[str] = mapped_column(String, nullable=False)
    audio_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
