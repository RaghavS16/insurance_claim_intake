"""
Authentication utilities for password hashing and JWT token management.

Production hardening:
- Configurable token expiry from settings
- Structured error types for token verification failures
- Password complexity validation delegated to validators module
"""
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, Optional
import bcrypt
import jwt

from src.config import settings

import threading
import time
import uuid

ALGORITHM = "HS256"

# In-memory blacklist with expiration tracking
_revoked_tokens_lock = threading.Lock()
_revoked_tokens: Dict[str, float] = {}  # jti or token_hash -> expiry_timestamp


class TokenError(Enum):
    """Structured token verification error types."""
    EXPIRED = "token_expired"
    INVALID = "token_invalid"
    MALFORMED = "token_malformed"
    REVOKED = "token_revoked"


def get_password_hash(password: str) -> str:
    """Hash a plain text password using bcrypt."""
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain text password against a bcrypt hash."""
    try:
        password_bytes = plain_password.encode("utf-8")
        hashed_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a new JWT access token with unique jti and configurable expiry."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({
        "jti": str(uuid.uuid4()),
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
    })
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def revoke_token(token: str) -> bool:
    """
    Revoke a JWT token by adding its jti (or token) to the blacklist.
    """
    try:
        # Decode without verification in case it is near expiration
        unverified = jwt.decode(token, options={"verify_signature": False})
        jti = unverified.get("jti") or token
        exp = unverified.get("exp", time.time() + 3600)
    except Exception:
        jti = token
        exp = time.time() + 3600

    now = time.time()
    with _revoked_tokens_lock:
        # Clean expired tokens
        expired_keys = [k for k, v in _revoked_tokens.items() if v <= now]
        for k in expired_keys:
            _revoked_tokens.pop(k, None)

        _revoked_tokens[jti] = exp
    return True


def is_token_revoked(token: str) -> bool:
    """Check if token or its jti has been blacklisted."""
    try:
        unverified = jwt.decode(token, options={"verify_signature": False})
        jti = unverified.get("jti")
    except Exception:
        jti = None

    now = time.time()
    with _revoked_tokens_lock:
        if jti and jti in _revoked_tokens:
            if _revoked_tokens[jti] > now:
                return True
        if token in _revoked_tokens:
            if _revoked_tokens[token] > now:
                return True
    return False


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode and verify a JWT access token.
    Ensures signature is valid, token is not expired, and not in the blacklist.
    """
    if is_token_revoked(token):
        return None

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        jti = payload.get("jti")
        if jti and is_token_revoked(token):
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
    except Exception:
        return None

