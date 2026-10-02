"""Durable outbox primitives; callers must enqueue in the same DB transaction as state changes."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.database.hardening_models import OutboxEvent


def enqueue(session: Session, *, event_type: str, aggregate_type: str, aggregate_id: str,
            payload: dict[str, Any], idempotency_key: str) -> OutboxEvent:
    """Add an event to the current transaction; do not commit here."""
    existing = session.scalar(select(OutboxEvent).where(OutboxEvent.idempotency_key == idempotency_key))
    if existing:
        return existing
    event = OutboxEvent(id=str(uuid.uuid4()), event_type=event_type,
                        aggregate_type=aggregate_type, aggregate_id=aggregate_id,
                        payload_json=payload, idempotency_key=idempotency_key)
    session.add(event)
    session.flush()
    return event


def retry_delay(attempts: int) -> timedelta:
    """Bounded exponential backoff for durable worker retries."""
    return timedelta(seconds=min(300, 2 ** min(max(attempts, 0), 8)))


def mark_retry(session: Session, event: OutboxEvent, error: str) -> None:
    event.attempts += 1
    event.status = "pending"
    event.last_error = error[:4000]
    event.next_attempt_at = datetime.now(timezone.utc) + retry_delay(event.attempts)


def mark_processed(event: OutboxEvent) -> None:
    event.status = "processed"
    event.processed_at = datetime.now(timezone.utc)
