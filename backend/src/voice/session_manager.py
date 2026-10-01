"""Server-side sideband orchestration for managed realtime voice sessions."""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import redis.asyncio as redis
import websockets

from src.agents.turn_processor import process_claimant_turn
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
    """Owns the authenticated sideband connection and claim application processing."""

    def __init__(self) -> None:
        self.events = VoiceEventStore()
        self._tasks: dict[str, asyncio.Task] = {}
        self._connections: dict[str, Any] = {}
        self._active_call_by_ticket: dict[str, str] = {}
        self._processed_items: set[tuple[str, str]] = set()
        self._lock = asyncio.Lock()

    @staticmethod
    def safety_identifier(user_id: str) -> str:
        return hashlib.sha256(f"insureclaim:{user_id}".encode("utf-8")).hexdigest()

    async def start(self, *, call_id: str, ticket_id: str, user_id: str, model: str) -> bool:
        async with self._lock:
            active = self._active_call_by_ticket.get(ticket_id)
            if active and active != call_id:
                return False
            self._active_call_by_ticket[ticket_id] = call_id
            existing = self._tasks.get(call_id)
            if existing and not existing.done():
                return True
            self._tasks[call_id] = asyncio.create_task(
                self._run_sideband(
                    call_id=call_id,
                    ticket_id=ticket_id,
                    user_id=user_id,
                    model=model,
                ),
                name=f"voice-sideband-{call_id}",
            )
            return True

    async def close(self, call_id: str) -> None:
        task = self._tasks.get(call_id)
        connection = self._connections.get(call_id)
        if connection is not None:
            try:
                await connection.send(json.dumps({"type": "session.close"}))
            except Exception:
                logger.debug("Failed to request realtime session close", exc_info=True)
        if task and not task.done():
            task.cancel()

    async def _run_sideband(self, *, call_id: str, ticket_id: str, user_id: str, model: str) -> None:
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
                provider="openai_realtime",
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

                deadline = time.monotonic() + settings.MAX_VOICE_SESSION_SECONDS
                async for raw in ws:
                    if time.monotonic() >= deadline:
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
            final_status = "failed"
            final_reason = type(exc).__name__
            logger.exception("Realtime voice sideband failed for %s", ticket_id)
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
            self._connections.pop(call_id, None)
            self._mark_session(db, session_row, final_status, final_reason)
            db.close()
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

    async def _handle_event(self, *, ws: Any, db, ticket_id: str, call_id: str, event: Dict[str, Any]) -> None:
        event_type = str(event.get("type") or "")

        if event_type == "input_audio_buffer.speech_started":
            await self.events.publish(
                ticket_id,
                make_event("voice.state", ticket_id, call_id=call_id, state="listening"),
            )
            return

        if event_type == "input_audio_buffer.speech_stopped":
            await self.events.publish(
                ticket_id,
                make_event("voice.state", ticket_id, call_id=call_id, state="transcribing"),
            )
            return

        if event_type == "response.created":
            await self.events.publish(
                ticket_id,
                make_event("voice.state", ticket_id, call_id=call_id, state="speaking"),
            )
            return

        if event_type in {"response.done", "response.cancelled"}:
            await self.events.publish(
                ticket_id,
                make_event("voice.state", ticket_id, call_id=call_id, state="idle"),
            )
            return

        if event_type != "conversation.item.input_audio_transcription.completed":
            return

        item_id = str(event.get("item_id") or "")
        transcript = " ".join(str(event.get("transcript") or "").split()).strip()
        if not item_id or not transcript:
            return

        marker = (call_id, item_id)
        if marker in self._processed_items:
            return
        self._processed_items.add(marker)

        await self.events.publish(
            ticket_id,
            make_event(
                "voice.user.final",
                ticket_id,
                call_id=call_id,
                item_id=item_id,
                text=transcript,
            ),
        )
        await self.events.publish(
            ticket_id,
            make_event("voice.state", ticket_id, call_id=call_id, state="thinking"),
        )

        claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
        if not claim:
            await self._speak_exact(
                ws,
                "I couldn't find that claim session. Please return to the claim page and try again.",
            )
            return

        result = await process_claimant_turn(db, claim, transcript, "voice")

        await self.events.publish(
            ticket_id,
            make_event(
                "voice.claim.state",
                ticket_id,
                call_id=call_id,
                extracted_data=result.get("extracted_data", {}) or {},
                missing_fields=result.get("missing_fields", []) or [],
                field_status=result.get("field_status", {}) or {},
                awaiting_confirmation=bool(result.get("awaiting_confirmation")),
                confirmed=bool(result.get("confirmed")),
                status=result.get("status"),
                conversation_status=result.get("conversation_status"),
                conversation_phase=result.get("conversation_phase"),
                missing_evidence=result.get("missing_evidence", []) or [],
                evidence=result.get("evidence", []) or [],
                submission_readiness=result.get("submission_readiness", {}) or {},
            ),
        )

        response_text = str(result.get("next_question") or result.get("message") or "").strip()
        if not response_text:
            return

        await self.events.publish(
            ticket_id,
            make_event("voice.agent.final", ticket_id, call_id=call_id, text=response_text),
        )
        await self._speak_exact(ws, response_text)

    @staticmethod
    async def _speak_exact(ws: Any, text: str) -> None:
        await ws.send(
            json.dumps(
                {
                    "type": "response.create",
                    "response": {
                        "input": [],
                        "output_modalities": ["audio"],
                        "instructions": (
                            "Speak exactly the APPLICATION RESPONSE below. "
                            "Do not add, remove, reinterpret, or invent information. "
                            "Use a calm, concise customer-service delivery.\n\n"
                            f"APPLICATION RESPONSE:\n{text}"
                        ),
                    },
                }
            )
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
