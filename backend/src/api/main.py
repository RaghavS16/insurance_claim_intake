"""
FastAPI application for Insurance Claim Intake and Conversation Management.

Production-hardened entry point. This module acts as a slim orchestrator:
- Configures middleware, exception handlers, and lifecycle events
- Includes separated route modules for auth, claims, adjuster, and knowledge
- Provides centralized authentication dependencies
- Initializes database schema and tables on startup

All business logic has been extracted into dedicated route modules:
- auth_routes.py: Authentication (signup, login, logout)
- claim_routes.py: Claim intake, confirmation, documents
"""
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from src.config import settings
from src.database.session import get_db, engine, dispose_engine
from src.database.models import Base, User
from src.api.realtime_voice import router as voice_router
from src.utils.logger import app_logger
from src.utils.validators import validate_full_name, validate_phone
from src.utils.tracing import CorrelationIdMiddleware
from src.middleware import SecurityHeadersMiddleware, RequestSizeLimitMiddleware, RequestContextMiddleware
from src.services.observability import configure_otel

# Route modules
from src.api import auth_routes, auth_onboarding_routes, claim_routes, policy_routes, admin_routes, admin_workflow_routes, adjuster_routes, knowledge_routes, notification_routes

# Shared auth dependencies
from src.api.deps import get_current_user

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
# Database Initialization (Schema and Tables Only)
# ---------------------------------------------------------------------------
def _init_db_schema():
    """Initialize database schema and tables only; no demo seed records inserted."""
    try:
        if settings.ENVIRONMENT in ("production", "staging"):
            logger.info("Production/staging startup: schema creation is migration-managed; run Alembic migrations separately.")
            return
        Base.metadata.create_all(bind=engine)

        # Ensure Alembic version tracking stays synchronized with create_all in development
        try:
            import os
            from alembic.config import Config
            from alembic import command
            alembic_cfg_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "alembic.ini")
            if os.path.exists(alembic_cfg_path):
                alembic_cfg = Config(alembic_cfg_path)
                command.stamp(alembic_cfg, "head")
        except Exception as stamp_err:
            logger.debug("Alembic sync notice: %s", stamp_err)

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

            if "user_notification_states" not in tables:
                logger.info("Database auto-migration: creating user_notification_states table")
                Base.metadata.create_all(bind=conn, tables=[Base.metadata.tables["user_notification_states"]], checkfirst=True)
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

        logger.info("Database schema and tables initialized.")
    except Exception as exc:
        logger.warning("Database schema check notice: %s", exc)


# ---------------------------------------------------------------------------
# Application Lifecycle
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle manager."""
    settings.validate_startup()
    configure_otel()
    if settings.ENVIRONMENT in ("production", "staging"):
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        if settings.REQUIRE_MIGRATIONS_IN_PRODUCTION:
            if getattr(settings, "VERIFY_MIGRATIONS_ON_STARTUP", False) or os.getenv("VERIFY_MIGRATIONS_ON_STARTUP", "false").lower() == "true":
                try:
                    from alembic.config import Config
                    from alembic.script import ScriptDirectory
                    cfg = Config(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "alembic.ini"))
                    script = ScriptDirectory.from_config(cfg)
                    heads = set(script.get_heads())
                    with engine.connect() as conn:
                        current = {str(row[0]) for row in conn.execute(text("SELECT version_num FROM alembic_version"))}
                    if current != heads:
                        raise RuntimeError(f"Database migration state is not at head: current={sorted(current)} expected={sorted(heads)}")
                except Exception as exc:
                    logger.exception("Production migration verification failed: %s", type(exc).__name__)
                    raise
            else:
                logger.info("VERIFY_MIGRATIONS_ON_STARTUP is false; skipping synchronous Alembic check on startup (<1.5s boot).")
        if settings.REQUIRE_REDIS_IN_PRODUCTION and not settings.REDIS_URL:
            raise RuntimeError("REDIS_URL is required in production/staging.")
    else:
        _init_db_schema()

    outbox_task = None
    if getattr(settings, "RUN_EMBEDDED_OUTBOX_WORKER", True):
        try:
            import asyncio
            from src.services.outbox_worker import run_worker
            from src.services.outbox_handlers import HANDLERS
            poll_interval = float(getattr(settings, "OUTBOX_POLL_INTERVAL_SECONDS", 15.0))
            outbox_task = asyncio.create_task(run_worker(HANDLERS, poll_seconds=poll_interval))
            logger.info("Embedded outbox worker started (poll_seconds=%.1f).", poll_interval)
        except Exception as exc:
            logger.warning("Could not start embedded outbox worker: %s", exc)

    yield

    if outbox_task:
        outbox_task.cancel()
        try:
            await outbox_task
        except (asyncio.CancelledError, Exception):
            pass
        logger.info("Embedded outbox worker stopped.")

    # Graceful shutdown: dispose connection pool
    dispose_engine()
    logger.info("Application shutdown complete.")


_enable_docs = settings.ENABLE_API_DOCS or (settings.ENVIRONMENT not in ("production", "staging"))

app = FastAPI(
    title="IntelliClaim API",
    description="Voice-driven agentic AI system for insurance intake and adjudication",
    version="2.0.0",
    docs_url="/docs" if _enable_docs else None,
    redoc_url="/redoc" if _enable_docs else None,
    openapi_url="/openapi.json" if _enable_docs else None,
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Tracing & CORS Middleware
# ---------------------------------------------------------------------------
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Accept", "If-None-Match", "X-Correlation-ID"],
)


# ---------------------------------------------------------------------------
# Exception Handlers
# ---------------------------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return API-safe JSON for request validation errors with field details."""
    details = []
    try:
        for err in exc.errors():
            loc = err.get("loc", ())
            field_parts = [str(l) for l in loc if l != "body"]
            field_name = ".".join(field_parts) if field_parts else "body"
            details.append({"field": field_name, "msg": str(err.get("msg", "Invalid value"))})
    except Exception:
        pass
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid request payload.",
                "details": details,
            },
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions and return safe 500 error (no stack trace to client)."""
    logger.exception("Unhandled server exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": {"code": "INTERNAL_ERROR", "message": "An internal server error occurred. Please try again later."}, "request_id": getattr(request.state, "request_id", None)},
    )


# ---------------------------------------------------------------------------
# Health & Root
# ---------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def root():
    if settings.ENVIRONMENT in ("production", "staging"):
        return {"service": "insurance-claim-intake", "status": "ok"}
    return RedirectResponse(url="/docs")


@app.get("/health")
def health_check():
    """Liveness probe: does not require downstream services."""
    return {"status": "ok"}

@app.get("/ready")
def readiness_check():
    """Readiness probe that verifies the database, S3 head_bucket, Redis, and ClamAV."""
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        if settings.ENVIRONMENT in ("production", "staging"):
            if not settings.S3_BUCKET:
                raise RuntimeError("S3_BUCKET is not configured")
            from src.storage.s3 import _client
            _client().head_bucket(Bucket=settings.S3_BUCKET)
            if settings.REQUIRE_REDIS_IN_PRODUCTION or settings.REDIS_URL:
                if not settings.REDIS_URL:
                    raise RuntimeError("REDIS_URL is not configured")
                import redis
                redis.Redis.from_url(settings.REDIS_URL, socket_timeout=1.5, socket_connect_timeout=1.5).ping()
            if settings.REQUIRE_MALWARE_SCAN:
                from src.utils.clamav import ping_clamav
                ping_clamav()
        return {"status": "ready", "database": "ok", "storage": "configured", "redis": "ok" if settings.REDIS_URL else "not_required"}
    except Exception as exc:
        logger.exception("Readiness check failed: %s", type(exc).__name__)
        return JSONResponse(status_code=503, content={"status": "not_ready", "reason": "dependency_unavailable"})


# ---------------------------------------------------------------------------
# Include Route Modules with Dependency Injection
# ---------------------------------------------------------------------------
# Override the `current_user` dependency placeholder in each route module
# by configuring the router's dependency overrides at inclusion time.

# Auth routes (signup, login, logout)
app.include_router(auth_routes.router)
app.include_router(auth_onboarding_routes.router)

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


class UpdateMeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: Optional[str] = Field(default=None, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=20)

    @field_validator("full_name")
    @classmethod
    def check_full_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return validate_full_name(v)

    @field_validator("phone")
    @classmethod
    def check_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return validate_phone(v)


@app.patch("/api/v1/auth/me", tags=["Authentication"])
def update_me(
    payload: UpdateMeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the currently authenticated user's profile details."""
    if payload.full_name is not None:
        current_user.full_name = payload.full_name
    if payload.phone is not None:
        current_user.phone = payload.phone
    db.commit()
    db.refresh(current_user)
    return {
        "id": current_user.id,
        "full_name": current_user.full_name,
        "email": current_user.email,
        "phone": current_user.phone,
        "role": current_user.role,
        "status": current_user.status,
    }


# Role-based notification routes
app.include_router(notification_routes.router)


# Claim routes — inject get_current_user dependency
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
    admin_workflow_routes.router,
    dependencies=[Depends(get_current_user)],
)
app.include_router(
    admin_routes.router,
    dependencies=[Depends(get_current_user)],
)

app.include_router(adjuster_routes.router)
app.include_router(knowledge_routes.router)

# Voice WebSocket router
app.include_router(voice_router)