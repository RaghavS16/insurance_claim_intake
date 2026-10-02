"""Shared security primitives used by HTTP and WebSocket entry points."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import jwt
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.database.models import RevokedToken, User
from src.utils.auth import is_token_revoked, verify_token

def assert_active_user(user: User) -> User:
    if str(user.status).lower() != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is not active.")
    return user

def authenticate_token(token: str, db: Session) -> User:
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    if is_token_revoked(token):
        raise HTTPException(status_code=401, detail="Token has been revoked.")
    payload = verify_token(token)
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid or expired token.")

    jti = payload.get("jti")
    if jti:
        row = db.query(RevokedToken).filter(RevokedToken.token_jti == jti).first()
        if row:
            raise HTTPException(status_code=401, detail="Token has been revoked.")

    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required.")
    assert_active_user(user)

    token_version = int(payload.get("sv", 1))
    current_version = int(getattr(user, "session_version", 1) or 1)
    if token_version != current_version:
        raise HTTPException(status_code=401, detail="Session is no longer valid.")
    return user

def token_payload(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, options={"verify_signature": False})
    except Exception:
        return None

def request_bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication required.")
    return authorization[7:].strip()
