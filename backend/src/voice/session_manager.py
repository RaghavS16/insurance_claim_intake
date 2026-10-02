"""Lifecycle and concurrency manager for self-hosted Pipecat voice sessions."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

import redis.asyncio as redis

from src.config import settings
from src.database.models import Claim, VoiceSession
from src.database.session import SessionLocal
from src.utils.logger import app_logger
from src.voice.events import make_event

logger = app_logger


class VoiceEventStore:
    """Redis-backed event stream with local fan-out for single-process mode."""

    def __init__(self) -> None:
        self.redis = None
        if settings.REDIS_URL:
            try:
                self.redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
            except Exception:
                logger.exception("Voice Redis initialization failed")
        self._local_queues: dict[str, list[asyncio.Queue[str]]] = defaultdict(list)
        self._local_lock = asyncio.Lock()

    @staticmethod
    def _key(ticket_id: str) -> str:
        return f"voice:events:{ticket_id}"

    async def publish(self, ticket_id: str, event: dict[str, Any]) -> None:
        payload = json.dumps(event, default=str)
        if self.redis is not None:
            try:
                await self.redis.xadd(
                    self._key(ticket_id),
                    {"payload": payload},
                    maxlen=settings.VOICE_EVENT_STREAM_MAXLEN,
                    approximate=True,
                )
            except Exception:
                logger.exception("Failed to publish voice event to Redis.")
        async with self._local_lock:
            for queue in list(self._local_queues.get(ticket_id, [])):
                try:
                    queue.put_nowait(payload)
                except asyncio.QueueFull:
                    logger.warning("Dropping local voice event for %s", ticket_id)

    async def subscribe(self, websocket, ticket_id: str, last_event_id: Optional[str] = None) -> None:
        if self.redis is not None:
            cursor = last_event_id or "$"
            try:
                while True:
                    rows = await self.redis.xread(
                        {self._key(ticket_id): cursor},
                        count=50,
                        block=1000,
                    )
                    for _, messages in rows:
                        for stream_id, data in messages:
                            cursor = stream_id
                            payload = data.get("payload")
                            if payload:
                                await websocket.send_text(payload)
            except Exception:
                logger.debug("Redis voice subscriber ended for %s", ticket_id, exc_info=True)
            return

        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        async with self._local_lock:
            self._local_queues[ticket_id].append(queue)
        try:
            while True:
                await websocket.send_text(await queue.get())
        except Exception:
            logger.debug("Local voice subscriber ended for %s", ticket_id, exc_info=True)
        finally:
            async with self._local_lock:
                listeners = self._local_queues.get(ticket_id, [])
                if queue in listeners:
                    listeners.remove(queue)


class VoiceSessionManager:
    """Owns authenticated Pipecat workers and enforces one voice call per claim."""

    def __init__(self) -> None:
        self.events = VoiceEventStore()
        self._tasks: dict[str, asyncio.Task] = {}
        self._connections: dict[str, Any] = {}
        self._active_call_by_ticket: dict[str, str] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def safety_identifier(user_id: str) -> str:
        # Retained for compatibility with earlier callers; the local pipeline
        # does not transmit this value to any third-party provider.
        return hashlib.sha256(f"insureclaim:{user_id}".encode("utf-8")).hexdigest()

    async def start(
        self,
        *,
        call_id: str,
        ticket_id: str,
        user_id: str,
        model: str,
        tenant_id: str,
    ) -> bool:
        """Reserve a claim-scoped voice session and persist its lifecycle row."""
        if settings.VOICE_WORKER_DRAINING:
            return False
        worker_id = settings.VOICE_WORKER_ID
        async with self._lock:
            active = self._active_call_by_ticket.get(ticket_id)
            if active and active != call_id:
                return False

            if self.events.redis is not None:
                lock_key = f"voice:lock:{ticket_id}"
                acquired = await self.events.redis.set(
                    lock_key,
                    call_id,
                    nx=True,
                    ex=settings.MAX_VOICE_SESSION_SECONDS + 60,
                )
                if not acquired:
                    current = await self.events.redis.get(lock_key)
                    if current != call_id:
                        return False

            db = SessionLocal()
            try:
                claim = db.query(Claim).filter(
                    Claim.ticket_id == ticket_id,
                    Claim.tenant_id == tenant_id,
                ).first()
                if not claim:
                    await self._release_lock(ticket_id, call_id)
                    return False
                row = VoiceSession(
                    tenant_id=str(getattr(claim, "tenant_id", "") or ""),
                    call_id=call_id,
                    claim_id=str(claim.id),
                    user_id=str(user_id),
                    provider="pipecat_local",
                    model=model,
                    status="connecting",
                    started_at=datetime.now(timezone.utc),
                    worker_id=worker_id,
                    lease_expires_at=datetime.now(timezone.utc),
                )
                db.add(row)
                db.commit()
            except Exception:
                db.rollback()
                await self._release_lock(ticket_id, call_id)
                raise
            finally:
                db.close()

            self._active_call_by_ticket[ticket_id] = call_id
            if self.events.redis is not None:
                await self.events.redis.set(f"voice:active:{ticket_id}", call_id, ex=settings.MAX_VOICE_SESSION_SECONDS + 60)

        await self.events.publish(
            ticket_id,
            make_event(
                "voice.session.started",
                ticket_id,
                call_id=call_id,
                provider="pipecat_local",
                model=model,
                worker_id=worker_id,
            ),
        )
        return True

    async def active_call(self, ticket_id: str) -> str | None:
        if self.events.redis is not None:
            try:
                value = await self.events.redis.get(f"voice:active:{ticket_id}")
                if value:
                    return str(value)
            except Exception:
                logger.exception("Voice active-session lookup failed.")
        async with self._lock:
            return self._active_call_by_ticket.get(ticket_id)

    async def attach(
        self,
        *,
        call_id: str,
        ticket_id: str,
        user_id: str,
        connection: Any,
        tenant_id: str,
    ) -> None:
        """Attach a negotiated WebRTC connection to the reserved voice session."""
        async with self._lock:
            if self._active_call_by_ticket.get(ticket_id) != call_id:
                raise RuntimeError("Voice session is not active.")
            if call_id in self._tasks and not self._tasks[call_id].done():
                raise RuntimeError("Voice session is already attached.")

            db = SessionLocal()
            try:
                row = db.query(VoiceSession).filter(
                    VoiceSession.call_id == call_id,
                    VoiceSession.tenant_id == tenant_id,
                ).first()
                if not row or row.worker_id != settings.VOICE_WORKER_ID:
                    raise RuntimeError("Voice session belongs to another worker.")
            finally:
                db.close()

            self._connections[call_id] = connection
            task = asyncio.create_task(
                self._run(
                    call_id=call_id,
                    ticket_id=ticket_id,
                    user_id=user_id,
                    connection=connection,
                    tenant_id=tenant_id,
                ),
                name=f"pipecat-voice-{call_id}",
            )
            self._tasks[call_id] = task

    async def _run(
        self,
        *,
        call_id: str,
        ticket_id: str,
        user_id: str,
        connection: Any,
        tenant_id: str,
    ) -> None:
        from src.voice.pipecat import run_voice_pipeline

        db = SessionLocal()
        row: Optional[VoiceSession] = None
        started_at = datetime.now(timezone.utc)
        final_status = "closed"
        final_reason = "session_ended"

        try:
            row = db.query(VoiceSession).filter(VoiceSession.call_id == call_id).first()
            if row:
                row.status = "active"
                row.worker_id = settings.VOICE_WORKER_ID
                row.lease_expires_at = datetime.now(timezone.utc)
                db.commit()

            await asyncio.wait_for(
                run_voice_pipeline(
                    connection=connection,
                    ticket_id=ticket_id,
                    call_id=call_id,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    events=self.events,
                ),
                timeout=settings.MAX_VOICE_SESSION_SECONDS,
            )
        except asyncio.TimeoutError:
            final_status = "timeout"
            final_reason = "max_session_duration"
            logger.warning("Pipecat voice session timed out for %s", call_id)
        except asyncio.CancelledError:
            final_reason = "cancelled"
            raise
        except Exception as exc:
            final_status = "failed"
            final_reason = type(exc).__name__
            logger.exception("Pipecat voice session failed for %s", call_id)
            await self.events.publish(
                ticket_id,
                make_event(
                    "voice.error",
                    ticket_id,
                    call_id=call_id,
                    error_type=type(exc).__name__,
                ),
            )
        finally:
            if row is None:
                try:
                    row = db.query(VoiceSession).filter(VoiceSession.call_id == call_id).first()
                except Exception:
                    row = None

            if row:
                row.status = final_status
                row.close_reason = final_reason
                row.ended_at = datetime.now(timezone.utc)
                row.duration_seconds = max(
                    0,
                    int((row.ended_at - started_at).total_seconds()),
                )
                try:
                    db.commit()
                except Exception:
                    db.rollback()
                    logger.exception("Failed to finalize voice session %s", call_id)

            db.close()
            self._connections.pop(call_id, None)
            self._tasks.pop(call_id, None)
            if self._active_call_by_ticket.get(ticket_id) == call_id:
                self._active_call_by_ticket.pop(ticket_id, None)
            if self.events.redis is not None:
                try:
                    key = f"voice:active:{ticket_id}"
                    script = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"
                    await self.events.redis.eval(script, 1, key, call_id)
                except Exception:
                    logger.debug("Failed to clear distributed voice session registry.", exc_info=True)

            await self._release_lock(ticket_id, call_id)
            await self.events.publish(
                ticket_id,
                make_event(
                    "voice.session.ended",
                    ticket_id,
                    call_id=call_id,
                    status=final_status,
                    reason=final_reason,
                ),
            )

    async def heartbeat(self, *, ticket_id: str, call_id: str) -> bool:
        """Renew the distributed voice lease only when this process owns the fencing token."""
        if self.events.redis is None:
            return self._active_call_by_ticket.get(ticket_id) == call_id
        key = f"voice:lock:{ticket_id}"
        script = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('expire', KEYS[1], ARGV[2]) else return 0 end"
        result = await self.events.redis.eval(script, 1, key, call_id, str(settings.MAX_VOICE_SESSION_SECONDS + 60))
        if int(result or 0) != 1:
            return False
        await self.events.redis.set(f"voice:active:{ticket_id}", call_id, ex=settings.MAX_VOICE_SESSION_SECONDS + 60)
        db = SessionLocal()
        try:
            row = db.query(VoiceSession).filter(
                VoiceSession.call_id == call_id,
                VoiceSession.tenant_id.is_not(None),
            ).first()
            if row:
                row.lease_expires_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            db.rollback()
            logger.debug("Failed to persist voice lease heartbeat.", exc_info=True)
        finally:
            db.close()
        return True

    async def close(self, call_id: str) -> None:
        """Cancel the pipeline and tear down its WebRTC connection."""
        task = self._tasks.get(call_id)
        connection = self._connections.get(call_id)
        if task and not task.done():
            task.cancel()
        if connection is not None:
            try:
                await connection.disconnect()
            except Exception:
                logger.debug("Failed to disconnect WebRTC connection.", exc_info=True)

    async def _release_lock(self, ticket_id: str, call_id: str) -> None:
        if self.events.redis is None:
            return
        try:
            await self.events.redis.eval(
                "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",
                1,
                f"voice:lock:{ticket_id}",
                call_id,
            )
        except Exception:
            logger.debug("Failed to release voice Redis lock.", exc_info=True)


voice_session_manager = VoiceSessionManager()
