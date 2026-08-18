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
- adjuster_routes.py: Adjuster review pipeline
- knowledge_routes.py: Knowledge document management
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
from src.database.models import Base, Claim, Document, Policy, Adjuster, ConversationTurn, User, KnowledgeDocument
from src.api.voice_ws import router as voice_router
from src.utils.logger import app_logger
from src.utils.auth import get_password_hash, verify_password, create_access_token, verify_token

# Route modules
from src.api import auth_routes, claim_routes, adjuster_routes, knowledge_routes

logger = app_logger
security_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Centralized Authentication Dependencies
# ---------------------------------------------------------------------------
def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    Extract and verify JWT token to fetch the currently authenticated user.

    SECURITY: The X-User-ID header fallback is ONLY available in test environments.
    Production/staging environments strictly require a valid JWT bearer token.
    """
    token = None
    if credentials:
        token = credentials.credentials

    uid = None
    if token:
        payload = verify_token(token)
        if payload:
            uid = payload.get("sub")
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated: Invalid or expired token."
            )
    else:
        # X-User-ID fallback is ONLY available in test environment
        if settings.ENVIRONMENT == "test":
            uid = request.headers.get("X-User-ID")
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required: missing bearer token."
            )

    if not uid:
        if settings.ENVIRONMENT == "test" and not request.headers.get("X-Test-No-Fallback"):
            uid = "TEST_USER_ID"
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required."
            )

    # Fetch user from DB
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        if settings.ENVIRONMENT == "test":
            # Autocreate mock user dynamically to prevent breaking existing Phase 1 tests
            user = db.query(User).filter(User.email == f"{uid.lower()}@test.com").first()
            if not user:
                user = User(
                    id=uid,
                    full_name=uid,
                    email=f"{uid.lower()}@test.com",
                    phone="",
                    password_hash=get_password_hash("test-password"),
                    role="CLAIMANT",
                    status="active"
                )
                db.add(user)
                db.commit()
                db.refresh(user)
            return user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: User not found."
        )
    return user


def get_current_user_id(current_user: User = Depends(get_current_user)) -> str:
    """Dependency helper to get the authenticated user ID string."""
    return str(current_user.id)


def require_role(allowed_roles: List[str]):
    """Enforce that the authenticated user possesses an allowed role."""
    def dependency(current_user: User = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Role '{current_user.role}' not permitted."
            )
        return current_user
    return dependency


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

        # Safe SQLite migration: dynamically add customer_id/claimant_id to claims if missing
        from sqlalchemy import inspect, text
        inspector = inspect(engine)
        if "claims" in inspector.get_table_names():
            columns = [c["name"] for c in inspector.get_columns("claims")]
            with engine.connect() as conn:
                if "customer_id" not in columns:
                    logger.info("Database auto-migration: adding customer_id to claims table")
                    conn.execute(text("ALTER TABLE claims ADD COLUMN customer_id VARCHAR"))
                    conn.commit()
                if "claimant_id" not in columns:
                    logger.info("Database auto-migration: adding claimant_id to claims table")
                    col_type = "UUID REFERENCES users(id)" if settings.DATABASE_URL.startswith("postgresql") else "VARCHAR"
                    conn.execute(text(f"ALTER TABLE claims ADD COLUMN claimant_id {col_type}"))
                    conn.commit()

        db = SessionLocal()
        try:
            # Seed policies if empty
            if db.query(Policy).first() is None:
                canonical_policies = [
                    ("MOT-5521", "motor", 500000, 5000, date(2024, 1, 1), date(2030, 12, 31), True),
                    ("XYZ123", "motor", 500000, 10000, date(2024, 1, 1), date(2030, 12, 31), True),
                    ("HOME456", "home", 1000000, 10000, date(2025, 3, 1), date(2026, 2, 28), True),
                    ("HLT-7789", "health", 800000, 2000, date(2024, 6, 1), date(2026, 5, 31), True),
                    ("SNR-9912", "senior_health", 600000, 3000, date(2024, 1, 1), date(2027, 12, 31), True),
                    ("TRV-3301", "travel", 200000, 1000, date(2025, 1, 1), date(2025, 12, 31), True),
                    ("CYB-8820", "cyber", 1500000, 15000, date(2024, 1, 1), date(2026, 12, 31), True),
                ]
                for pnum, ptype, cov, ded, eff, exp, active in canonical_policies:
                    db.add(Policy(
                        id=str(uuid.uuid4()),
                        policy_number=pnum,
                        customer_id=str(uuid.uuid4()),
                        policy_type=ptype,
                        coverage_amount=cov,
                        deductible=ded,
                        effective_date=eff,
                        expiry_date=exp,
                        is_active=active,
                    ))

                canonical_adjusters = [
                    ("motor", "Priya Sharma", "priya.motor@insure.co"),
                    ("home", "Rohan Mehta", "rohan.home@insure.co"),
                    ("health", "Dr. Anita Roy", "anita.health@insure.co"),
                    ("senior_health", "Dr. V. Rao", "rao.senior@insure.co"),
                    ("travel", "Vikram Sen", "vikram.travel@insure.co"),
                    ("cyber", "Neha Kapoor", "neha.cyber@insure.co"),
                ]
                for spec, name, email in canonical_adjusters:
                    uid = str(uuid.uuid4())
                    db.add(Adjuster(
                        id=uid,
                        name=name,
                        email=email,
                        specialization=spec,
                        claims_assigned=0,
                        is_active=True,
                    ))
                    # Seed matching user credentials
                    db.add(User(
                        id=uid,
                        full_name=name,
                        email=email,
                        password_hash=get_password_hash("AdjusterPassword123!"),
                        role="ADJUSTER",
                        status="active"
                    ))

                # Seed default claimant john@test.com
                db.add(User(
                    id="claimant_john",
                    full_name="John Doe",
                    email="john@test.com",
                    password_hash=get_password_hash("ClaimantPassword123!"),
                    role="CLAIMANT",
                    status="active"
                ))

                db.commit()
                logger.info("Database schema initialized and canonical records seeded.")
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Database schema check notice: %s", exc)


# ---------------------------------------------------------------------------
# Application Lifecycle
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle manager."""
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
# CORS Configuration
# ---------------------------------------------------------------------------
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
        "id": str(current_user.id),
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

# Adjuster routes — only ADJUSTER role allowed
app.include_router(
    adjuster_routes.router,
    dependencies=[Depends(require_role(["ADJUSTER"]))],
)

# Knowledge routes — ADJUSTER role required
app.include_router(
    knowledge_routes.router,
    dependencies=[Depends(require_role(["ADJUSTER"]))],
)

# Voice WebSocket router
app.include_router(voice_router)