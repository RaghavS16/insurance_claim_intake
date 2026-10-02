"""TOTP MFA primitives with encrypted secret storage and hashed recovery codes."""
from __future__ import annotations
import base64
import hashlib
import hmac
import secrets
from cryptography.fernet import Fernet
import pyotp
from src.config import settings

def _fernet() -> Fernet:
    raw = settings.MFA_ENCRYPTION_KEY
    if not raw:
        if settings.ENVIRONMENT in ("production", "staging"):
            raise RuntimeError("MFA_ENCRYPTION_KEY is required in production/staging.")
        raw = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest()).decode()
    return Fernet(raw.encode())

def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()

def decrypt_secret(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()

def new_totp_secret() -> str:
    return pyotp.random_base32()

def totp_code(secret: str) -> str:
    return pyotp.TOTP(secret).now()

def verify_totp(secret: str, code: str) -> bool:
    return bool(pyotp.TOTP(secret).verify(code.strip(), valid_window=1))

def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=settings.MFA_ISSUER)

def new_recovery_codes(count: int | None = None) -> list[str]:
    count = count or settings.MFA_RECOVERY_CODE_COUNT
    return [secrets.token_hex(6).upper() for _ in range(count)]

def hash_recovery_code(code: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), code.strip().upper().encode(), hashlib.sha256).hexdigest()

def verify_recovery_hash(code: str, digest: str) -> bool:
    return hmac.compare_digest(hash_recovery_code(code), digest)
