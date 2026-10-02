"""
Authentication API routes.

Handles user signup, login, logout, and profile retrieval.
Extracted from the monolithic main.py for clean architectural separation.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
import hashlib
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.config import settings
from src.database.session import get_db
from src.database.models import User, PasswordResetOTP, RevokedToken
from src.database.hardening_models import MFAChallenge, MFARecoveryCode, Tenant, TenantMembership, RefreshToken
from src.utils.mfa import encrypt_secret, decrypt_secret, new_totp_secret, verify_totp, provisioning_uri, new_recovery_codes, hash_recovery_code, verify_recovery_hash
from src.utils.auth import get_password_hash, verify_password, create_access_token, verify_token, revoke_token
from src.utils.validators import validate_email, validate_password_strength, validate_full_name, validate_phone
from src.utils.email_otp import generate_otp, hash_otp, otp_expiry, send_otp_email
from src.utils.rate_limiter import enforce_rate_limit
from src.utils.logger import app_logger

logger = app_logger
router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------
class SignUpRequest(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=3, max_length=254)
    phone: str = Field(..., min_length=5, max_length=20, description="Mandatory phone number")
    password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=1, max_length=128)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)


class VerifyOtpRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    otp: str = Field(..., min_length=4, max_length=8)


class ResetPasswordRequest(BaseModel):
    reset_token: str = Field(..., min_length=10)
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)


# ---------------------------------------------------------------------------
# Refresh/MFA helpers

def _refresh_hash(raw: str) -> str:
    return hashlib.sha256(f"{settings.SECRET_KEY}:{raw}".encode("utf-8")).hexdigest()


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="refresh_token",
        value=token,
        httponly=True,
        secure=settings.ENVIRONMENT in {"production", "staging"},
        samesite=settings.REFRESH_COOKIE_SAMESITE,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/v1/auth",
    )


def _issue_refresh_token(db: Session, user: User, request: Request, family_id: str | None = None) -> str:
    raw = secrets.token_urlsafe(48)
    db.add(RefreshToken(
        tenant_id=str(user.tenant_id),
        user_id=str(user.id),
        token_hash=_refresh_hash(raw),
        family_id=family_id or str(uuid.uuid4()),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        user_agent=(request.headers.get("user-agent") or "")[:500] or None,
        ip_address=(request.client.host if request.client else None),
    ))
    return raw

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/signup")
def signup(payload: SignUpRequest, request: Request, db: Session = Depends(get_db)):
    """Register a new claimant account with validated input."""
    enforce_rate_limit(request, action="signup", max_requests=10, window_seconds=60)
    # Validate and sanitize inputs
    try:
        clean_name = validate_full_name(payload.full_name)
        clean_email = validate_email(payload.email)
        validate_password_strength(payload.password)
        clean_phone = validate_phone(payload.phone)
        if not clean_phone:
            raise ValueError("Phone number is required.")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passwords do not match.")

    existing_user = db.query(User).filter(User.email == clean_email).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered.")

    hashed_pwd = get_password_hash(payload.password)
    tenant = Tenant(name=f"{clean_name}'s Workspace", status="active")
    db.add(tenant)
    db.flush()
    new_user = User(
        full_name=clean_name,
        email=clean_email,
        phone=clean_phone,
        password_hash=hashed_pwd,
        role="CLAIMANT",
        status="active",
        tenant_id=tenant.id,
    )
    db.add(new_user)
    db.flush()
    db.add(TenantMembership(tenant_id=str(tenant.id), user_id=str(new_user.id), role="CLAIMANT", status="active"))

    try:
        db.commit()
        db.refresh(new_user)
    except Exception:
        db.rollback()
        logger.exception("Failed to create user account")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Account creation failed. Please try again.",
        )

    if settings.REQUIRE_EMAIL_VERIFICATION:
        verification_code = generate_otp()
        db.add(PasswordResetOTP(tenant_id=tenant.id, user_id=new_user.id, otp_hash=hash_otp(verification_code), purpose="email_verification", expires_at=otp_expiry(), attempts=0, verified=False, consumed=False))
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise HTTPException(status_code=500, detail="Account verification setup failed.")
        send_otp_email(new_user.email, verification_code, full_name=new_user.full_name, purpose="email_verification")
    return {
        "id": str(new_user.id),
        "full_name": new_user.full_name,
        "email": new_user.email,
        "phone": new_user.phone,
        "role": new_user.role,
        "status": new_user.status,
    }


@router.post("/login")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """Authenticate a user and return a JWT access token."""
    enforce_rate_limit(request, action="login", max_requests=10, window_seconds=60)
    try:
        clean_email = validate_email(payload.email)
    except ValueError:
        # Don't reveal whether the email format was the issue
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    user = db.query(User).filter(User.email == clean_email).first()
    if not user or not verify_password(payload.password, str(user.password_hash)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled. Please contact support.",
        )

    user.last_login_at = datetime.now(timezone.utc)
    user.session_version = int(getattr(user, "session_version", 1) or 1)
    db.commit()
    if settings.REQUIRE_EMAIL_VERIFICATION and not user.email_verified_at:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Please verify your email before signing in.")
    if bool(getattr(user, "mfa_enabled", False) or getattr(user, "mfa_required", False)):
        raw_challenge = __import__("secrets").token_urlsafe(32)
        challenge = MFAChallenge(tenant_id=str(user.tenant_id), user_id=str(user.id), challenge_token_hash=__import__("hashlib").sha256(raw_challenge.encode()).hexdigest(), expires_at=datetime.now(timezone.utc) + timedelta(seconds=settings.MFA_CHALLENGE_EXPIRE_SECONDS))
        db.add(challenge)
        db.commit()
        return {"mfa_required": True, "challenge_token": raw_challenge, "expires_in": settings.MFA_CHALLENGE_EXPIRE_SECONDS}
    access_token = create_access_token(data={"sub": str(user.id), "role": user.role, "sv": user.session_version, "mfa": False})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role,
        },
    }



@router.post("/verify-email")
def verify_email(payload: VerifyOtpRequest, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(request, action="verify_email", max_requests=10, window_seconds=60)
    try:
        clean_email = validate_email(payload.email)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid email or verification code.")
    user = db.query(User).filter(User.email == clean_email).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid email or verification code.")
    record = (
        db.query(PasswordResetOTP)
        .filter(PasswordResetOTP.user_id == user.id, PasswordResetOTP.purpose == "email_verification", PasswordResetOTP.consumed == False)
        .order_by(PasswordResetOTP.created_at.desc())
        .with_for_update()
        .first()
    )
    if not record:
        raise HTTPException(status_code=400, detail="Invalid or expired verification code.")
    now = datetime.now(timezone.utc)
    expires = record.expires_at.replace(tzinfo=timezone.utc) if record.expires_at.tzinfo is None else record.expires_at
    if now > expires or (record.attempts or 0) >= settings.OTP_MAX_ATTEMPTS:
        raise HTTPException(status_code=400, detail="Invalid or expired verification code.")
    if hash_otp(payload.otp.strip()) != record.otp_hash:
        record.attempts = (record.attempts or 0) + 1
        db.commit()
        raise HTTPException(status_code=400, detail="Invalid or expired verification code.")
    record.verified = True
    record.consumed = True
    user.email_verified_at = now
    db.commit()
    return {"message": "Email verified successfully. You can now sign in."}



# ---------------------------------------------------------------------------
# Forgot Password: Step 1 — Request OTP
# ---------------------------------------------------------------------------
@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    """
    Issue an email OTP for password reset. Always returns a generic success
    message regardless of whether the email exists, to avoid account enumeration.
    """
    enforce_rate_limit(request, action="forgot_password", max_requests=10, window_seconds=60)
    try:
        clean_email = validate_email(payload.email)
    except ValueError:
        # Same generic response even on malformed email — don't leak validation detail here
        return {"message": "If an account with that email exists, a reset code has been sent."}

    generic_response = {"message": "If an account with that email exists, a reset code has been sent."}

    user = db.query(User).filter(User.email == clean_email).first()
    if not user or user.status != "active":
        return generic_response

    # Rate-limit resends in production/staging environments
    if settings.ENVIRONMENT not in ("development", "test"):
        recent = (
            db.query(PasswordResetOTP)
            .filter(PasswordResetOTP.user_id == user.id, PasswordResetOTP.consumed == False)  # noqa: E712
            .order_by(PasswordResetOTP.created_at.desc())
            .first()
        )
        now = datetime.now(timezone.utc)
        if recent and recent.created_at:
            recent_created = recent.created_at
            if recent_created.tzinfo is None:
                recent_created = recent_created.replace(tzinfo=timezone.utc)
            elapsed = (now - recent_created).total_seconds()
            if elapsed < settings.OTP_RESEND_COOLDOWN_SECONDS:
                return generic_response  # silently rate-limited in production

    otp = generate_otp()
    record = PasswordResetOTP(
        tenant_id=user.tenant_id,
        user_id=user.id,
        otp_hash=hash_otp(otp),
        expires_at=otp_expiry(),
        attempts=0,
        verified=False,
        consumed=False,
    )
    db.add(record)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to persist password reset OTP for user %s", user.id)
        return generic_response

    send_otp_email(user.email, otp, full_name=user.full_name)
    return generic_response


# ---------------------------------------------------------------------------
# Forgot Password: Step 2 — Verify OTP, issue short-lived reset token
# ---------------------------------------------------------------------------
@router.post("/verify-otp")
def verify_otp(payload: VerifyOtpRequest, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(request, action="verify_otp", max_requests=10, window_seconds=60)
    try:
        clean_email = validate_email(payload.email)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email format.")

    generic_invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired code. Please request a new one.",
    )

    user = db.query(User).filter(User.email == clean_email).first()
    if not user:
        raise generic_invalid

    record = (
        db.query(PasswordResetOTP)
        .filter(PasswordResetOTP.user_id == user.id, PasswordResetOTP.consumed == False)  # noqa: E712
        .order_by(PasswordResetOTP.created_at.desc())
        .with_for_update()
        .first()
    )
    if not record:
        raise generic_invalid

    now = datetime.now(timezone.utc)
    expires_at = record.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at and now > expires_at:
        raise generic_invalid

    if (record.attempts or 0) >= settings.OTP_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many incorrect attempts. Please request a new code.",
            headers={"Retry-After": "300"},  # Suggest retry after 5 minutes
        )

    if hash_otp(payload.otp.strip()) != record.otp_hash:
        record.attempts = (record.attempts or 0) + 1  # type: ignore[assignment]
        db.commit()
        raise generic_invalid

    record.verified = True  # type: ignore[assignment]
    db.commit()

    reset_token = create_access_token(
        data={"sub": str(user.id), "purpose": "password_reset", "otp_id": str(record.id)},
        expires_delta=timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
    )
    return {"reset_token": reset_token, "message": "Code verified. Use this token to set a new password."}


# ---------------------------------------------------------------------------
# Forgot Password: Step 3 — Reset password using verified token
# ---------------------------------------------------------------------------
@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(request, action="reset_password", max_requests=10, window_seconds=60)
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passwords do not match.")

    try:
        validate_password_strength(payload.new_password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    token_payload = verify_token(payload.reset_token)
    if not token_payload or token_payload.get("purpose") != "password_reset":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired reset token. Please restart the password reset process.",
        )

    user_id = token_payload.get("sub")
    otp_id = token_payload.get("otp_id")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid reset token.")

    record = db.query(PasswordResetOTP).filter(PasswordResetOTP.id == otp_id, PasswordResetOTP.tenant_id == user.tenant_id).first()
    if not record or not record.verified or record.consumed:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This reset code has already been used or is no longer valid. Please restart the process.",
        )

    user.password_hash = get_password_hash(payload.new_password)  # type: ignore[assignment]\n    user.session_version = int(getattr(user, "session_version", 1) or 1) + 1
    record.consumed = True  # type: ignore[assignment]
    # Revoke the reset token so it cannot be used again
    revoke_token(payload.reset_token)

    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to reset password for user %s", user_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Password reset failed. Please try again.")

    return {"message": "Password has been reset successfully. You can now log in with your new password."}


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    """
    Logout endpoint. Immediately revokes the JWT access token server-side.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        try:
            import jwt as _jwt
            payload = _jwt.decode(token, options={"verify_signature": False})
            revoke_token(token)
            jti = payload.get("jti") or token
            exp_ts = payload.get("exp")
            exp_dt = datetime.fromtimestamp(exp_ts, tz=timezone.utc) if exp_ts else datetime.now(timezone.utc) + timedelta(hours=1)
            db.add(RevokedToken(token_jti=jti, user_id=payload.get("sub"), expires_at=exp_dt))
            db.commit()
        except Exception:
            db.rollback()

    return {"message": "Logged out successfully. Token has been revoked."}


@router.post("/refresh")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    """Rotate the current HTTP-only refresh token and issue a short-lived access JWT."""
    enforce_rate_limit(request, action="refresh", max_requests=30, window_seconds=60)
    raw = request.cookies.get("refresh_token")
    if not raw:
        raise HTTPException(status_code=401, detail="Refresh authentication required.")
    now = datetime.now(timezone.utc)
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == _refresh_hash(raw)).with_for_update().first()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid refresh authentication.")
    if row.revoked_at is not None:
        family = db.query(RefreshToken).filter(
            RefreshToken.family_id == row.family_id,
            RefreshToken.revoked_at.is_(None),
        ).all()
        for item in family:
            item.revoked_at = now
        user = db.query(User).filter(User.id == row.user_id).first()
        if user:
            user.session_version = int(user.session_version or 1) + 1
        db.commit()
        raise HTTPException(status_code=401, detail="Refresh token replay detected. Please sign in again.")
    expires = row.expires_at.replace(tzinfo=timezone.utc) if row.expires_at.tzinfo is None else row.expires_at
    if expires <= now:
        row.revoked_at = now
        db.commit()
        raise HTTPException(status_code=401, detail="Refresh authentication expired.")
    user = db.query(User).filter(User.id == row.user_id, User.tenant_id == row.tenant_id).first()
    if not user or user.status != "active":
        raise HTTPException(status_code=401, detail="Refresh authentication invalid.")
    raw_new = _issue_refresh_token(db, user, request, row.family_id)
    new_row = db.query(RefreshToken).filter(RefreshToken.token_hash == _refresh_hash(raw_new)).first()
    row.revoked_at = now
    row.replaced_by_id = new_row.id if new_row else None
    row.last_used_at = now
    access = create_access_token(data={"sub": str(user.id), "role": user.role, "sv": user.session_version, "mfa": True})
    db.commit()
    _set_refresh_cookie(response, raw_new)
    return {"access_token": access, "token_type": "bearer", "user": {"id": str(user.id), "full_name": user.full_name, "email": user.email, "role": user.role}}


@router.post("/mfa/setup")
def mfa_setup(request: Request, current_user: User = Depends(__import__("src.api.deps", fromlist=["get_current_user"]).get_current_user), db: Session = Depends(get_db)):
    """Start TOTP enrollment; secret is stored encrypted until verified."""
    enforce_rate_limit(request, action="mfa_setup", max_requests=5, window_seconds=300)
    if current_user.mfa_enabled:
        raise HTTPException(status_code=409, detail="MFA is already enabled.")
    secret = new_totp_secret()
    current_user.mfa_secret_encrypted = encrypt_secret(secret)
    db.commit()
    return {"provisioning_uri": provisioning_uri(secret, current_user.email), "manual_key": secret, "issuer": settings.MFA_ISSUER}


@router.post("/mfa/setup/verify")
def mfa_setup_verify(payload: MFASetupVerifyRequest, request: Request, current_user: User = Depends(__import__("src.api.deps", fromlist=["get_current_user"]).get_current_user), db: Session = Depends(get_db)):
    enforce_rate_limit(request, action="mfa_setup_verify", max_requests=settings.MFA_MAX_ATTEMPTS, window_seconds=300)
    if not current_user.mfa_secret_encrypted:
        raise HTTPException(status_code=409, detail="Start MFA setup first.")
    if not verify_totp(decrypt_secret(current_user.mfa_secret_encrypted), payload.code.strip()):
        raise HTTPException(status_code=400, detail="Invalid authentication code.")
    current_user.mfa_enabled = True
    codes = new_recovery_codes(settings.MFA_RECOVERY_CODE_COUNT)
    for code in codes:
        db.add(MFARecoveryCode(tenant_id=str(current_user.tenant_id), user_id=str(current_user.id), code_hash=hash_recovery_code(code), consumed=False))
    db.commit()
    return {"mfa_enabled": True, "recovery_codes": codes}


@router.post("/mfa/verify")
def mfa_verify(payload: MFAVerifyRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    enforce_rate_limit(request, action="mfa_verify", max_requests=settings.MFA_MAX_ATTEMPTS, window_seconds=300)
    challenge_hash = hashlib.sha256(payload.challenge_token.encode("utf-8")).hexdigest()
    challenge = db.query(MFAChallenge).filter(MFAChallenge.challenge_token_hash == challenge_hash).with_for_update().first()
    if not challenge:
        raise HTTPException(status_code=401, detail="Invalid MFA challenge.")
    now = datetime.now(timezone.utc)
    expires = challenge.expires_at.replace(tzinfo=timezone.utc) if challenge.expires_at.tzinfo is None else challenge.expires_at
    if challenge.consumed or expires <= now or (challenge.attempts or 0) >= settings.MFA_MAX_ATTEMPTS:
        raise HTTPException(status_code=401, detail="MFA challenge expired or locked.")
    user = db.query(User).filter(User.id == challenge.user_id, User.tenant_id == challenge.tenant_id).first()
    valid = False
    if user and payload.code and user.mfa_secret_encrypted:
        try:
            valid = verify_totp(decrypt_secret(user.mfa_secret_encrypted), payload.code.strip())
        except Exception:
            valid = False
    if not valid and user and payload.recovery_code:
        codes = db.query(MFARecoveryCode).filter(
            MFARecoveryCode.user_id == user.id,
            MFARecoveryCode.tenant_id == user.tenant_id,
            MFARecoveryCode.consumed.is_(False),
        ).with_for_update().all()
        for recovery in codes:
            if verify_recovery_hash(payload.recovery_code.strip(), recovery.code_hash):
                recovery.consumed = True
                valid = True
                break
    if not valid:
        challenge.attempts = int(challenge.attempts or 0) + 1
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid MFA code.")
    challenge.consumed = True
    refresh_token = _issue_refresh_token(db, user, request)
    access = create_access_token(data={"sub": str(user.id), "role": user.role, "sv": user.session_version, "mfa": True})
    db.commit()
    _set_refresh_cookie(response, refresh_token)
    return {"access_token": access, "token_type": "bearer", "user": {"id": str(user.id), "full_name": user.full_name, "email": user.email, "role": user.role}, "mfa_verified": True}


@router.post("/mfa/disable")
def mfa_disable(payload: MFADisableRequest, request: Request, current_user: User = Depends(__import__("src.api.deps", fromlist=["get_current_user"]).get_current_user), db: Session = Depends(get_db)):
    enforce_rate_limit(request, action="mfa_disable", max_requests=5, window_seconds=300)
    if not current_user.mfa_enabled or not current_user.mfa_secret_encrypted:
        raise HTTPException(status_code=409, detail="MFA is not enabled.")
    if not verify_totp(decrypt_secret(current_user.mfa_secret_encrypted), payload.code.strip()):
        raise HTTPException(status_code=400, detail="Invalid authentication code.")
    current_user.mfa_enabled = False
    current_user.mfa_secret_encrypted = None
    db.query(MFARecoveryCode).filter(
        MFARecoveryCode.user_id == current_user.id,
        MFARecoveryCode.tenant_id == current_user.tenant_id,
        MFARecoveryCode.consumed.is_(False),
    ).update({"consumed": True})
    current_user.session_version = int(current_user.session_version or 1) + 1
    db.commit()
    return {"mfa_enabled": False}
