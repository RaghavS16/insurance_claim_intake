"""SMTP delivery for adjuster onboarding invitations."""
from src.utils.email_otp import send_invitation_email

def send_adjuster_invite_email(to_email: str, full_name: str, invite_url: str) -> bool:
    return send_invitation_email(to_email, full_name, invite_url)

