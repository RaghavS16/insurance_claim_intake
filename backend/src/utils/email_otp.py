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
from email.utils import formataddr
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



def otp_subject_body(otp: str, full_name: Optional[str] = None, purpose: str = "password_reset") -> tuple[str, str]:
    subject = "Verify your InsureClaimAI email" if purpose == "email_verification" else "Your InsureClaimAI password reset code"
    greeting = f"Hi {full_name}," if full_name else "Hi,"
    label = "email verification" if purpose == "email_verification" else "password reset verification"
    body = (
        f"{greeting}\n\n"
        f"Your {label} code is: {otp}\n\n"
        f"This code expires in {settings.OTP_EXPIRY_MINUTES} minutes. "
        "If you didn't request this, you can safely ignore this email.\n"
    )
    return subject, body


def queue_otp_email(db, *, to_email: str, otp: str, full_name: Optional[str], purpose: str, event_key: str):
    from src.services.outbox import enqueue
    subject, body = otp_subject_body(otp, full_name=full_name, purpose=purpose)
    return enqueue(
        db,
        event_type="email.verification" if purpose == "email_verification" else "email.password_reset",
        aggregate_type="user",
        aggregate_id=to_email,
        payload={"to": to_email, "subject": subject, "body": body, "purpose": purpose},
        idempotency_key=event_key,
    )


def _send_email_smtp(to_email: str, subject: str, body: str) -> bool:
    """Send an email using configured EMAIL_BACKEND (mailpit vs real SMTP) with retry logic."""
    from_email = settings.SMTP_FROM_EMAIL or "raghavradhakrishnan.d@gmail.com"
    from_name = getattr(settings, "SMTP_FROM_NAME", "InsureClaim AI") or "InsureClaim AI"

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, from_email))
    msg["To"] = to_email

    is_mailpit = getattr(settings, "EMAIL_BACKEND", "mailpit").lower() == "mailpit"
    host = "127.0.0.1" if is_mailpit else (settings.SMTP_HOST or "127.0.0.1")
    port = 1025 if is_mailpit else (settings.SMTP_PORT or 587)
    use_tls = False if is_mailpit else bool(settings.SMTP_USE_TLS)
    smtp_username = (settings.SMTP_USERNAME or "").strip() if not is_mailpit else ""
    smtp_password = (settings.SMTP_PASSWORD or "").replace(" ", "").strip() if not is_mailpit else ""

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            with smtplib.SMTP(host, port, timeout=10) as server:
                if use_tls:
                    server.starttls()
                if smtp_username and smtp_password:
                    server.login(smtp_username, smtp_password)
                server.sendmail(from_email, [to_email], msg.as_string())
            logger.info("Successfully sent email to %s via %s (%s:%s)", to_email, "Mailpit" if is_mailpit else "SMTP", host, port)
            return True
        except Exception as exc:
            logger.warning("Email delivery attempt %d/%d to %s failed: %s", attempt, max_attempts, to_email, exc)
            if attempt == max_attempts:
                logger.exception("Final failure sending email to %s", to_email)
                return False
            import time
            time.sleep(0.5 * attempt)
    return False


def send_otp_email(to_email: str, otp: str, full_name: Optional[str] = None, purpose: str = "password_reset") -> bool:
    """
    Send the OTP via configured email backend (Mailpit or SMTP) with retries.
    Never logs plaintext OTP in production.
    """
    subject, body = otp_subject_body(otp, full_name=full_name, purpose=purpose)

    if settings.ENVIRONMENT not in ("production", "staging"):
        logger.info("Generated %s OTP for %s: %s (dev/test)", purpose, to_email, otp)
    else:
        logger.info("%s OTP generated for %s (masked: %s***%s)", purpose, to_email, otp[:1], otp[-1:])

    return _send_email_smtp(to_email, subject, body)


def send_invitation_email(to_email: str, name: str, invite_url: str) -> bool:
    """Send adjuster invitation email with onboarding link."""
    subject = "Your InsureClaim AI adjuster invitation"
    body = (
        f"Hi {name},\n\n"
        "You have been invited to join InsureClaim AI as a claims adjuster.\n\n"
        f"Complete your account and passkey setup here:\n{invite_url}\n\n"
        "This invitation expires in 3 days.\n"
    )
    return _send_email_smtp(to_email, subject, body)

