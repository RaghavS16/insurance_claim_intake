"""Single-process outbox worker; run multiple replicas safely with row locking on PostgreSQL."""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Callable
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.database.hardening_models import OutboxEvent
from src.services.outbox import mark_processed, mark_retry

log = logging.getLogger(__name__)
Handler = Callable[[OutboxEvent], None]


def dispatch_once(session: Session, handlers: dict[str, Handler], limit: int = 25) -> int:
    now = datetime.now(timezone.utc)
    q = (select(OutboxEvent).where(OutboxEvent.status == "pending", OutboxEvent.next_attempt_at <= now)
         .order_by(OutboxEvent.created_at).limit(limit).with_for_update(skip_locked=True))
    events = list(session.scalars(q))
    count = 0
    for event in events:
        handler = handlers.get(event.event_type)
        if handler is None:
            mark_retry(session, event, f"No handler registered for {event.event_type}")
            continue
        try:
            handler(event)
            mark_processed(event)
            count += 1
        except Exception as exc:
            log.exception("Outbox event failed: %s", event.id)
            mark_retry(session, event, str(exc))
    session.commit()
    return count
