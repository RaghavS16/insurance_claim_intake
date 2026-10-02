"""Transactional outbox service and worker primitives."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.database.hardening_models import OutboxEvent

def enqueue(db: Session, *, event_type: str, aggregate_type: str, aggregate_id: str, payload: dict[str,Any], idempotency_key: str) -> OutboxEvent:
    existing=db.execute(select(OutboxEvent).where(OutboxEvent.idempotency_key==idempotency_key)).scalar_one_or_none()
    if existing: return existing
    tenant_id = None
    if aggregate_type == "claim":
        try:
            from src.database.models import Claim
            tenant_id = db.execute(select(Claim.tenant_id).where(Claim.id == aggregate_id)).scalar_one_or_none()
        except Exception:
            tenant_id = None
    row=OutboxEvent(tenant_id=tenant_id,event_type=event_type,aggregate_type=aggregate_type,aggregate_id=aggregate_id,payload_json=payload,idempotency_key=idempotency_key,status="pending",next_attempt_at=datetime.now(timezone.utc))
    db.add(row)
    return row

def retry_delay(attempts:int)->int:
    return min(300, 2 ** min(max(attempts,0), 8))

def mark_retry(row:OutboxEvent,error:Exception)->None:
    row.attempts=int(row.attempts or 0)+1
    row.status="pending"
    row.next_attempt_at=datetime.now(timezone.utc)+timedelta(seconds=retry_delay(row.attempts))
    row.last_error=type(error).__name__+":"+str(error)[:1000]

def mark_processed(row:OutboxEvent)->None:
    row.status="processed"
    row.processed_at=datetime.now(timezone.utc)
    row.last_error=None

Handler=Callable[[dict[str,Any]], Awaitable[None] | None]
