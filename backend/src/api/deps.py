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
        # X-User-ID fallback is ONLY available in test environment
        if settings.ENVIRONMENT == "test":
            uid = request.headers.get("X-User-ID")
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required: missing bearer token.",
            )

    if not uid:
        if settings.ENVIRONMENT == "test" and not request.headers.get("X-Test-No-Fallback"):
            uid = "TEST_USER_ID"
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required.",
            )

    # Fetch user from DB and enforce current account/session state.
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
    if (
        settings.PRIVILEGED_PASSKEY_REQUIRED
        and user.role.upper() in {"ADMIN", "ADJUSTER"}
        and not request.url.path.startswith("/api/v1/auth/passkey/")
    ):
        amr = payload.get("amr", []) if (token and payload) else []
        if "webauthn" not in amr:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="A registered passkey is required for privileged access.",
            )
    return user

def get_current_user_id(current_user: User = Depends(get_current_user)) -> str:
    """Dependency helper to get the authenticated user ID string."""
    return current_user.id


def require_role(allowed_roles: List[str], *, require_phishing_resistant: bool = False):
    """Enforce role access and, for privileged roles, optional passkey authentication."""

    def dependency(
        request: Request = cast(Request, None),
        current_user: User = Depends(get_current_user),
    ):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Role '{current_user.role}' not permitted.",
            )
        privileged = current_user.role.upper() in {"ADMIN", "ADJUSTER"}
        auth_amr = set(getattr(request.state, "auth_amr", []) or []) if (request and hasattr(request, "state")) else set()
        if (
            (require_phishing_resistant or (privileged and settings.PRIVILEGED_PASSKEY_REQUIRED))
            and privileged
            and "webauthn" not in auth_amr
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Phishing-resistant passkey authentication is required for this privileged operation.",
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

    This consolidates the three near-identical ``_resolve_admin``,
    ``_resolve_adjuster``, and ``_resolve_user`` functions that were
    copy-pasted across admin_routes, adjuster_routes, claim_routes, and
    policy_routes.
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
    privileged = user.role.upper() in {"ADMIN", "ADJUSTER"}
    if (
        privileged
        and settings.PRIVILEGED_PASSKEY_REQUIRED
        and "webauthn" not in set(getattr(request.state, "auth_amr", []) or [])
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Phishing-resistant passkey authentication is required for this privileged operation.",
        )
    return user


def get_claim_or_404(db: Session, ticket_id: str) -> Claim:
    """Fetch a Claim by ticket_id and raise HTTP 404 if not found.

    Replaces the repeated pattern::

        claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found.")
    """
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found.")
    return claim


def get_adjuster_or_404(db: Session, adjuster_id: str) -> Adjuster:
    """Fetch an Adjuster by id and raise HTTP 404 if not found.

    Replaces the repeated pattern::

        adjuster = db.query(Adjuster).filter(Adjuster.id == adjuster_id).first()
        if not adjuster:
            raise HTTPException(status_code=404, detail="Adjuster not found.")
    """
    adjuster = db.query(Adjuster).filter(Adjuster.id == adjuster_id).first()
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
    except Exception:
        db.rollback()
        logger.exception(log_message or error_detail)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_detail,
        )
