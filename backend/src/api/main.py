"""
FastAPI application for Insurance Claim Intake and Conversation Management.

Production-hardened entry point. This module acts as a slim orchestrator:
- Configures middleware, exception handlers, and lifecycle events
- Includes separated route modules for auth, claims, adjuster, and knowledge
- Provides centralized authentication dependencies
- Seeds canonical data on first startup

All business logic has been extracted into dedicated route modules:
- auth_routes.py: Authentication (signup, login, logout)
- claim_routes.py: Claim intake, confirmation, documents
"""
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.config import settings
from src.database.session import get_db, engine, SessionLocal, dispose_engine
from src.database.models import Base, Claim, Policy, Adjuster, ConversationTurn, User, PasswordResetOTP, RevokedToken
from src.api.voice_ws import router as voice_router
from src.utils.logger import app_logger
from src.utils.auth import get_password_hash, verify_password, create_access_token, verify_token, is_token_revoked
from src.utils.tracing import CorrelationIdMiddleware, get_correlation_id

# Route modules
from src.api import auth_routes, claim_routes, policy_routes, admin_routes

# Shared auth dependencies (also exported for backward compatibility)
from src.api.deps import get_current_user, get_current_user_id, require_role  # noqa: F401

logger = app_logger


# ---------------------------------------------------------------------------
# Note: get_current_user, get_current_user_id, and require_role are now defined
# in src.api.deps and re-exported from this module for backward compatibility.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Auth endpoint: /api/v1/auth/me (kept here because it uses get_current_user directly)
# ---------------------------------------------------------------------------
# (Placed after the auth_routes router is included below)


# ---------------------------------------------------------------------------
# Database Initialization & Seeding
# ---------------------------------------------------------------------------
def _init_db_and_seeds():
    """Ensure database schema is created and seed initial canonical records if empty."""
    try:
        Base.metadata.create_all(bind=engine)

        # Safe auto-migration: dynamically add columns to claims and policies if missing
        from sqlalchemy import inspect, text
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        is_pg = settings.DATABASE_URL.startswith("postgresql")

        with engine.connect() as conn:
            if "claims" in tables:
                claim_cols = [c["name"] for c in inspector.get_columns("claims")]
                if "customer_id" not in claim_cols:
                    logger.info("Database auto-migration: adding customer_id to claims table")
                    conn.execute(text("ALTER TABLE claims ADD COLUMN customer_id VARCHAR"))
                    conn.commit()
                if "claimant_id" not in claim_cols:
                    logger.info("Database auto-migration: adding claimant_id to claims table")
                    col_type = "UUID REFERENCES users(id)" if is_pg else "VARCHAR"
                    conn.execute(text(f"ALTER TABLE claims ADD COLUMN claimant_id {col_type}"))
                    conn.commit()

            if "policies" in tables:
                policy_cols = [c["name"] for c in inspector.get_columns("policies")]
                if "policyholder_name" not in policy_cols:
                    logger.info("Database auto-migration: adding policyholder_name to policies table")
                    conn.execute(text("ALTER TABLE policies ADD COLUMN policyholder_name VARCHAR"))
                    conn.commit()
                if "policyholder_dob" not in policy_cols:
                    logger.info("Database auto-migration: adding policyholder_dob to policies table")
                    conn.execute(text("ALTER TABLE policies ADD COLUMN policyholder_dob DATE"))
                    conn.commit()
                if "policyholder_phone_last4" not in policy_cols:
                    logger.info("Database auto-migration: adding policyholder_phone_last4 to policies table")
                    conn.execute(text("ALTER TABLE policies ADD COLUMN policyholder_phone_last4 VARCHAR(4)"))
                    conn.commit()
                if "linked_at" not in policy_cols:
                    logger.info("Database auto-migration: adding linked_at to policies table")
                    dt_type = "TIMESTAMPTZ" if is_pg else "DATETIME"
                    conn.execute(text(f"ALTER TABLE policies ADD COLUMN linked_at {dt_type}"))
                    conn.commit()
                if "link_attempts" not in policy_cols:
                    logger.info("Database auto-migration: adding link_attempts to policies table")
                    conn.execute(text("ALTER TABLE policies ADD COLUMN link_attempts INTEGER DEFAULT 0"))
                    conn.commit()

                if is_pg:
                    try:
                        conn.execute(text("ALTER TABLE policies ALTER COLUMN customer_id DROP NOT NULL"))
                        conn.commit()
                    except Exception:
                        pass

            if is_pg and "users" in tables:
                try:
                    conn.execute(text("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check"))
                    conn.execute(text("ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('CLAIMANT', 'ADJUSTER', 'ADMIN'))"))
                    conn.commit()
                except Exception:
                    pass

            if "password_reset_otps" not in tables:
                logger.info("Database auto-migration: creating password_reset_otps table")
                Base.metadata.create_all(bind=conn, tables=[Base.metadata.tables["password_reset_otps"]], checkfirst=True)
                conn.commit()

            if "revoked_tokens" not in tables:
                logger.info("Database auto-migration: creating revoked_tokens table")
                Base.metadata.create_all(bind=conn, tables=[Base.metadata.tables["revoked_tokens"]], checkfirst=True)
                conn.commit()

            if "adjusters" in tables:
                adjuster_cols = [c["name"] for c in inspector.get_columns("adjusters")]
                if "phone" not in adjuster_cols:
                    logger.info("Database auto-migration: adding phone to adjusters table")
                    conn.execute(text("ALTER TABLE adjusters ADD COLUMN phone VARCHAR"))
                    conn.commit()

            if "policies" in tables:
                try:
                    conn.execute(text("UPDATE policies SET is_active = 1 WHERE is_active IS NULL"))
                    conn.commit()
                except Exception:
                    pass

        # Seed canonical policies and users in development and test environments
        if settings.ENVIRONMENT in ("development", "test"):
            db = SessionLocal()
            try:
                # 1. Seed policies if empty
                if db.query(Policy).first() is None:
                    canonical_policies = [
                        ("MOT-5521", "motor", 500000, 5000, date(2024, 1, 1), date(2030, 12, 31), True, "John Doe", date(1990, 5, 15), "1234"),
                        ("XYZ123", "motor", 500000, 10000, date(2024, 1, 1), date(2030, 12, 31), True, "John Doe", date(1990, 5, 15), "1234"),
                        ("HOME456", "home", 1000000, 10000, date(2025, 3, 1), date(2026, 2, 28), True, "Alice Smith", date(1985, 8, 20), "5678"),
                        ("HLT-7789", "health", 800000, 2000, date(2024, 6, 1), date(2026, 5, 31), True, "Robert Johnson", date(1978, 12, 10), "9012"),
                        ("SNR-9912", "senior_health", 600000, 3000, date(2024, 1, 1), date(2027, 12, 31), True, "Mary Davis", date(1955, 3, 25), "3456"),
                        ("TRV-3301", "travel", 200000, 1000, date(2025, 1, 1), date(2025, 12, 31), True, "David Wilson", date(1992, 11, 5), "7890"),
                        ("CYB-8820", "cyber", 1500000, 15000, date(2024, 1, 1), date(2026, 12, 31), True, "TechCorp LLC", date(2000, 1, 1), "0000"),
                    ]
                    for pnum, ptype, cov, ded, eff, exp, active, hname, hdob, hphone in canonical_policies:
                        db.add(Policy(
                            id=str(uuid.uuid4()),
                            policy_number=pnum,
                            customer_id=None,
                            policy_type=ptype,
                            coverage_amount=cov,
                            deductible=ded,
                            effective_date=eff,
                            expiry_date=exp,
                            is_active=active,
                            policyholder_name=hname,
                            policyholder_dob=hdob,
                            policyholder_phone_last4=hphone,
                            link_attempts=0,
                        ))
                    db.commit()

                # 2. Seed adjusters roster if empty
                canonical_adjusters = [
                    ("motor", "Priya Sharma", "priya.motor@insure.co", "+1 (555) 234-0101"),
                    ("home", "Rohan Mehta", "rohan.home@insure.co", "+1 (555) 234-0102"),
                    ("health", "Dr. Anita Roy", "anita.health@insure.co", "+1 (555) 234-0103"),
                    ("senior_health", "Dr. V. Rao", "rao.senior@insure.co", "+1 (555) 234-0104"),
                    ("travel", "Vikram Sen", "vikram.travel@insure.co", "+1 (555) 234-0105"),
                    ("cyber", "Neha Kapoor", "neha.cyber@insure.co", "+1 (555) 234-0106"),
                ]
                for spec, name, email, phone in canonical_adjusters:
                    existing_adj = db.query(Adjuster).filter(Adjuster.email == email).first()
                    if not existing_adj:
                        db.add(Adjuster(
                            id=str(uuid.uuid4()),
                            name=name,
                            email=email,
                            phone=phone,
                            specialization=spec,
                            claims_assigned=0,
                            is_active=True,
                        ))
                db.commit()

                # 3. Seed canonical users (Admin, Adjusters, Claimant)
                canonical_users = [
                    ("System Admin", "admin@insure.co", "+1 (555) 000-0001", "AdminPassword123!", "ADMIN"),
                    ("Test Admin", "admin@test.com", "+1 (555) 000-0002", "AdminPassword123!", "ADMIN"),
                    ("John Doe", "john@test.com", "1234", "ClaimantPassword123!", "CLAIMANT"),
                ]
                # Add adjusters to canonical users
                for spec, name, email, phone in canonical_adjusters:
                    canonical_users.append((name, email, phone, "AdjusterPassword123!", "ADJUSTER"))

                for uname, uemail, uphone, upass, urole in canonical_users:
                    existing_u = db.query(User).filter(User.email == uemail).first()
                    if not existing_u:
                        db.add(User(
                            id=str(uuid.uuid4()),
                            full_name=uname,
                            email=uemail,
                            phone=uphone,
                            password_hash=get_password_hash(upass),
                            role=urole,
                            status="active",
                        ))
                    else:
                        # Ensure active status and valid role
                        if existing_u.status != "active":
                            existing_u.status = "active"
                        if existing_u.role != urole:
                            existing_u.role = urole

                db.commit()
                logger.info("Database initialized with canonical policies, adjusters, and users (including Admin).")
            finally:
                db.close()
        else:
            logger.info("Production environment detected: Skipping automatic demo record seeding.")
    except Exception as exc:
        logger.warning("Database schema check notice: %s", exc)


# ---------------------------------------------------------------------------
# Application Lifecycle
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle manager."""
    settings.validate_startup()
    _init_db_and_seeds()
    yield
    # Graceful shutdown: dispose connection pool
    dispose_engine()
    logger.info("Application shutdown complete.")


app = FastAPI(
    title="Insurance Claim Intake Voice Agent API",
    description="Conversational voice-first insurance claim intake service",
    version="2.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Tracing & CORS Middleware
# ---------------------------------------------------------------------------
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Exception Handlers
# ---------------------------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return API-safe JSON for request validation errors."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors(), "message": "Invalid request payload."},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions and return safe 500 error (no stack trace to client)."""
    logger.exception("Unhandled server exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred. Please try again later."},
    )


# ---------------------------------------------------------------------------
# Health & Root
# ---------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/health")
def health_check():
    """Health check endpoint for container probes and monitoring."""
    return {"status": "ok", "environment": settings.ENVIRONMENT}


# ---------------------------------------------------------------------------
# Include Route Modules with Dependency Injection
# ---------------------------------------------------------------------------
# Override the `current_user` dependency placeholder in each route module
# by configuring the router's dependency overrides at inclusion time.

# Auth routes (signup, login, logout)
app.include_router(auth_routes.router)

# The /me endpoint needs get_current_user from this module, so we define it here
@app.get("/api/v1/auth/me", tags=["Authentication"])
def get_me(current_user: User = Depends(get_current_user)):
    """Retrieve the currently authenticated user's profile."""
    return {
        "id": current_user.id,
        "full_name": current_user.full_name,
        "email": current_user.email,
        "phone": current_user.phone,
        "role": current_user.role,
        "status": current_user.status,
    }


# Claim routes — inject get_current_user dependency
claim_routes.router.dependencies = []
for route in claim_routes.router.routes:
    # Override the placeholder Depends() with actual get_current_user
    pass
app.include_router(
    claim_routes.router,
    dependencies=[Depends(get_current_user)],
)

# Policy routes — inject get_current_user dependency
app.include_router(
    policy_routes.router,
    dependencies=[Depends(get_current_user)],
)

# Admin routes — inject get_current_user dependency
app.include_router(
    admin_routes.router,
    dependencies=[Depends(get_current_user)],
)

# Voice WebSocket router
app.include_router(voice_router)