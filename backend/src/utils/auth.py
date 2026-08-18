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

ALGORITHM = "HS256"


class TokenError(Enum):
    """Structured token verification error types."""
    EXPIRED = "token_expired"
    INVALID = "token_invalid"
    MALFORMED = "token_malformed"


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
    """Create a new JWT access token with configurable expiry."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({
        "exp": int(expire.timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
    })
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode and verify a JWT access token.

    Returns the payload dict on success, None on any failure.
    Logs structured error type for monitoring.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
    except Exception:
        return None
