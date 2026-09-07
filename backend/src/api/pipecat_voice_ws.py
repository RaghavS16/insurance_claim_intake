"""Pipecat-backed WebSocket endpoint for insurance claim conversations."""

from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.config import settings
from src.database.models import Claim
from src.database.session import SessionLocal
from src.utils.auth import verify_token
from src.utils.authorization import enforce_claim_ownership
from src.voice.pipecat import build_voice_pipeline, websocket_transport

from pipecat.pipeline.worker import PipelineWorker
from pipecat.workers.runner import WorkerRunner

router = APIRouter()


async def _authenticate_claim(websocket: WebSocket, ticket_id: str) -> Claim | None:
    """Authenticate the query-string bearer token and validate claim ownership."""
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="Authentication required")
        return None

    payload = verify_token(token)
    if not payload or not payload.get("sub"):
        await websocket.close(code=1008, reason="Invalid or expired token")
        return None

    db = SessionLocal()
    try:
        claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
        if not claim:
            await websocket.close(code=1008, reason="Claim not found")
            return None
        try:
            from src.database.models import User
            user = db.query(User).filter(User.id == payload["sub"]).first()
            if not user:
                await websocket.close(code=1008, reason="User not found")
                return None
            enforce_claim_ownership(claim, user)
        except Exception:
            await websocket.close(code=1008, reason="Claim access denied")
            return None
        return claim
    finally:
        db.expunge(claim) if claim is not None else None
        db.close()


@router.websocket("/api/v1/ws/voice/{ticket_id}")
async def pipecat_voice(websocket: WebSocket, ticket_id: str):
    """Run the claim voice session through Pipecat."""
    claim = await _authenticate_claim(websocket, ticket_id)
    if claim is None:
        return

    await websocket.accept()
    transport = websocket_transport(websocket)
    worker: PipelineWorker = build_voice_pipeline(
        transport,
        claim,
        stt_model=settings.STT_MODEL_SIZE,
        vad_aggressiveness=settings.VAD_AGGRESSIVENESS,
        piper_url=settings.PIPER_HTTP_URL,
        piper_voice=settings.PIPER_VOICE,
    )

    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    try:
        await runner.run()
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        raise
    except Exception:
        from src.utils.logger import app_logger
        app_logger.exception("Pipecat voice session failed for %s", ticket_id)
        try:
            await websocket.close(code=1011, reason="Voice session failed")
        except Exception:
            pass
    finally:
        try:
            await runner.cancel()
        except Exception:
            pass
