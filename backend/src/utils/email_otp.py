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
    subject = "Verify your IntelliClaim email" if purpose == "email_verification" else "Your IntelliClaim password reset code"
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


def _send_email_brevo(to_email: str, subject: str, body: str) -> bool:
    """Deliver email via Brevo HTTP API (Port 443, sub-200ms)."""
    import os
    import httpx
    api_key = os.getenv("BREVO_API_KEY") or getattr(settings, "BREVO_API_KEY", None)
    if not api_key:
        return False
    from_email = os.getenv("SMTP_EMAIL") or settings.SMTP_FROM_EMAIL or "no-reply@insurance-claims.local"
    from_name = getattr(settings, "SMTP_FROM_NAME", "IntelliClaim Security") or "IntelliClaim Security"
    html_body = f"<html><body style='font-family: Arial, sans-serif; line-height: 1.6;'><p>{body.replace(chr(10), '<br>')}</p></body></html>"
    payload = {
        "sender": {"name": from_name, "email": from_email},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_body,
        "textContent": body,
    }
    headers = {
        "api-key": api_key.strip(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post("https://api.brevo.com/v3/smtp/email", json=payload, headers=headers)
            if resp.status_code in (200, 201, 202):
                logger.info("Successfully sent email to %s via Brevo HTTPS API", to_email)
                return True
            logger.warning("Brevo API responded with status %d: %s", resp.status_code, resp.text)
    except Exception as exc:
        logger.warning("Brevo HTTPS API delivery to %s failed: %s", to_email, exc)
    return False


def _send_email_resend(to_email: str, subject: str, body: str) -> bool:
    """Deliver email via Resend HTTP API (Port 443, sub-200ms)."""
    import os
    import httpx
    api_key = os.getenv("RESEND_API_KEY") or getattr(settings, "RESEND_API_KEY", None)
    if not api_key:
        return False
    from_email = os.getenv("SMTP_EMAIL") or settings.SMTP_FROM_EMAIL or "onboarding@resend.dev"
    from_name = getattr(settings, "SMTP_FROM_NAME", "IntelliClaim Security") or "IntelliClaim Security"
    html_body = f"<p>{body.replace(chr(10), '<br>')}</p>"
    payload = {
        "from": f"{from_name} <{from_email}>",
        "to": [to_email],
        "subject": subject,
        "text": body,
        "html": html_body,
    }
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post("https://api.resend.com/emails", json=payload, headers=headers)
            if resp.status_code in (200, 201, 202):
                logger.info("Successfully sent email to %s via Resend HTTPS API", to_email)
                return True
            logger.warning("Resend API responded with status %d: %s", resp.status_code, resp.text)
    except Exception as exc:
        logger.warning("Resend HTTPS API delivery to %s failed: %s", to_email, exc)
    return False


def _send_email_smtp(to_email: str, subject: str, body: str) -> bool:
    """Send an email using configured EMAIL_BACKEND (mailpit vs real SMTP) with fast-fail retry logic."""
    from_email = settings.SMTP_FROM_EMAIL or "no-reply@insurance-claims.local"
    from_name = getattr(settings, "SMTP_FROM_NAME", "IntelliClaim AI") or "IntelliClaim AI"

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, from_email))
    msg["To"] = to_email

    is_mailpit = getattr(settings, "EMAIL_BACKEND", "mailpit").lower() == "mailpit"
    if is_mailpit and settings.ENVIRONMENT in ("production", "staging"):
        logger.error("Mailpit is strictly forbidden in production or staging environments.")
        return False

    if not settings.SMTP_HOST:
        logger.warning("SMTP_HOST is not configured; cannot deliver email.")
        return False

    host = settings.SMTP_HOST
    if is_mailpit and host in ("localhost", "127.0.0.1"):
        import socket
        try:
            socket.gethostbyname("mailpit")
            host = "mailpit"
        except (socket.error, OSError):
            pass

    port = 1025 if is_mailpit else (settings.SMTP_PORT or 587)
    use_tls = False if is_mailpit else bool(settings.SMTP_USE_TLS)
    use_ssl = False if is_mailpit else bool(settings.SMTP_USE_SSL)
    timeout = getattr(settings, "SMTP_TIMEOUT_SECONDS", 4) or 4
    smtp_username = (settings.SMTP_USERNAME or "").strip() if not is_mailpit else ""
    smtp_password = (settings.SMTP_PASSWORD or "") if not is_mailpit else ""  # Never strip internal spaces

    # Fast-fail in cloud/local: 1 attempt with tight 4s timeout so a blocked port fails immediately
    max_attempts = 1
    for attempt in range(1, max_attempts + 1):
        try:
            if use_ssl:
                with smtplib.SMTP_SSL(host, port, timeout=timeout) as server:
                    if smtp_username and smtp_password:
                        server.login(smtp_username, smtp_password)
                    server.sendmail(from_email, [to_email], msg.as_string())
            else:
                with smtplib.SMTP(host, port, timeout=timeout) as server:
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


def _deliver_email(to_email: str, subject: str, body: str) -> bool:
    """Deliver email via HTTPS Port 443 (Brevo, then Resend) with fast-fail SMTP fallback."""
    import os
    if os.getenv("BREVO_API_KEY") or getattr(settings, "BREVO_API_KEY", None):
        if _send_email_brevo(to_email, subject, body):
            return True
    if os.getenv("RESEND_API_KEY") or getattr(settings, "RESEND_API_KEY", None):
        if _send_email_resend(to_email, subject, body):
            return True
    return _send_email_smtp(to_email, subject, body)


def send_otp_email(to_email: str, otp: str, full_name: Optional[str] = None, purpose: str = "password_reset") -> bool:
    """
    Send the OTP via configured HTTPS API or email backend with retries.
    Never logs plaintext OTP in production.
    """
    # Normalize purpose aliases
    if purpose in ("VERIFY", "verify"):
        purpose = "email_verification"
    elif purpose in ("RESET", "reset"):
        purpose = "password_reset"

    subject, body = otp_subject_body(otp, full_name=full_name, purpose=purpose)

    if settings.ENVIRONMENT not in ("production", "staging"):
        logger.info("Generated %s OTP for %s: %s (dev/test)", purpose, to_email, otp)
    else:
        logger.info("%s OTP generated for %s (masked: %s***%s)", purpose, to_email, otp[:1], otp[-1:])

    return _deliver_email(to_email, subject, body)


def dispatch_otp_email_background(to_email: str, otp: str, full_name: Optional[str] = None, purpose: str = "password_reset") -> None:
    """Safely invokes send_otp_email inside a try...except block for FastAPI BackgroundTasks."""
    try:
        success = send_otp_email(to_email, otp, full_name=full_name, purpose=purpose)
        if success:
            logger.info("Background OTP email delivered to %s (purpose=%s)", to_email, purpose)
        else:
            logger.warning("Background OTP email delivery failed for %s (purpose=%s)", to_email, purpose)
    except Exception as exc:
        logger.exception("Background OTP dispatch exception for %s: %s", to_email, exc)


def send_invitation_email(to_email: str, name: str, invite_url: str) -> bool:
    """Send adjuster invitation email with onboarding link."""
    subject = "Your IntelliClaim adjuster invitation"
    body = (
        f"Hi {name},\n\n"
        "You have been invited to join IntelliClaim as a claims adjuster.\n\n"
        f"Complete your account setup here:\n{invite_url}\n\n"
        "This invitation expires in 3 days.\n"
    )
    return _deliver_email(to_email, subject, body)

