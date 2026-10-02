"""Database-backed outbox dispatcher. Run as a dedicated worker process."""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from src.database.session import SessionLocal
from src.database.hardening_models import OutboxEvent
from src.services.outbox import mark_processed, mark_retry

async def dispatch_once(handlers: dict[str, object], limit: int = 25) -> int:
    db=SessionLocal()
    try:
        rows=db.execute(
            select(OutboxEvent)
            .where(OutboxEvent.status=="pending", OutboxEvent.next_attempt_at <= datetime.now(timezone.utc))
            .order_by(OutboxEvent.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).scalars().all()
        processed=0
        for row in rows:
            handler=handlers.get(row.event_type)
            if handler is None:
                row.status="dead_letter"
                row.last_error="No handler registered for event type"
                row.processed_at=datetime.now(timezone.utc)
                continue
            try:
                result=handler(row.payload_json)
                if asyncio.iscoroutine(result):
                    await result
                mark_processed(row)
                processed += 1
            except Exception as exc:
                mark_retry(row, exc)
        db.commit()
        return processed
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

async def run_worker(handlers: dict[str, object], poll_seconds: float = 1.0) -> None:
    while True:
        try:
            await dispatch_once(handlers)
        except Exception:
            # The worker remains alive; individual events are retried transactionally.
            pass
        await asyncio.sleep(poll_seconds)

if __name__ == "__main__":
    async def _main() -> None:
        await run_worker({})
    asyncio.run(_main())
