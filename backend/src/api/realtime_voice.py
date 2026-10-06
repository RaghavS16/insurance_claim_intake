"""Self-hosted Pipecat WebRTC signaling and authenticated voice events."""

from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.api.deps import get_current_user
from src.config import settings
from src.database.models import Claim, User, VoiceSession
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

    active_call = await voice_session_manager.active_call(ticket_id)
    if active_call:
        try:
            await voice_session_manager.close(active_call)
            await asyncio.sleep(0.05)
        except Exception:
            pass

    call_id = f"CALL-{uuid.uuid4().hex}"
    ok = await voice_session_manager.start(
        call_id=call_id,
        ticket_id=ticket_id,
        user_id=str(current_user.id),
        model=settings.VOICE_STT_MODEL,
        tenant_id=str(current_user.tenant_id or ""),
    )
    if not ok:
        raise HTTPException(
            status_code=409,
            detail="A voice session is already active for this claim.",
        )

    ice_servers = []
    for url in settings.voice_ice_servers_list:
        if url.startswith(("turn:", "turns:")):
            if settings.TURN_USERNAME and settings.TURN_PASSWORD:
                ice_servers.append({
                    "urls": url,
                    "username": settings.TURN_USERNAME,
                    "credential": settings.TURN_PASSWORD,
                })
        else:
            ice_servers.append({"urls": url})
    if not ice_servers:
        ice_servers = [{"urls": "stun:stun.l.google.com:19302"}]

    response = JSONResponse({
        "call_id": call_id,
        "ticket_id": ticket_id,
        "provider": "pipecat_local",
        "transport": "small_webrtc",
        "worker_id": voice_session_manager.worker_id(),
        "ice_servers": ice_servers,
    })
    response.set_cookie(
        settings.VOICE_STICKY_COOKIE_NAME,
        voice_session_manager.worker_id(),
        httponly=True,
        secure=settings.ENVIRONMENT in {"production", "staging"},
        samesite="lax",
        max_age=settings.MAX_VOICE_SESSION_SECONDS + 60,
    )
    return response


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
    session_row = db.query(VoiceSession).filter(
        VoiceSession.call_id == call_id,
        VoiceSession.tenant_id == str(current_user.tenant_id or ""),
    ).first()
    if not session_row:
        raise HTTPException(status_code=404, detail="Voice session not found.")
    
    current_worker = voice_session_manager.worker_id()
    if session_row.worker_id != current_worker:
        session_row.worker_id = current_worker
        db.commit()

    active_call = await voice_session_manager.active_call(ticket_id)
    if active_call != call_id:
        # Re-associate active call in memory if needed
        async with voice_session_manager._lock:
            voice_session_manager._active_call_by_ticket[ticket_id] = call_id

    pipecat_ice = [s for s in settings.voice_ice_servers_list if s] or ["stun:stun.l.google.com:19302"]
    connection = SmallWebRTCConnection(
        ice_servers=pipecat_ice,
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
            tenant_id=str(current_user.tenant_id or ""),
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


@router.post("/turn/{ticket_id}")
async def voice_process_turn(
    ticket_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fallback & direct voice turn processor: runs claim agent, publishes live stream events, returns assistant voice reply."""
    claim = _validate_claim_access(db, ticket_id, current_user)
    body = await request.json()
    user_text = str(body.get("text") or "").strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="Voice text is required.")

    from src.agents.turn_processor import process_claimant_turn
    from src.voice.events import make_event

    turn_count = int(body.get("turn_count") or 1)
    await voice_session_manager.events.publish(
        ticket_id,
        make_event("voice.user.final", ticket_id, text=user_text),
    )
    await voice_session_manager.events.publish(
        ticket_id,
        make_event("voice.state", ticket_id, state="thinking"),
    )

    result = await process_claimant_turn(
        db,
        claim,
        user_text,
        "voice",
        turn_count,
    )
    agent_reply = result.get("agent_reply") or "I have processed your claim details."

    await voice_session_manager.events.publish(
        ticket_id,
        make_event(
            "voice.agent.final",
            ticket_id,
            text=agent_reply,
            citations=result.get("citations", []),
            grounded=result.get("grounded", False),
        ),
    )
    await voice_session_manager.events.publish(
        ticket_id,
        make_event("voice.state", ticket_id, state="speaking"),
    )

    return {
        "text": agent_reply,
        "citations": result.get("citations", []),
        "extracted_data": result.get("extracted_data", {}),
        "missing_fields": result.get("missing_fields", []),
        "status": claim.status,
    }


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
    active = await voice_session_manager.active_call(ticket_id)
    if active:
        row = db.query(VoiceSession).filter(
            VoiceSession.call_id == active,
            VoiceSession.tenant_id == str(current_user.tenant_id or ""),
        ).first()
        if row and row.worker_id != voice_session_manager.worker_id() and row.worker_id != settings.VOICE_WORKER_ID:
            row.worker_id = voice_session_manager.worker_id()
            db.commit()
        await voice_session_manager.close(active)
    return {"status": "closed"}
