"""Self-hosted Pipecat WebRTC signaling and authenticated voice events."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from src.api.deps import get_current_user
from src.config import settings
from src.database.models import Claim, User
from src.database.session import SessionLocal, get_db
from src.utils.production_security import authenticate_token
from src.utils.authorization import enforce_claim_ownership
from src.utils.logger import app_logger
from src.voice.pipecat import SmallWebRTCConnection
from src.voice.session_manager import voice_session_manager

router = APIRouter(prefix="/api/v1/voice", tags=["Voice"])
logger = app_logger


def _validate_claim_access(db: Session, ticket_id: str, user: User) -> Claim:
    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id, Claim.tenant_id == str(user.tenant_id or "")).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found.")
    try:
        enforce_claim_ownership(claim, user, db)
    except Exception as exc:
        raise HTTPException(status_code=403, detail="Claim access denied.") from exc
    return claim


@router.post("/realtime/session/{ticket_id}")
async def create_realtime_session(
    ticket_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reserve one claim-scoped self-hosted Pipecat voice session."""
    if not settings.VOICE_ENABLED or settings.VOICE_PROVIDER != "pipecat_local":
        raise HTTPException(status_code=503, detail="Voice channel is disabled.")
    _validate_claim_access(db, ticket_id, current_user)

    call_id = f"CALL-{uuid.uuid4().hex}"
    ok = await voice_session_manager.start(
        call_id=call_id,
        ticket_id=ticket_id,
        user_id=str(current_user.id),
        model=settings.VOICE_STT_MODEL,
    )
    if not ok:
        raise HTTPException(
            status_code=409,
            detail="A voice session is already active for this claim.",
        )

    return {
        "call_id": call_id,
        "ticket_id": ticket_id,
        "provider": "pipecat_local",
        "transport": "small_webrtc",
    }


@router.post("/realtime/offer/{call_id}")
async def create_realtime_offer(
    call_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Negotiate one browser WebRTC offer into a Pipecat Small WebRTC answer."""
    if not settings.VOICE_ENABLED or settings.VOICE_PROVIDER != "pipecat_local":
        raise HTTPException(status_code=503, detail="Voice channel is disabled.")

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > settings.MAX_VOICE_SDP_BYTES:
                raise HTTPException(status_code=413, detail="Voice session offer is too large.")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid voice session request.") from exc

    body = await request.json()
    ticket_id = str(body.get("ticket_id") or "").strip()
    offer_sdp = str(body.get("sdp") or "")
    offer_type = str(body.get("type") or "offer")

    if not ticket_id or not offer_sdp or len(offer_sdp.encode("utf-8")) > settings.MAX_VOICE_SDP_BYTES:
        raise HTTPException(status_code=400, detail="Invalid WebRTC offer.")
    if offer_type != "offer":
        raise HTTPException(status_code=400, detail="Only WebRTC offer SDP is accepted.")

    _validate_claim_access(db, ticket_id, current_user)
    active_call = await voice_session_manager.active_call(ticket_id)
    if active_call != call_id:
        raise HTTPException(status_code=409, detail="Voice session is not active.")

    connection = SmallWebRTCConnection(
        connection_timeout_secs=settings.VOICE_WEBRTC_CONNECTION_TIMEOUT_SECONDS,
    )
    try:
        await connection.initialize(sdp=offer_sdp, type=offer_type)
        answer = connection.get_answer()
        if not answer:
            raise HTTPException(status_code=502, detail="Pipecat could not create a WebRTC answer.")

        await voice_session_manager.attach(
            call_id=call_id,
            ticket_id=ticket_id,
            user_id=str(current_user.id),
            connection=connection,
        )
        return {
            "sdp": answer["sdp"],
            "type": answer["type"],
            "pc_id": answer.get("pc_id"),
            "provider": "pipecat_local",
            "transport": "small_webrtc",
        }
    except HTTPException:
        await connection.disconnect()
        raise
    except Exception as exc:
        await connection.disconnect()
        await voice_session_manager.close(call_id)
        logger.exception("Pipecat WebRTC negotiation failed.")
        raise HTTPException(
            status_code=502,
            detail="Voice connection could not be established.",
        ) from exc


@router.websocket("/events/{ticket_id}")
async def voice_events(websocket: WebSocket, ticket_id: str):
    """Authenticated claim-scoped application event stream; media stays WebRTC-only."""
    origin = websocket.headers.get("origin")
    if origin and origin not in settings.allowed_origins_list:
        await websocket.close(code=1008, reason="Origin not allowed")
        return
    await websocket.accept()
    try:
        raw = await websocket.receive_text()
        message = json.loads(raw)
        if message.get("type") != "auth":
            await websocket.close(code=1008, reason="Authentication required")
            return

        token = str(message.get("token") or "")
        db = SessionLocal()
        try:
            try:
                user = authenticate_token(token, db)
            except HTTPException:
                await websocket.close(code=1008, reason="Invalid or expired token")
                return
            _validate_claim_access(db, ticket_id, user)
        finally:
            db.close()

        await websocket.send_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "event_id": "connection-ready",
                    "event_type": "voice.events.ready",
                    "ticket_id": ticket_id,
                }
            )
        )
        last_event_id = str(message.get("last_event_id") or "") or None
        await voice_session_manager.events.subscribe(websocket, ticket_id, last_event_id=last_event_id)
    except WebSocketDisconnect:
        return
    except Exception:
        logger.debug("Voice event socket ended for %s", ticket_id, exc_info=True)
        try:
            await websocket.close(code=1011, reason="Voice event channel failed")
        except Exception:
            pass


@router.post("/heartbeat/{ticket_id}/{call_id}")
async def voice_heartbeat(ticket_id: str, call_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _validate_claim_access(db, ticket_id, current_user)
    active = await voice_session_manager.active_call(ticket_id)
    if active != call_id:
        raise HTTPException(status_code=409, detail="Voice session ownership has changed.")
    renewed = await voice_session_manager.heartbeat(ticket_id=ticket_id, call_id=call_id)
    if not renewed:
        raise HTTPException(status_code=409, detail="Voice session lease expired or is owned by another worker.")
    return {"call_id": call_id, "lease_renewed": True}

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
    return {"status": "closed"}
