"""Lifecycle and concurrency manager for self-hosted Pipecat voice sessions."""
from __future__ import annotations

import asyncio
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import redis.asyncio as redis

from src.config import settings
from src.database.models import Claim, VoiceSession
from src.database.session import SessionLocal
from src.utils.logger import app_logger
from src.voice.events import make_event

logger = app_logger


class VoiceEventStore:
    """Application event fan-out with Redis Streams for shared deployments."""

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

    async def publish(self, ticket_id: str, event: Dict[str, Any]) -> None:
        payload = json.dumps(event, default=str)
        if self.redis is not None:
            try:
                await self.redis.xadd(
                    self._key(ticket_id),
                    {"payload": payload},
                    maxlen=1000,
                    approximate=True,
                )
            except Exception:
                logger.exception("Voice Redis publish failed for %s; using local fan-out", ticket_id)
        async with self._local_lock:
            for queue in list(self._local_queues.get(ticket_id, [])):
                try:
                    queue.put_nowait(payload)
                except asyncio.QueueFull:
                    pass

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
                            raw = data.get("payload")
                            if raw:
                                await websocket.send_text(raw)
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
                current = self._local_queues.get(ticket_id, [])
                if queue in current:
                    current.remove(queue)


class VoiceSessionManager:
    """Owns authenticated Pipecat sessions and WebRTC workers."""

    def __init__(self) -> None:
        self.events = VoiceEventStore()
        self._tasks: dict[str, asyncio.Task] = {}
        self._connections: dict[str, Any] = {}
        self._active_call_by_ticket: dict[str, str] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def safety_identifier(user_id: str) -> str:
        return hashlib.sha256(f"insureclaim:{user_id}".encode("utf-8")).hexdigest()

    async def start(self, *, call_id: str, ticket_id: str, user_id: str, model: str) -> bool:
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

            self._active_call_by_ticket[ticket_id] = call_id
            existing = self._tasks.get(call_id)
            if existing and not existing.done():
                return True

                self._tasks[call_id] = asyncio.create_task(
                self._run_pipecat(
                    call_id=call_id,
                    ticket_id=ticket_id,
                    user_id=user_id,
                    model=model,
                ),
                name=f"pipecat-voice-{call_id}",
            )

        try:

    async def close(self, call_id: str) -> None:
        task = self._tasks.get(call_id)
        connection = self._connections.get(call_id)
        if connection is not None:
            try:
            except Exception:
                logger.debug("Failed to request realtime session close", exc_info=True)
        if task and not task.done():
            task.cancel()

    async def _run_pipecat(self, *, call_id: str, ticket_id: str, user_id: str, model: str) -> None:
        db = SessionLocal()
        session_row: Optional[VoiceSession] = None
        final_status = "closed"
        final_reason = "session_ended"

        try:
            claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
            if not claim:
                raise RuntimeError("Claim not found")

            session_row = VoiceSession(
                call_id=call_id,
                claim_id=str(claim.id),
                user_id=str(user_id),
                provider="pipecat_local",
                model=model,
                status="connecting",
                started_at=datetime.now(timezone.utc),
            )
            db.add(session_row)
            db.commit()

            await self.events.publish(
                ticket_id,
                make_event(
                    "voice.session.started",
                    ticket_id,
                    call_id=call_id,
                    provider="openai_realtime",
                    model=model,
                ),
            )

            url = f"{settings.OPENAI_REALTIME_WS_URL}?call_id={call_id}"
            async with websockets.connect(
                url,
                additional_headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                max_size=16 * 1024 * 1024,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=5,
            ) as ws:
                self._connections[call_id] = ws
                session_row.status = "active"
                db.commit()
                self._ready_results[call_id] = True
                ready = self._ready_events.get(call_id)
                if ready:
                    ready.set()
                await self.events.publish(
                    ticket_id,
                    make_event("voice.session.ready", ticket_id, call_id=call_id),
                )

                deadline = time.monotonic() + settings.MAX_VOICE_SESSION_SECONDS
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        final_status = "timeout"
                        final_reason = "max_session_duration"
                        try:
                            await ws.send(json.dumps({"type": "session.close"}))
                        except Exception:
                            pass
                        break

                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                    except asyncio.TimeoutError:
                        final_status = "timeout"
                        final_reason = "max_session_duration"
                        try:
                            await ws.send(json.dumps({"type": "session.close"}))
                        except Exception:
                            pass
                        break

                    try:
                        event = json.loads(raw)
                    except (TypeError, json.JSONDecodeError):
                        continue
                    await self._handle_event(
                        ws=ws,
                        db=db,
                        ticket_id=ticket_id,
                        call_id=call_id,
                        event=event,
                    )

        except asyncio.CancelledError:
            final_status = "closed"
            final_reason = "cancelled"
            raise
        except Exception as exc:
                ready = self._ready_events.get(call_id)
            if ready:
                ready.set()
            final_status = "failed"
            final_reason = type(exc).__name__
            logger.exception("Pipecat voice session failed for %s", ticket_id)
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
            self._ready_results.setdefault(call_id, False)
            ready = self._ready_events.get(call_id)
            if ready:
                ready.set()
            self._connections.pop(call_id, None)
            self._mark_session(db, session_row, final_status, final_reason)
            db.close()
            if self.events.redis is not None:
                try:
                    await self.events.redis.eval(
                        "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",
                        1,
                        f"voice:lock:{ticket_id}",
                        call_id,
                    )
                except Exception:
                    logger.debug("Failed to release distributed voice lock for %s", ticket_id, exc_info=True)
            self._ready_events.pop(call_id, None)
            self._ready_results.pop(call_id, None)
            async with self._lock:
                if self._active_call_by_ticket.get(ticket_id) == call_id:
                    self._active_call_by_ticket.pop(ticket_id, None)
                self._tasks.pop(call_id, None)

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

    @staticmethod
    def _mark_session(db, session_row: Optional[VoiceSession], status: str, reason: str) -> None:
        if session_row is None:
            return
        try:
            session_row.status = status
            session_row.close_reason = reason
            session_row.ended_at = datetime.now(timezone.utc)
            if session_row.started_at:
                started = session_row.started_at
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                session_row.duration_seconds = max(
                    0,
                    int((session_row.ended_at - started).total_seconds()),
                )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to finalize voice session %s", session_row.call_id)


voice_session_manager = VoiceSessionManager()
