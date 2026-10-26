"""Database-backed outbox dispatcher. Run as a dedicated worker process."""
from __future__ import annotations
import asyncio
import os
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import select
from src.config import settings
from src.database.session import SessionLocal
from src.database.hardening_models import OutboxEvent
from src.utils.logger import app_logger
from src.services.outbox import mark_processed, mark_retry
from src.services.observability import record_outbox


def _claim_events_sync(limit: int = 25) -> list[tuple[str, str, OutboxEvent]]:
    """
    Atomically query and claim pending events under FOR UPDATE SKIP LOCKED.
    Marks rows as 'processing' and commits immediately so DB locks are NEVER
    held across external network I/O.
    """
    db = SessionLocal()
    try:
        stmt = (
            select(OutboxEvent)
            .where(
                OutboxEvent.status == "pending",
                OutboxEvent.next_attempt_at <= datetime.now(timezone.utc),
            )
            .order_by(OutboxEvent.created_at)
            .limit(limit)
        )
        if db.bind and db.bind.dialect.name == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True)
        rows = db.execute(stmt).scalars().all()
        claimed: list[tuple[str, str, OutboxEvent]] = []
        now = datetime.now(timezone.utc)
        for row in rows:
            row.status = "processing"
            row.locked_at = now
            claimed.append((str(row.id), str(row.event_type), row))
        db.commit()
        return claimed
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _complete_event_sync(
    event_id: str,
    outcome: str,
    error: Exception | None = None,
    dead_letter_reason: str | None = None,
) -> None:
    """Brief <5ms transaction to finalize an event state outside the worker lock."""
    db = SessionLocal()
    try:
        row = db.query(OutboxEvent).filter(OutboxEvent.id == event_id).first()
        if not row:
            return
        if outcome == "processed":
            mark_processed(row)
            record_outbox(outcome="processed")
        elif outcome == "retry":
            mark_retry(row, error or RuntimeError("Unknown outbox execution error"))
            record_outbox(outcome="retry")
        elif outcome == "dead_letter":
            row.status = "dead_letter"
            row.last_error = dead_letter_reason or "No handler registered"
            row.processed_at = datetime.now(timezone.utc)
            record_outbox(outcome="dead_letter")
        db.commit()
    except Exception:
        db.rollback()
        app_logger.exception("Failed to update outbox event %s status", event_id)
    finally:
        db.close()


async def dispatch_once(handlers: dict[str, object], limit: int = 25) -> int:
    """Dispatches a batch of outbox events without blocking Uvicorn's asyncio loop."""
    claimed = await asyncio.to_thread(_claim_events_sync, limit)
    if not claimed:
        return 0

    processed = 0
    for event_id, event_type, row in claimed:
        handler = handlers.get(event_type)
        if handler is None:
            await asyncio.to_thread(
                _complete_event_sync,
                event_id,
                "dead_letter",
                None,
                "No handler registered for event type",
            )
            continue
        try:
            result = handler(row)
            if asyncio.iscoroutine(result):
                await result
            else:
                await asyncio.to_thread(lambda: result)
            await asyncio.to_thread(_complete_event_sync, event_id, "processed")
            processed += 1
        except Exception as exc:
            app_logger.warning("Outbox handler failed for %s (%s): %s", event_type, event_id, exc)
            await asyncio.to_thread(_complete_event_sync, event_id, "retry", exc)

    return processed


def _touch_heartbeat(path: str | None = None) -> None:
    try:
        import tempfile
        import time
        from pathlib import Path
        heartbeat_path = path or os.path.join(tempfile.gettempdir(), "outbox_worker_heartbeat")
        p = Path(heartbeat_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(time.time()), encoding="utf-8")
    except Exception:
        pass


async def run_worker(handlers: dict[str, object], poll_seconds: float | None = None) -> None:
    interval = (
        poll_seconds
        if poll_seconds is not None
        else float(os.getenv("OUTBOX_POLL_INTERVAL_SECONDS", getattr(settings, "OUTBOX_POLL_INTERVAL_SECONDS", 15.0)))
    )
    while True:
        try:
            _touch_heartbeat()
            processed = await dispatch_once(handlers)
            if processed == 0:
                await asyncio.sleep(interval)
        except Exception:
            app_logger.exception("Outbox worker cycle failed")
            await asyncio.sleep(interval)


async def _main() -> None:
    from src.services.outbox_handlers import HANDLERS
    await run_worker(HANDLERS)


if __name__ == "__main__":
    asyncio.run(_main())
