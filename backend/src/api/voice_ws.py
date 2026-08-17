"""
WebSocket endpoint for real-time voice claim conversation streaming.
One connection per claim session (ticket_id).

Protocol:
  Client -> Server: Binary PCM16 mono 16kHz audio chunks
  Client -> Server: Text JSON {"type": "end_session"}
  Server -> Client: Text JSON {"type": "transcript", "text": "..."}
  Server -> Client: Text JSON {"type": "state_update", "extracted_data": {...}, "missing_fields": [...], ...}
  Server -> Client: Binary WAV synthesized agent response audio
  Server -> Client: Text JSON {"type": "agent_text_fallback", "text": "..."} (when TTS unavailable)
  Server -> Client: Text JSON {"type": "error", "detail": "..."}
"""
import json
import logging
from typing import Any, Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from src.database.session import SessionLocal
from src.database.models import Claim, ConversationTurn
from src.agents.graph import build_conversation_graph
from src.voice.session import VoiceSession
from src.voice.stt import transcribe_pcm16
from src.voice.tts import synthesize, TTSError
from src.utils.logger import app_logger

logger = app_logger
router = APIRouter()


def _persist_turn(db: Session, claim: Claim, speaker: str, text: str, turn_number: int) -> None:
    """Persist conversation turn into database."""
    try:
        turn = ConversationTurn(
            claim_id=claim.id,
            turn_number=turn_number,
            speaker=speaker,
            text=text,
        )
        db.add(turn)
        db.commit()
    except Exception as exc:
        logger.warning("Failed to persist conversation turn: %s", exc)
        db.rollback()


async def _run_turn(db: Session, claim: Claim, voice_session: VoiceSession, user_text: str) -> Dict[str, Any]:
    """Run one conversation-graph turn, update claim record, and persist turn history."""
    prior_state = dict(getattr(claim, "pipeline_state", None) or {})
    turn_number = voice_session.next_turn()

    _persist_turn(db, claim, "user", user_text, turn_number)

    graph_input = {
        **prior_state,
        "claim_text": user_text,
        "ticket_id": claim.ticket_id,
        "input_mode": "voice",
    }

    graph = build_conversation_graph()
    result = graph.invoke(graph_input)

    setattr(claim, "pipeline_state", dict(result))
    setattr(claim, "conversation_status", result.get("conversation_status", "collecting"))
    setattr(claim, "claim_type", result.get("extracted_data", {}).get("claim_type"))
    setattr(claim, "description", result.get("extracted_data", {}).get("damage_description"))
    setattr(claim, "claimed_amount", result.get("extracted_data", {}).get("claimed_amount"))

    if result.get("extraction_confidence") is not None:
        setattr(claim, "extraction_confidence", float(result["extraction_confidence"]))

    try:
        db.commit()
    except Exception as exc:
        logger.warning("Failed to commit claim state update: %s", exc)
        db.rollback()

    agent_text = result.get("next_question", "")
    if agent_text:
        _persist_turn(db, claim, "agent", agent_text, turn_number)

    return result


async def _handle_utterance(websocket: WebSocket, db: Session, claim: Claim, voice_session: VoiceSession, pcm_bytes: bytes) -> None:
    """Process a single segmented audio utterance from claimant."""
    # Reset segmenter buffer to prevent reverberation feedback
    voice_session.segmenter._leftover = b""
    voice_session.segmenter._voiced_frames = []
    voice_session.segmenter._triggered = False

    text = transcribe_pcm16(pcm_bytes)
    if not text or len(text.strip()) < 2:
        return

    # Send claimant transcript back to client
    await websocket.send_json({"type": "transcript", "text": text})

    try:
        result = await _run_turn(db, claim, voice_session, text)
    except Exception:
        logger.exception("Conversation turn failed for claim %s", claim.ticket_id)
        await websocket.send_json({
            "type": "error",
            "detail": "We encountered an issue processing your response. Please try speaking again.",
        })
        return

    # Send updated structured claim state
    await websocket.send_json({
        "type": "state_update",
        "ticket_id": claim.ticket_id,
        "extracted_data": result.get("extracted_data", {}),
        "missing_fields": result.get("missing_fields", []),
        "field_status": result.get("field_status", {}),
        "conversation_status": result.get("conversation_status"),
        "awaiting_confirmation": result.get("awaiting_confirmation", False),
        "confirmed": result.get("confirmed", False),
        "agent_text": result.get("next_question", ""),
    })

    agent_text = result.get("next_question", "")
    if not agent_text:
        return

    # Synthesize audio or fall back to client text-to-speech
    try:
        audio_bytes = synthesize(agent_text)
        await websocket.send_bytes(audio_bytes)
    except TTSError:
        # Instruct client to speak fallback text via Web Speech API
        await websocket.send_json({"type": "agent_text_fallback", "text": agent_text})
    except Exception as exc:
        logger.warning("TTS synthesis error: %s. Sending fallback text event.", exc)
        await websocket.send_json({"type": "agent_text_fallback", "text": agent_text})


@router.websocket("/ws/claims/{ticket_id}/voice")
async def voice_conversation(websocket: WebSocket, ticket_id: str):
    """WebSocket endpoint for bidirectional audio streaming."""
    await websocket.accept()
    db = SessionLocal()

    try:
        claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
        if not claim:
            await websocket.send_json({"type": "error", "detail": "Claim ticket_id not found."})
            await websocket.close(code=4404)
            return

        voice_session = VoiceSession(ticket_id=ticket_id)

        while True:
            message = await websocket.receive()

            if "bytes" in message and message["bytes"] is not None:
                utterances = voice_session.segmenter.feed(message["bytes"])
                for pcm_bytes in utterances:
                    await _handle_utterance(websocket, db, claim, voice_session, pcm_bytes)

            elif "text" in message and message["text"] is not None:
                try:
                    payload = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue

                if payload.get("type") == "end_session":
                    leftover = voice_session.segmenter.flush()
                    if leftover:
                        await _handle_utterance(websocket, db, claim, voice_session, leftover)
                    break

    except WebSocketDisconnect:
        logger.info("Voice session %s disconnected cleanly.", ticket_id)
    except Exception:
        logger.exception("Voice session %s encountered an unexpected error.", ticket_id)
        try:
            await websocket.send_json({"type": "error", "detail": "Voice connection error. Please reconnect."})
        except Exception:
            pass
    finally:
        db.close()
