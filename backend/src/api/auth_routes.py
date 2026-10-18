"""
Authentication API routes.

Handles user signup, login, logout, and profile retrieval.
Extracted from the monolithic main.py for clean architectural separation.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import hashlib
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.config import settings
from src.database.session import get_db
from src.database.models import User, PasswordResetOTP, RevokedToken, Adjuster
from src.database.hardening_models import Tenant, TenantMembership, RefreshToken
from src.utils.auth import get_password_hash, verify_password, create_access_token, verify_token, revoke_token
from src.utils.validators import validate_email, validate_password_strength, validate_full_name, validate_phone
from src.utils.email_otp import generate_otp, hash_otp, otp_expiry, queue_otp_email, send_otp_email
from src.utils.rate_limiter import enforce_rate_limit
from src.utils.logger import app_logger
from src.api.deps import get_current_user

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

class EmailOnlyRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)


class VerifyOtpRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    otp: str = Field(..., min_length=4, max_length=8)


class RefreshTokenRequest(BaseModel):
    refresh_token: Optional[str] = Field(None, min_length=20, max_length=512)


def set_refresh_token_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=(settings.ENVIRONMENT == "production"),
        samesite="strict",
        path="/api/v1/auth",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )


def clear_refresh_token_cookie(response: Response) -> None:
    response.delete_cookie(
        key="refresh_token",
        path="/api/v1/auth",
        httponly=True,
        secure=(settings.ENVIRONMENT == "production"),
        samesite="strict",
    )


class ResetPasswordRequest(BaseModel):
    reset_token: str = Field(..., min_length=10)
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)


def _issue_refresh_token(db: Session, user: User, family_id: str | None = None, *, auth_context: dict | None = None) -> str:
    """Create an opaque refresh token; only its SHA-256 hash is persisted."""
    raw = secrets.token_urlsafe(48)
    db.add(RefreshToken(
        user_id=user.id,
        tenant_id=user.tenant_id or "",
        token_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        family_id=family_id or str(uuid.uuid4()),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        auth_context_json=auth_context or {"mfa": False, "amr": ["pwd"]},
    ))
    return raw


def _rotate_refresh_token(db: Session, raw: str) -> tuple[User, str]:
    """Consume one refresh token and issue exactly one replacement."""
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == digest).with_for_update().first()
    now = datetime.now(timezone.utc)
    if not row:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token.")
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    if row.revoked_at or row.used_at or expires <= now:
        if row.used_at and not row.revoked_at:
            db.query(RefreshToken).filter(
                RefreshToken.family_id == row.family_id,
                RefreshToken.tenant_id == row.tenant_id,
                RefreshToken.revoked_at.is_(None),
            ).update({RefreshToken.revoked_at: now}, synchronize_session=False)
            db.commit()
        else:
            db.rollback()
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token.")
    user = db.query(User).filter(User.id == row.user_id, User.tenant_id == row.tenant_id, User.status == "active").first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token.")
    row.used_at = now
    replacement = _issue_refresh_token(db, user, row.family_id, auth_context=dict(row.auth_context_json or {"mfa": False, "amr": ["pwd"]}))
    db.flush()
    return user, replacement


def _auth_response(user: User, refresh_token: str, *, amr: list[str] | None = None, mfa_authenticated: bool = False) -> dict:
    sv = int(getattr(user, "session_version", 1) or 1)
    return {
        "access_token": create_access_token(data={"sub": user.id, "tenant_id": user.tenant_id or "", "role": user.role, "sv": sv, "mfa": mfa_authenticated, "amr": amr or []}),
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {"id": user.id, "full_name": user.full_name, "email": user.email, "role": user.role},
    }


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

    existing_user = db.query(User).filter(User.email == clean_email, User.tenant_id.is_not(None)).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered.")

    hashed_pwd = get_password_hash(payload.password)
    tenant = db.query(Tenant).filter(Tenant.id == "00000000-0000-0000-0000-000000000001").first()
    if not tenant:
        tenant = db.query(Tenant).filter(Tenant.status == "active").first()
    if not tenant:
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
    db.add(TenantMembership(tenant_id=tenant.id, user_id=new_user.id, role="CLAIMANT", status="active"))

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

    verification_required = bool(settings.REQUIRE_EMAIL_VERIFICATION)
    if verification_required:
        verification_code = generate_otp()
        record = PasswordResetOTP(
            user_id=new_user.id,
            tenant_id=tenant.id,
            otp_hash=hash_otp(verification_code),
            purpose="email_verification",
            expires_at=otp_expiry(),
            attempts=0,
            verified=False,
            consumed=False,
        )
        db.add(record)
        db.flush()
        email_event = queue_otp_email(
            db,
            to_email=new_user.email,
            otp=verification_code,
            full_name=new_user.full_name,
            purpose="email_verification",
            event_key=f"email-verification:{new_user.id}:{record.id}",
        )
        try:
            if send_otp_email(to_email=new_user.email, otp=verification_code, full_name=new_user.full_name, purpose="email_verification"):
                if email_event:
                    email_event.status = "sent"
                    email_event.processed_at = datetime.now(timezone.utc)
        except Exception:
            pass
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to finalize claimant registration")
        raise HTTPException(status_code=500, detail="Account creation failed. Please try again.")
    return {
        "id": new_user.id,
        "full_name": new_user.full_name,
        "email": new_user.email,
        "phone": new_user.phone,
        "role": new_user.role,
        "status": new_user.status,
        "email_verification_required": verification_required,
    }


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    """Authenticate a user and return a JWT access token."""
    enforce_rate_limit(request, action="login", max_requests=10, window_seconds=60)
    try:
        clean_email = validate_email(payload.email)
    except ValueError:
        # Constant-time dummy verify to prevent timing enumeration
        DUMMY_BCRYPT_HASH = "$2b$12$e86g5WzY44dE9Bsm4N4b5uQj9Uomv1d/c2zF5tXq2K1s5c8c5z1G."
        verify_password(payload.password, DUMMY_BCRYPT_HASH)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    from src.utils.account_lockout import check_account_lock, record_auth_failure, record_auth_success
    check_account_lock("login", clean_email)

    user = db.query(User).filter(User.email == clean_email, User.tenant_id.is_not(None)).first()
    if not user:
        # Constant-time dummy verify for non-existent account
        DUMMY_BCRYPT_HASH = "$2b$12$e86g5WzY44dE9Bsm4N4b5uQj9Uomv1d/c2zF5tXq2K1s5c8c5z1G."
        verify_password(payload.password, DUMMY_BCRYPT_HASH)
        record_auth_failure("login", clean_email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not verify_password(payload.password, user.password_hash):
        record_auth_failure("login", clean_email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    record_auth_success("login", clean_email)

    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled. Please contact support.",
        )

    if user.role == "ADJUSTER":
        adjuster = db.query(Adjuster).filter(
            Adjuster.user_id == user.id,
            Adjuster.tenant_id == user.tenant_id,
        ).first()
        if not adjuster or not adjuster.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Adjuster onboarding is incomplete. Please finish invitation setup before signing in.",
            )

    user.last_login_at = datetime.now(timezone.utc)
    user.session_version = int(getattr(user, "session_version", 1) or 1)
    db.commit()
    if settings.REQUIRE_EMAIL_VERIFICATION and not user.email_verified_at:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Please verify your email before signing in.")
    auth_context = {"mfa": False, "amr": ["pwd"]}
    refresh_token = _issue_refresh_token(db, user, auth_context=auth_context)
    db.commit()
    set_refresh_token_cookie(response, refresh_token)
    access_token = create_access_token(data={"sub": user.id, "tenant_id": user.tenant_id or "", "role": user.role, "sv": user.session_version, **auth_context})
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
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

    from src.utils.account_lockout import check_account_lock, record_auth_failure, record_auth_success
    check_account_lock("verify_email", clean_email)

    user = db.query(User).filter(User.email == clean_email, User.tenant_id.is_not(None)).first()
    if not user:
        record_auth_failure("verify_email", clean_email)
        raise HTTPException(status_code=400, detail="Invalid email or verification code.")
    record = (
        db.query(PasswordResetOTP)
        .filter(PasswordResetOTP.user_id == user.id, PasswordResetOTP.tenant_id == user.tenant_id, PasswordResetOTP.purpose == "email_verification", PasswordResetOTP.consumed == False)
        .order_by(PasswordResetOTP.created_at.desc())
        .with_for_update()
        .first()
    )
    if not record:
        record_auth_failure("verify_email", clean_email)
        raise HTTPException(status_code=400, detail="Invalid or expired verification code.")
    now = datetime.now(timezone.utc)
    expires = record.expires_at.replace(tzinfo=timezone.utc) if record.expires_at.tzinfo is None else record.expires_at
    if now > expires or (record.attempts or 0) >= settings.OTP_MAX_ATTEMPTS:
        record_auth_failure("verify_email", clean_email)
        raise HTTPException(status_code=400, detail="Invalid or expired verification code.")
    if hash_otp(payload.otp.strip()) != record.otp_hash:
        record.attempts = (record.attempts or 0) + 1
        db.commit()
        record_auth_failure("verify_email", clean_email)
        raise HTTPException(status_code=400, detail="Invalid or expired verification code.")
    record.verified = True
    record.consumed = True
    user.email_verified_at = now
    db.commit()
    record_auth_success("verify_email", clean_email)
    return {"message": "Email verified successfully. You can now sign in."}



# ---------------------------------------------------------------------------
# Forgot Password: Step 1 — Request OTP
# ---------------------------------------------------------------------------

@router.post("/resend-verification")
def resend_verification(payload: EmailOnlyRequest, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(request, action="resend_verification", max_requests=5, window_seconds=300)
    generic = {"message": "If an account with that email requires verification, a new verification code has been sent."}
    if not settings.REQUIRE_EMAIL_VERIFICATION:
        return generic
    try:
        clean_email = validate_email(payload.email)
    except ValueError:
        return generic
    user = db.query(User).filter(User.email == clean_email, User.tenant_id.is_not(None), User.status == "active").first()
    if not user or user.email_verified_at:
        return generic
    latest = (
        db.query(PasswordResetOTP)
        .filter(
            PasswordResetOTP.user_id == user.id,
            PasswordResetOTP.tenant_id == user.tenant_id,
            PasswordResetOTP.purpose == "email_verification",
            PasswordResetOTP.consumed == False,
        )
        .order_by(PasswordResetOTP.created_at.desc())
        .with_for_update()
        .first()
    )
    now = datetime.now(timezone.utc)
    if latest and latest.created_at:
        created_at = latest.created_at.replace(tzinfo=timezone.utc) if latest.created_at.tzinfo is None else latest.created_at
        if (now - created_at).total_seconds() < settings.OTP_RESEND_COOLDOWN_SECONDS:
            return generic
        latest.consumed = True
    otp = generate_otp()
    record = PasswordResetOTP(
        user_id=user.id,
        tenant_id=user.tenant_id or "",
        otp_hash=hash_otp(otp),
        purpose="email_verification",
        expires_at=otp_expiry(),
        attempts=0,
        verified=False,
        consumed=False,
    )
    db.add(record)
    db.flush()
    event = queue_otp_email(
        db,
        to_email=user.email,
        otp=otp,
        full_name=user.full_name,
        purpose="email_verification",
        event_key=f"email-verification:{user.id}:{record.id}",
    )
    try:
        if send_otp_email(to_email=user.email, otp=otp, full_name=user.full_name, purpose="email_verification"):
            if event:
                event.status = "sent"
                event.processed_at = datetime.now(timezone.utc)
    except Exception:
        pass
    db.commit()
    return generic


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

    from sqlalchemy import func
    user = db.query(User).filter(
        func.lower(func.trim(User.email)) == clean_email.lower().strip()
    ).first()
    if not user or user.status != "active":
        return generic_response

    # Rate-limit resends in production/staging environments
    if settings.ENVIRONMENT not in ("development", "test"):
        recent = (
            db.query(PasswordResetOTP)
            .filter(PasswordResetOTP.user_id == user.id, PasswordResetOTP.tenant_id == user.tenant_id, PasswordResetOTP.purpose == "password_reset", PasswordResetOTP.consumed == False)  # noqa: E712
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
        tenant_id=user.tenant_id or "",
        otp_hash=hash_otp(otp),
        purpose="password_reset",
        expires_at=otp_expiry(),
        attempts=0,
        verified=False,
        consumed=False,
    )
    db.add(record)
    try:
        db.flush()
        event = queue_otp_email(
            db,
            to_email=user.email,
            otp=otp,
            full_name=user.full_name,
            purpose="password_reset",
            event_key=f"password-reset:{user.id}:{record.id}",
        )
        try:
            if send_otp_email(to_email=user.email, otp=otp, full_name=user.full_name, purpose="password_reset"):
                if event:
                    event.status = "sent"
                    event.processed_at = datetime.now(timezone.utc)
        except Exception:
            pass
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to queue password reset email for user %s", user.id)
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

    from src.utils.account_lockout import check_account_lock, record_auth_failure, record_auth_success
    check_account_lock("verify_otp", clean_email)

    generic_invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired code. Please request a new one.",
    )

    user = db.query(User).filter(User.email == clean_email, User.tenant_id.is_not(None)).first()
    if not user:
        record_auth_failure("verify_otp", clean_email)
        raise generic_invalid

    record = (
        db.query(PasswordResetOTP)
        .filter(PasswordResetOTP.user_id == user.id, PasswordResetOTP.tenant_id == user.tenant_id, PasswordResetOTP.purpose == "password_reset", PasswordResetOTP.consumed == False)  # noqa: E712
        .order_by(PasswordResetOTP.created_at.desc())
        .with_for_update()
        .first()
    )
    if not record:
        record_auth_failure("verify_otp", clean_email)
        raise generic_invalid

    now = datetime.now(timezone.utc)
    expires_at = record.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at and now > expires_at:
        record_auth_failure("verify_otp", clean_email)
        raise generic_invalid

    if (record.attempts or 0) >= settings.OTP_MAX_ATTEMPTS:
        record_auth_failure("verify_otp", clean_email)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many incorrect attempts. Please request a new code.",
            headers={"Retry-After": "300"},  # Suggest retry after 5 minutes
        )

    if hash_otp(payload.otp.strip()) != record.otp_hash:
        record.attempts = (record.attempts or 0) + 1  # type: ignore[assignment]
        db.commit()
        record_auth_failure("verify_otp", clean_email)
        raise generic_invalid

    record.verified = True  # type: ignore[assignment]
    db.commit()
    record_auth_success("verify_otp", clean_email)

    reset_token = create_access_token(
        data={"sub": user.id, "purpose": "password_reset", "otp_id": record.id},
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
    user = db.query(User).filter(User.id == user_id, User.tenant_id.is_not(None)).first()
    if not user or not getattr(user, "tenant_id", None):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid reset token.")

    from src.utils.account_lockout import check_account_lock, record_auth_failure, record_auth_success
    check_account_lock("reset_password", user.email)

    record = db.query(PasswordResetOTP).filter(PasswordResetOTP.id == otp_id, PasswordResetOTP.user_id == user.id, PasswordResetOTP.tenant_id == user.tenant_id).first()
    if not record or not record.verified or record.consumed:
        record_auth_failure("reset_password", user.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This reset code has already been used or is no longer valid. Please restart the process.",
        )

    user.password_hash = get_password_hash(payload.new_password)  # type: ignore[assignment]
    user.session_version = int(getattr(user, "session_version", 1) or 1) + 1
    record.consumed = True  # type: ignore[assignment]
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user.id,
        RefreshToken.tenant_id == user.tenant_id,
        RefreshToken.revoked_at.is_(None),
    ).update({RefreshToken.revoked_at: datetime.now(timezone.utc)}, synchronize_session=False)
    # Revoke the reset token so it cannot be used again
    revoke_token(payload.reset_token)

    try:
        db.commit()
        record_auth_success("reset_password", user.email)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Password reset could not be completed.")
    except Exception:
        db.rollback()
        logger.exception("Failed to reset password for user %s", user_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Password reset failed. Please try again.")

    return {"message": "Password has been reset successfully. You can now log in with your new password."}


@router.post("/refresh")
def refresh_access_token(
    request: Request,
    response: Response,
    payload: Optional[RefreshTokenRequest] = None,
    db: Session = Depends(get_db),
):
    enforce_rate_limit(request, action="refresh", max_requests=30, window_seconds=60)
    origin = request.headers.get("origin")
    if origin:
        allowed = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
        if origin not in allowed:
            raise HTTPException(status_code=403, detail="Cross-origin refresh forbidden.")

    raw = request.cookies.get("refresh_token")
    if not raw:
        if settings.ENVIRONMENT != "production" and payload and payload.refresh_token:
            raw = payload.refresh_token.strip()
        else:
            raise HTTPException(status_code=401, detail="Refresh token is required.")

    user, replacement = _rotate_refresh_token(db, raw)
    db.commit()
    set_refresh_token_cookie(response, replacement)
    old_row = db.query(RefreshToken).filter(RefreshToken.token_hash == hashlib.sha256(raw.encode("utf-8")).hexdigest()).first()
    context: dict[str, Any] = dict((old_row.auth_context_json if old_row else None) or {"mfa": False, "amr": ["pwd"]})
    return _auth_response(user, replacement, amr=list(context.get("amr") or []), mfa_authenticated=bool(context.get("mfa")))


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Logout endpoint. Clears refresh token cookie and revokes the token family.
    """
    clear_refresh_token_cookie(response)
    raw_cookie = request.cookies.get("refresh_token")
    now = datetime.now(timezone.utc)
    if raw_cookie:
        cookie_hash = hashlib.sha256(raw_cookie.encode("utf-8")).hexdigest()
        row = db.query(RefreshToken).filter(RefreshToken.token_hash == cookie_hash).first()
        if row and row.family_id:
            db.query(RefreshToken).filter(
                RefreshToken.family_id == row.family_id,
                RefreshToken.tenant_id == row.tenant_id,
                RefreshToken.revoked_at.is_(None),
            ).update({RefreshToken.revoked_at: now}, synchronize_session=False)
            db.commit()

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        try:
            import jwt as _jwt
            payload = _jwt.decode(token, options={"verify_signature": False})
            revoke_token(token)
            jti = payload.get("jti") or token
            exp_ts = payload.get("exp")
            exp_dt = datetime.fromtimestamp(exp_ts, tz=timezone.utc) if exp_ts else now + timedelta(hours=1)
            user_id = str(payload.get("sub") or "")
            user = db.query(User).filter(User.id == user_id, User.tenant_id.is_not(None)).first()
            db.add(RevokedToken(
                token_jti=jti,
                user_id=user_id or None,
                tenant_id=str(user.tenant_id) if user else None,
                expires_at=exp_dt,
            ))
            if user:
                db.query(RefreshToken).filter(
                    RefreshToken.user_id == user.id,
                    RefreshToken.tenant_id == user.tenant_id,
                    RefreshToken.revoked_at.is_(None),
                ).update({RefreshToken.revoked_at: now}, synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()

    return {"message": "Logged out successfully. Token has been revoked."}

    return {"message": "Logged out successfully. Token has been revoked."}
