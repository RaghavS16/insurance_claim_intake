"""Database-backed outbox dispatcher. Run as a dedicated worker process."""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from src.database.session import SessionLocal
from src.database.hardening_models import OutboxEvent
from src.utils.logger import app_logger
from src.services.outbox import mark_processed, mark_retry
from src.services.observability import record_outbox

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
                record_outbox(outcome="dead_letter")
                row.last_error="No handler registered for event type"
                row.processed_at=datetime.now(timezone.utc)
                continue
            try:
                result=handler(row)
                if asyncio.iscoroutine(result):
                    await result
                mark_processed(row)
                record_outbox(outcome="processed")
                processed += 1
            except Exception as exc:
                mark_retry(row, exc)
                record_outbox(outcome="retry")
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
            processed = await dispatch_once(handlers)
            if processed == 0:
                await asyncio.sleep(poll_seconds)
        except Exception:
            app_logger.exception("Outbox worker cycle failed")
            await asyncio.sleep(poll_seconds)


async def _main() -> None:
    from src.services.outbox_handlers import HANDLERS
    await run_worker(HANDLERS)


if __name__ == "__main__":
    asyncio.run(_main())
