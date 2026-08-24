"""
OTP generation, hashing, and email dispatch for forgot-password flow.

If SMTP is not configured (dev/test), the OTP is logged instead of emailed —
mirrors the TTS fallback pattern used elsewhere in this codebase.
"""
import hashlib
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from typing import Optional

from src.config import settings
from src.utils.logger import app_logger

logger = app_logger


def generate_otp() -> str:
    """Generate a cryptographically secure numeric OTP of configured length."""
    digits = "0123456789"
    return "".join(secrets.choice(digits) for _ in range(settings.OTP_LENGTH))


def hash_otp(otp: str) -> str:
    """Hash an OTP for storage (OTPs are short-lived and low-entropy — SHA-256 is
    sufficient here, unlike passwords which use bcrypt)."""
    return hashlib.sha256(otp.encode("utf-8")).hexdigest()


def otp_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=settings.OTP_EXPIRY_MINUTES)


def send_otp_email(to_email: str, otp: str, full_name: Optional[str] = None) -> bool:
    """
    Send the OTP via SMTP. If SMTP is not configured or fails, logs the OTP instead
    (dev/test convenience — mirrors TTSError fallback pattern elsewhere).
    Returns True if an email was actually sent, False if it fell back to logging.
    """
    subject = "Your InsureClaimAI password reset code"
    greeting = f"Hi {full_name}," if full_name else "Hi,"
    body = (
        f"{greeting}\n\n"
        f"Your password reset verification code is: {otp}\n\n"
        f"This code expires in {settings.OTP_EXPIRY_MINUTES} minutes. "
        f"If you didn't request this, you can safely ignore this email.\n"
    )

    # Always log OTP in application logs for development transparency
    logger.info("Generated Password Reset OTP for %s: %s", to_email, otp)

    if not settings.SMTP_HOST:
        logger.info("SMTP not configured — OTP for %s is: %s (dev/test fallback)", to_email, otp)
        return False

    from_email = settings.SMTP_USERNAME or settings.SMTP_FROM_EMAIL
    smtp_password = (settings.SMTP_PASSWORD or "").replace(" ", "").strip()
    smtp_username = (settings.SMTP_USERNAME or "").strip()

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            if smtp_username and smtp_password:
                server.login(smtp_username, smtp_password)
            server.sendmail(from_email, [to_email], msg.as_string())
        logger.info("Successfully sent OTP email to %s via SMTP (%s)", to_email, settings.SMTP_HOST)
        return True
    except Exception:
        logger.exception("Failed to send OTP email to %s", to_email)
        logger.info("OTP for %s (SMTP send failed, fallback log): %s", to_email, otp)
        return False
