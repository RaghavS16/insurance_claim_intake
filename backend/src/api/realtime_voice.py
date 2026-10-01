"""Managed realtime voice channel: WebRTC media + authenticated application events."""
from __future__ import annotations

import json
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.deps import get_current_user
from src.config import settings
from src.database.models import Claim, User
from src.database.session import SessionLocal, get_db
from src.utils.auth import verify_token
from src.utils.authorization import enforce_claim_ownership
from src.utils.logger import app_logger
from src.voice.session_manager import voice_session_manager

router = APIRouter(prefix="/api/v1/voice", tags=["Voice"])
logger = app_logger


class VoiceAttachRequest(BaseModel):
    call_id: str = Field(min_length=4, max_length=200)


def _validate_claim_access(db: Session, ticket_id: str, user: User) -> Claim:
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found.")
    try:
        enforce_claim_ownership(claim, user)
    except Exception as exc:
        raise HTTPException(status_code=403, detail="Claim access denied.") from exc
    return claim


def _session_config() -> dict:
    return {
        "type": "realtime",
        "model": settings.OPENAI_REALTIME_MODEL,
        "output_modalities": ["audio"],
        "max_output_tokens": settings.OPENAI_REALTIME_MAX_OUTPUT_TOKENS,
        "instructions": (
            "You are the voice transport for an insurance claim application. "
            "Do not independently answer insurance coverage, claim status, document, or submission questions. "
            "The application server processes completed claimant turns and sends the authoritative response to speak. "
            "Do not invent claim facts or business outcomes."
        ),
        "audio": {
            "input": {
                "turn_detection": {
                    "type": settings.OPENAI_REALTIME_TURN_DETECTION,
                    "eagerness": settings.OPENAI_REALTIME_VAD_EAGERNESS,
                    "create_response": False,
                    "interrupt_response": True,
                }
            },
            "output": {
                "voice": settings.OPENAI_REALTIME_VOICE,
            },
        },
    }


@router.post("/realtime/session/{ticket_id}")
async def create_realtime_session(
    ticket_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Exchange browser SDP for a managed Realtime session using the server API key."""
    if not settings.VOICE_ENABLED or settings.VOICE_PROVIDER != "openai_realtime":
        raise HTTPException(status_code=503, detail="Voice channel is disabled.")
    if not settings.OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="Realtime voice is not configured.")
    _validate_claim_access(db, ticket_id, current_user)

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > settings.MAX_VOICE_SDP_BYTES:
                raise HTTPException(status_code=413, detail="Voice session offer is too large.")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid voice session request.") from exc

    offer_sdp = await request.body()
    if not offer_sdp or len(offer_sdp) > settings.MAX_VOICE_SDP_BYTES:
        raise HTTPException(status_code=400, detail="Invalid WebRTC offer.")

    files = {
        "sdp": ("offer.sdp", offer_sdp, "application/sdp"),
        "session": (
            None,
            json.dumps(_session_config(), separators=(",", ":")),
            "application/json",
        ),
    }
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "OpenAI-Safety-Identifier": voice_session_manager.safety_identifier(str(current_user.id)),
        "X-Client-Request-Id": str(uuid.uuid4()),
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0)) as client:
            provider_response = await client.post(
                settings.OPENAI_REALTIME_CALLS_URL,
                files=files,
                headers=headers,
            )
    except httpx.HTTPError as exc:
        logger.exception("Realtime session request failed")
        raise HTTPException(status_code=502, detail="Voice provider is temporarily unavailable.") from exc

    if provider_response.status_code >= 400:
        logger.warning(
            "Realtime session creation rejected: %s %s",
            provider_response.status_code,
            provider_response.text[:500],
        )
        raise HTTPException(status_code=502, detail="Voice provider could not create a session.")

    location = provider_response.headers.get("Location", "")
    call_id = location.rstrip("/").split("/")[-1]
    if not call_id:
        raise HTTPException(status_code=502, detail="Voice provider did not return a call identifier.")

    started = await voice_session_manager.start(
        call_id=call_id,
        ticket_id=ticket_id,
        user_id=str(current_user.id),
        model=settings.OPENAI_REALTIME_MODEL,
    )
    if not started:
        raise HTTPException(status_code=409, detail="A voice session is already active for this claim.")

    return Response(
        content=provider_response.text,
        media_type="application/sdp",
        headers={
            "X-Voice-Call-Id": call_id,
            "Cache-Control": "no-store",
        },
    )


@router.websocket("/events/{ticket_id}")
async def voice_events(websocket: WebSocket, ticket_id: str):
    """Authenticated application state stream; no audio is transported here."""
    await websocket.accept()
    try:
        raw = await websocket.receive_text()
        message = json.loads(raw)
        if message.get("type") != "auth":
            await websocket.close(code=1008, reason="Authentication required")
            return

        token = str(message.get("token") or "")
        payload = verify_token(token)
        if not payload or not payload.get("sub"):
            await websocket.close(code=1008, reason="Invalid or expired token")
            return

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == payload["sub"]).first()
            if not user:
                await websocket.close(code=1008, reason="User not found")
                return
            _validate_claim_access(db, ticket_id, user)
        finally:
            db.close()

        await websocket.send_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "event_id": "connection-ready",
                    "event_type": "voice.events.ready",
                    "ticket_id": ticket_id,
                }
            )
        )
        await voice_session_manager.events.subscribe(websocket, ticket_id)
    except WebSocketDisconnect:
        return
    except Exception:
        logger.debug("Voice event socket ended for %s", ticket_id, exc_info=True)
        try:
            await websocket.close(code=1011, reason="Voice event channel failed")
        except Exception:
            pass


@router.post("/close/{ticket_id}")
async def close_voice_session(
    ticket_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _validate_claim_access(db, ticket_id, current_user)
    active = voice_session_manager._active_call_by_ticket.get(ticket_id)
    if active:
        await voice_session_manager.close(active)
    return JSONResponse({"status": "closed"})
