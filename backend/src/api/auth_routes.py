"""
Authentication API routes.

Handles user signup, login, logout, and profile retrieval.
Extracted from the monolithic main.py for clean architectural separation.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.config import settings
from src.database.session import get_db
from src.database.models import User, PasswordResetOTP
from src.utils.auth import get_password_hash, verify_password, create_access_token, verify_token
from src.utils.validators import validate_email, validate_password_strength, validate_full_name, validate_phone
from src.utils.email_otp import generate_otp, hash_otp, otp_expiry, send_otp_email
from src.utils.logger import app_logger

logger = app_logger
router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------
class SignUpRequest(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=3, max_length=254)
    phone: Optional[str] = Field(None, max_length=20)
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
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/signup")
def signup(payload: SignUpRequest, db: Session = Depends(get_db)):
    """Register a new claimant account with validated input."""
    # Validate and sanitize inputs
    try:
        clean_name = validate_full_name(payload.full_name)
        clean_email = validate_email(payload.email)
        validate_password_strength(payload.password)
        clean_phone = validate_phone(payload.phone)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passwords do not match.")

    existing_user = db.query(User).filter(User.email == clean_email).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered.")

    hashed_pwd = get_password_hash(payload.password)
    new_user = User(
        full_name=clean_name,
        email=clean_email,
        phone=clean_phone,
        password_hash=hashed_pwd,
        role="CLAIMANT",  # Public signup always creates CLAIMANT role
        status="active",
    )
    db.add(new_user)
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

    return {
        "id": str(new_user.id),
        "full_name": new_user.full_name,
        "email": new_user.email,
        "phone": new_user.phone,
        "role": new_user.role,
        "status": new_user.status,
    }


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate a user and return a JWT access token."""
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

    access_token = create_access_token(data={"sub": str(user.id), "role": user.role})
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


# ---------------------------------------------------------------------------
# Forgot Password: Step 1 — Request OTP
# ---------------------------------------------------------------------------
@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Issue an email OTP for password reset. Always returns a generic success
    message regardless of whether the email exists, to avoid account enumeration.
    """
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
def verify_otp(payload: VerifyOtpRequest, db: Session = Depends(get_db)):
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
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
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

    record = db.query(PasswordResetOTP).filter(PasswordResetOTP.id == otp_id).first()
    if not record or not record.verified or record.consumed:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This reset code has already been used or is no longer valid. Please restart the process.",
        )

    user.password_hash = get_password_hash(payload.new_password)  # type: ignore[assignment]
    record.consumed = True  # type: ignore[assignment]
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to reset password for user %s", user_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Password reset failed. Please try again.")

    return {"message": "Password has been reset successfully. You can now log in with your new password."}


@router.post("/logout")
def logout():
    """
    Logout endpoint. In a stateless JWT architecture, actual token revocation
    requires a server-side token blacklist (Redis). For now, the client must
    discard the token. This endpoint exists for API completeness.
    """
    return {"message": "Logged out successfully. Please discard your access token."}
