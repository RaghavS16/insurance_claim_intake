"""SMTP delivery for adjuster onboarding invitations."""
from email.mime.text import MIMEText
from email.utils import formataddr
import smtplib
from src.config import settings
from src.utils.logger import app_logger
logger=app_logger

def send_adjuster_invite_email(to_email: str, full_name: str, invite_url: str) -> bool:
    subject="Your InsureClaim AI adjuster invitation"
    body=(f"Hi {full_name},\n\nYou have been invited to join InsureClaim AI as a claims adjuster.\n\n"
          f"Complete your account and passkey setup here:\n{invite_url}\n\n"
          "This invitation expires in 3 days.\n")
    if not settings.SMTP_HOST:
        if settings.ENVIRONMENT not in {"production","staging"}:
            logger.info("Adjuster invitation URL for %s: %s", to_email, invite_url)
        return False
    from_email=settings.SMTP_USERNAME or settings.SMTP_FROM_EMAIL
    msg=MIMEText(body); msg["Subject"]=subject; msg["From"]=formataddr((getattr(settings,"SMTP_FROM_NAME","InsureClaim AI"),from_email)); msg["To"]=to_email
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            if settings.SMTP_USE_TLS: server.starttls()
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD: server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD.replace(" ","").strip())
            server.sendmail(from_email,[to_email],msg.as_string())
        return True
    except Exception:
        logger.exception("Failed to send adjuster invitation email to %s",to_email)
        return False
