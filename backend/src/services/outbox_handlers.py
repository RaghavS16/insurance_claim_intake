"""Concrete transactional-outbox handlers for claim lifecycle notifications."""
from __future__ import annotations

import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid

from src.config import settings
from src.database.hardening_models import OutboxEvent
from src.database.models import Claim, User
from src.database.session import SessionLocal
from src.knowledge.store import ingest_document
from src.storage.s3 import get_bytes, delete_bytes
from src.utils.logger import app_logger

logger = app_logger


def _send_email(to_email: str, subject: str, body: str, event_id: str) -> None:
    if not settings.SMTP_HOST:
        if settings.ENVIRONMENT in {"development", "test"}:
            logger.info("Outbox notification suppressed because SMTP is not configured (event=%s)", event_id)
        return
    from_email = (settings.SMTP_USERNAME or settings.SMTP_FROM_EMAIL).strip()
    from_name = getattr(settings, "SMTP_FROM_NAME", "InsureClaim AI") or "InsureClaim AI"
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, from_email))
    msg["To"] = to_email
    msg["Message-ID"] = make_msgid(domain=(from_email.split("@", 1)[-1] or "localhost"))
    msg["X-InsureClaim-Event-ID"] = event_id
    password = (settings.SMTP_PASSWORD or "").replace(" ", "").strip()
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
        if settings.SMTP_USE_TLS:
            server.starttls()
        if settings.SMTP_USERNAME and password:
            server.login(settings.SMTP_USERNAME, password)
        server.sendmail(from_email, [to_email], msg.as_string())


def _claimant_for_event(db, event: OutboxEvent) -> User | None:
    if event.aggregate_type != "claim":
        return None
    claim = db.query(Claim).filter(
        Claim.id == event.aggregate_id,
        Claim.tenant_id == event.tenant_id,
    ).first()
    if not claim or not claim.claimant_id:
        return None
    return db.query(User).filter(
        User.id == claim.claimant_id,
        User.tenant_id == event.tenant_id,
        User.status == "active",
    ).first()


async def handle_claim_event(event: OutboxEvent) -> None:
    """Deliver one claim lifecycle notification; safe to retry at the outbox layer."""
    import asyncio

    db = SessionLocal()
    try:
        claimant = _claimant_for_event(db, event)
        if not claimant or not claimant.email:
            return
        payload = dict(event.payload_json or {})
        if event.event_type == "claim.assigned":
            subject = f"Claim #{event.aggregate_id} assigned for review"
            body = (
                "Your insurance claim has been assigned to a claims adjuster. "
                "You can continue to follow its progress in the claim portal."
            )
        elif event.event_type == "claim.status_changed":
            status = str(payload.get("new_status") or "updated")
            subject = f"Claim status update: {status}"
            body = f"Your insurance claim status has been updated to: {status}."
        else:
            return
        await asyncio.to_thread(_send_email, str(claimant.email), subject, body, str(event.id))
    finally:
        db.close()




async def handle_knowledge_ingest(event: OutboxEvent) -> None:
    """Process one staged knowledge document outside the HTTP request lifecycle."""
    import asyncio
    payload = dict(event.payload_json or {})
    tenant_id = str(event.tenant_id or payload.get("tenant_id") or "")
    key = str(payload.get("key") or "")
    filename = str(payload.get("filename") or "")
    if not tenant_id or not key or not filename:
        raise ValueError("Knowledge ingestion event is missing required metadata.")
    content = await asyncio.to_thread(get_bytes, key)
    await asyncio.to_thread(
        ingest_document,
        content=content,
        filename=filename,
        document_type=payload.get("document_type"),
        insurance_type=payload.get("insurance_type"),
        policy_number=payload.get("policy_number"),
        effective_from=payload.get("effective_from"),
        effective_to=payload.get("effective_to"),
        policy_version=payload.get("policy_version"),
        uploaded_by=str(payload.get("uploaded_by") or ""),
        tenant_id=tenant_id,
        jurisdiction=payload.get("jurisdiction"),
    )
    await asyncio.to_thread(delete_bytes, key)


HANDLERS = {
    "claim.assigned": handle_claim_event,
    "knowledge.ingest": handle_knowledge_ingest,
    "claim.status_changed": handle_claim_event,
}
