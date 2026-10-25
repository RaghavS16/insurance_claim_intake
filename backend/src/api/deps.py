"""
Shared FastAPI dependency functions for authentication and authorization.

Centralizes get_current_user, get_current_user_id, require_role,
resolve_bearer_user, get_claim_or_404, get_adjuster_or_404, and
db_commit_or_500 so that other route modules (admin_routes, policy_routes,
claim_routes, adjuster_routes) can import from here instead of each
defining their own boilerplate, eliminating circular import risks.
"""
from typing import Any, List, Optional, cast

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from src.config import settings
from src.database.session import get_db
from src.database.models import Adjuster, Claim, RevokedToken, User
from src.database.hardening_models import ClaimEvidence
from src.utils.auth import get_password_hash, is_token_revoked, verify_token
from src.utils.logger import app_logger

logger = app_logger
security_scheme = HTTPBearer(auto_error=False)


def _is_token_revoked_db(token: str, db: Session) -> bool:
    """
    Check DB-persisted revocation table for revoked JWTs.
    This supplements the in-memory cache and survives server restarts.
    """
    try:
        from datetime import datetime, timezone
        import jwt as _jwt

        # Extract jti without full verification
        unverified = _jwt.decode(token, options={"verify_signature": False})
        jti = unverified.get("jti")
        if jti:
            revoked = db.query(RevokedToken).filter(RevokedToken.token_jti == jti).first()
            if revoked:
                # Check if revocation record is still within token's expiry window
                now = datetime.now(timezone.utc)
                expires_at = revoked.expires_at
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if expires_at > now:
                    return True
    except Exception as exc:
        # Authentication must fail closed if revocation state cannot be checked.
        logger.exception("Token revocation check failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Authentication service temporarily unavailable.") from exc
    return False


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Extract and verify JWT token to fetch the currently authenticated user.

    Checks both in-memory and DB-persisted token revocation to handle
    server restarts correctly.

    SECURITY: The X-User-ID header fallback is ONLY available in test environments.
    Production/staging environments strictly require a valid JWT bearer token.
    """
    token = None
    payload: dict[str, Any] | None = None
    if credentials:
        token = credentials.credentials

    uid = None
    if token:
        # Check revocation: first in-memory (fast), then DB (survives restarts)
        if is_token_revoked(token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated: Token has been revoked.",
            )
        if _is_token_revoked_db(token, db):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated: Token has been revoked.",
            )
        payload = verify_token(token)
        if payload:
            uid = payload.get("sub")
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated: Invalid or expired token.",
            )
    else:
        # X-User-ID fallback is ONLY available in test environment when explicit insecure test auth is enabled
        if settings.ENVIRONMENT == "test" and getattr(settings, "ALLOW_INSECURE_TEST_AUTH", False) is True:
            uid = request.headers.get("X-User-ID")
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required: missing bearer token.",
            )

    if not uid:
        if settings.ENVIRONMENT == "test" and getattr(settings, "ALLOW_INSECURE_TEST_AUTH", False) is True and not request.headers.get("X-Test-No-Fallback"):
            uid = "TEST_USER_ID"
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required.",
            )

    # Fetch user from DB and enforce current account/session state.
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        if settings.ENVIRONMENT == "test" and getattr(settings, "ALLOW_INSECURE_TEST_AUTH", False) is True:
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
                    status="active",
                )
                db.add(user)
                db.commit()
                db.refresh(user)
            if not getattr(user, "tenant_id", None):
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Tenant context is unavailable.")
            return user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: User not found.",
        )
    if not getattr(user, "tenant_id", None):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant membership is required.")
    if user.status.lower() != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is not active.")
    token_version = int(payload.get("sv", 1)) if (token and payload) else 1
    if token and token_version != int(getattr(user, "session_version", 1) or 1):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is no longer valid.")
    token_tenant = str(payload.get("tenant_id") or "") if (token and payload) else (user.tenant_id or "")
    if token and token_tenant != (user.tenant_id or ""):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session tenant context is no longer valid.")
    request.state.authenticated_user_id = user.id
    request.state.authenticated_tenant_id = user.tenant_id or ""
    request.state.auth_amr = list(payload.get("amr") or []) if (token and payload) else []
    if settings.REQUIRE_EMAIL_VERIFICATION and not getattr(user, "email_verified_at", None):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email verification is required.")
    return user

def get_current_user_id(current_user: User = Depends(get_current_user)) -> str:
    """Dependency helper to get the authenticated user ID string."""
    return current_user.id


def require_role(allowed_roles: List[str]):
    """Enforce role access for authenticated users."""

    def dependency(
        request: Request = cast(Request, None),
        current_user: User = Depends(get_current_user),
    ):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Role '{current_user.role}' not permitted.",
            )
        return current_user

    return dependency


# ---------------------------------------------------------------------------
# Shared request helpers
# ---------------------------------------------------------------------------

def resolve_bearer_user(
    request: Request,
    db: Session,
    allowed_roles: List[str],
) -> User:
    """Extract the Bearer token from the Authorization header, authenticate the
    caller via ``get_current_user``, and assert the user's role is in
    ``allowed_roles``.
    """
    auth_header = request.headers.get("authorization", "")
    credentials: Optional[HTTPAuthorizationCredentials] = None
    if auth_header.lower().startswith("bearer "):
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=auth_header[7:]
        )
    user = get_current_user(request=request, credentials=credentials, db=db)
    if user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: Role '{user.role}' is not permitted.",
        )
    return user


def get_claim_or_404(db: Session, ticket_id: str, tenant_id: Optional[str] = None) -> Claim:
    """Fetch a Claim by ticket_id and optional tenant_id, raising HTTP 404 if not found."""
    query = db.query(Claim).filter(Claim.ticket_id == ticket_id)
    if tenant_id:
        query = query.filter(Claim.tenant_id == tenant_id)
    claim = query.first()
    if not claim:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found.")
    return claim


def get_adjuster_or_404(db: Session, adjuster_id: str, tenant_id: Optional[str] = None) -> Adjuster:
    """Fetch an Adjuster by id and optional tenant_id, raising HTTP 404 if not found."""
    query = db.query(Adjuster).filter(Adjuster.id == adjuster_id)
    if tenant_id:
        query = query.filter(Adjuster.tenant_id == tenant_id)
    adjuster = query.first()
    if not adjuster:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Adjuster not found.")
    return adjuster


def db_commit_or_500(
    db: Session,
    logger,  # type: ignore[type-arg]
    error_detail: str,
    log_message: str = "",
) -> None:
    """Commit the current DB transaction, rolling back and raising HTTP 500 on failure.

    Replaces the repeated pattern::

        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("...")
            raise HTTPException(status_code=500, detail="...")
    """
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception(log_message or error_detail)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{error_detail} Exception: {str(e)}",
        )


def serialize_evidence_request(row: Any, db: Session) -> dict[str, Any]:
    """Serialize a ClaimEvidenceRequest row and its latest associated evidence."""
    evidence = (
        db.query(ClaimEvidence)
        .filter(ClaimEvidence.request_id == row.id, ClaimEvidence.tenant_id == row.tenant_id)
        .order_by(ClaimEvidence.created_at.desc())
        .first()
    )
    return {
        "id": str(row.id),
        "claim_id": str(row.claim_id),
        "adjuster_id": str(row.adjuster_id),
        "request_text": row.request_text,
        "notes": row.request_text,
        "status": row.status,
        "response_note": row.response_note,
        "requested_at": row.requested_at.isoformat() if row.requested_at else None,
        "responded_at": row.responded_at.isoformat() if row.responded_at else None,
        "evidence_id": str(evidence.id) if evidence else None,
        "evidence_name": evidence.original_filename if evidence else None,
        "response_evidence": {
            "id": str(evidence.id),
            "name": evidence.original_filename,
            "verification_status": evidence.verification_status,
        } if evidence else None,
    }
