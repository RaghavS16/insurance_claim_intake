"""WebAuthn/passkey ceremonies for phishing-resistant authentication."""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from src.config import settings
from src.database.hardening_models import WebAuthnChallenge, WebAuthnCredential
from src.database.models import User

try:
    from webauthn import (
        base64url_to_bytes,
        generate_authentication_options,
        generate_registration_options,
        options_to_json,
        verify_authentication_response,
        verify_registration_response,
    )
    from webauthn.helpers.structs import (
        PublicKeyCredentialDescriptor,
        UserVerificationRequirement,
        AuthenticatorSelectionCriteria,
        ResidentKeyRequirement,
    )
except Exception as exc:  # pragma: no cover
    base64url_to_bytes = None
    generate_authentication_options = None
    generate_registration_options = None
    options_to_json = None
    verify_authentication_response = None
    verify_registration_response = None
    PublicKeyCredentialDescriptor = None
    UserVerificationRequirement = None
    AuthenticatorSelectionCriteria = None
    ResidentKeyRequirement = None
    _WEBAUTHN_IMPORT_ERROR = exc
else:
    _WEBAUTHN_IMPORT_ERROR = None


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _challenge_bytes(challenge: str) -> bytes:
    if base64url_to_bytes is not None:
        return base64url_to_bytes(challenge)
    padding = "=" * (-len(challenge) % 4)
    return base64.urlsafe_b64decode(challenge + padding)


def _require_library() -> None:
    if _WEBAUTHN_IMPORT_ERROR is not None:
        raise RuntimeError("WebAuthn support is not installed.")


def _challenge_row(db: Session, *, user: User, purpose: str, challenge: bytes) -> WebAuthnChallenge:
    row = WebAuthnChallenge(
        tenant_id=str(user.tenant_id or ""),
        user_id=str(user.id),
        purpose=purpose,
        challenge=_b64(challenge),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=120),
        consumed=False,
    )
    db.add(row)
    db.flush()
    return row


def registration_options(db: Session, user: User) -> dict[str, Any]:
    _require_library()
    existing = db.query(WebAuthnCredential).filter(
        WebAuthnCredential.user_id == user.id,
        WebAuthnCredential.tenant_id == user.tenant_id,
    ).all()
    challenge = secrets.token_bytes(32)
    kwargs: dict[str, Any] = dict(
        rp_id=settings.PASSKEY_RP_ID,
        rp_name=settings.PASSKEY_RP_NAME,
        user_name=str(user.email),
        user_id=uuid.UUID(str(user.id)).bytes if _looks_like_uuid(str(user.id)) else hashlib.sha256(str(user.id).encode()).digest()[:32],
        challenge=challenge,
        timeout=120000,
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(item.credential_id))
            for item in existing
        ],
    )
    if AuthenticatorSelectionCriteria is not None and ResidentKeyRequirement is not None:
        kwargs["authenticator_selection"] = AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
        )
    options = generate_registration_options(**kwargs)
    row = _challenge_row(db, user=user, purpose="registration", challenge=challenge)
    db.commit()
    return {"challenge_id": str(row.id), "public_key": json.loads(options_to_json(options))}


def verify_registration(db: Session, user: User, challenge_id: str, credential: dict[str, Any]) -> WebAuthnCredential:
    _require_library()
    row = db.query(WebAuthnChallenge).filter(
        WebAuthnChallenge.id == challenge_id,
        WebAuthnChallenge.user_id == user.id,
        WebAuthnChallenge.tenant_id == user.tenant_id,
        WebAuthnChallenge.purpose == "registration",
        WebAuthnChallenge.consumed.is_(False),
    ).with_for_update().first()
    if not row or row.expires_at <= datetime.now(timezone.utc):
        raise ValueError("WebAuthn registration challenge is invalid or expired.")
    verification = verify_registration_response(
        credential=credential,
        expected_challenge=_challenge_bytes(row.challenge),
        expected_rp_id=settings.PASSKEY_RP_ID,
        expected_origin=settings.PASSKEY_ORIGIN,
        require_user_verification=settings.PASSKEY_REQUIRE_USER_VERIFICATION,
    )
    credential_id = _b64(verification.credential_id)
    if db.query(WebAuthnCredential).filter(WebAuthnCredential.credential_id == credential_id).first():
        raise ValueError("This passkey is already registered.")
    saved = WebAuthnCredential(
        tenant_id=str(user.tenant_id or ""),
        user_id=str(user.id),
        credential_id=credential_id,
        public_key=_b64(verification.credential_public_key),
        sign_count=0,
        device_type=str(getattr(verification, "credential_device_type", "") or ""),
        backed_up=bool(getattr(verification, "credential_backed_up", False)),
    )
    row.consumed = True
    db.add(saved)
    db.commit()
    return saved


def authentication_options(db: Session, user: User) -> dict[str, Any]:
    _require_library()
    credentials = db.query(WebAuthnCredential).filter(
        WebAuthnCredential.user_id == user.id,
        WebAuthnCredential.tenant_id == user.tenant_id,
    ).all()
    if not credentials:
        raise ValueError("No passkey is registered for this account.")
    challenge = secrets.token_bytes(32)
    options = generate_authentication_options(
        rp_id=settings.PASSKEY_RP_ID,
        challenge=challenge,
        timeout=120000,
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(item.credential_id))
            for item in credentials
        ],
        user_verification=(
            UserVerificationRequirement.REQUIRED
            if settings.PASSKEY_REQUIRE_USER_VERIFICATION
            else UserVerificationRequirement.PREFERRED
        ),
    )
    row = _challenge_row(db, user=user, purpose="authentication", challenge=challenge)
    db.commit()
    return {"challenge_id": str(row.id), "public_key": json.loads(options_to_json(options))}


def verify_authentication(db: Session, user: User, challenge_id: str, credential: dict[str, Any]) -> WebAuthnCredential:
    _require_library()
    row = db.query(WebAuthnChallenge).filter(
        WebAuthnChallenge.id == challenge_id,
        WebAuthnChallenge.user_id == user.id,
        WebAuthnChallenge.tenant_id == user.tenant_id,
        WebAuthnChallenge.purpose == "authentication",
        WebAuthnChallenge.consumed.is_(False),
    ).with_for_update().first()
    if not row or row.expires_at <= datetime.now(timezone.utc):
        raise ValueError("WebAuthn authentication challenge is invalid or expired.")
    credential_id = str(credential.get("id") or "").strip()
    saved = db.query(WebAuthnCredential).filter(
        WebAuthnCredential.credential_id == credential_id,
        WebAuthnCredential.user_id == user.id,
        WebAuthnCredential.tenant_id == user.tenant_id,
    ).with_for_update().first()
    if not saved:
        raise ValueError("WebAuthn credential is not registered.")
    verification = verify_authentication_response(
        credential=credential,
        expected_challenge=_challenge_bytes(row.challenge),
        expected_rp_id=settings.PASSKEY_RP_ID,
        expected_origin=settings.PASSKEY_ORIGIN,
        credential_public_key=_challenge_bytes(saved.public_key),
        credential_current_sign_count=int(saved.sign_count or 0),
        require_user_verification=settings.PASSKEY_REQUIRE_USER_VERIFICATION,
    )
    saved.sign_count = int(verification.new_sign_count)
    saved.last_used_at = datetime.now(timezone.utc)
    row.consumed = True
    db.commit()
    return saved


def _looks_like_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False
