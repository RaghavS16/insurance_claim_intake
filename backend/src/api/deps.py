"""
Shared FastAPI dependency functions for authentication and authorization.

Centralizes get_current_user, get_current_user_id, and require_role so that
other route modules (admin_routes, policy_routes, claim_routes) can import
from here instead of from main.py, eliminating circular import risks.
"""
from typing import List, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from src.config import settings
from src.database.session import get_db
from src.database.models import RevokedToken, User
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
    except Exception:
        pass
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
                    status="active",
                )
                db.add(user)
                db.commit()
                db.refresh(user)
            return user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: User not found.",
        )
    return user


def get_current_user_id(current_user: User = Depends(get_current_user)) -> str:
    """Dependency helper to get the authenticated user ID string."""
    return current_user.id


def require_role(allowed_roles: List[str]):
    """Enforce that the authenticated user possesses an allowed role."""

    def dependency(current_user: User = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Role '{current_user.role}' not permitted.",
            )
        return current_user

    return dependency
