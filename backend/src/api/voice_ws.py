"""
WebSocket endpoint for streaming voice conversation. One connection per
claim session (ticket_id). Client streams raw PCM16 mono 16kHz audio chunks
(any size); server VAD-segments into utterances, transcribes, runs the
conversation graph, synthesizes the reply, and streams audio + a JSON event
back on the same socket.

Protocol (binary frames = audio, text frames = JSON control/status events):
  Client -> Server: binary PCM16 chunks
  Client -> Server: text {"type": "end_session"}
  Server -> Client: text {"type": "transcript", "text": "..."}
  Server -> Client: text {"type": "state_update", "extracted_data": {...}, "missing_fields": [...]}
  Server -> Client: binary  (synthesized WAV audio of the agent's reply)
  Server -> Client: text {"type": "error", "detail": "..."}
"""
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from src.database.session import SessionLocal
from src.database.models import Claim, ConversationTurn
from src.agents.graph import build_conversation_graph
from src.voice.session import VoiceSession
from src.voice.stt import transcribe_pcm16
from src.voice.tts import synthesize, TTSError

logger = logging.getLogger(__name__)
router = APIRouter()


def _persist_turn(db: Session, claim: Claim, speaker: str, text: str, turn_number: int) -> None:
    db.add(ConversationTurn(claim_id=claim.id, turn_number=turn_number, speaker=speaker, text=text))
    db.commit()


async def _run_turn(db: Session, claim: Claim, voice_session: VoiceSession, user_text: str) -> dict:
    """Run one conversation-graph turn and persist state + transcript."""
    prior_state = dict(getattr(claim, "pipeline_state", None) or {})
    turn_number = voice_session.next_turn()

    _persist_turn(db, claim, "user", user_text, turn_number)

    graph_input = {
        **prior_state,
        "claim_text": user_text,
        "ticket_id": claim.ticket_id,
    }

    graph = build_conversation_graph()
    result = graph.invoke(graph_input)

    setattr(claim, "pipeline_state", dict(result))
    setattr(claim, "conversation_status", result.get("conversation_status", "in_progress"))
    setattr(claim, "claim_type", result.get("extracted_data", {}).get("claim_type"))
    db.commit()

    agent_text = result.get("next_question", "")
    if agent_text:
        _persist_turn(db, claim, "agent", agent_text, turn_number)

    return result


@router.websocket("/ws/claims/{ticket_id}/voice")
async def voice_conversation(websocket: WebSocket, ticket_id: str):
    await websocket.accept()
    db = SessionLocal()

    claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
    if not claim:
        await websocket.send_json({"type": "error", "detail": "ticket_id not found"})
        await websocket.close(code=4404)
        db.close()
        return

    voice_session = VoiceSession(ticket_id=ticket_id)

    try:
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
        logger.info("Voice session %s disconnected", ticket_id)
    except Exception:
        logger.exception("Voice session %s crashed", ticket_id)
        try:
            await websocket.send_json({"type": "error", "detail": "Internal error. Please try again."})
        except Exception:
            pass
    finally:
        db.close()


async def _handle_utterance(websocket, db, claim, voice_session, pcm_bytes: bytes) -> None:
    # Clear trailing audio buffer to avoid processing reverberation
    voice_session.segmenter._leftover = b""
    voice_session.segmenter._voiced_frames = []
    voice_session.segmenter._triggered = False

    text = transcribe_pcm16(pcm_bytes)

    if not text or len(text.strip()) < 2:
        # Ignore ambient silence/breathing without interrupting the user
        return

    await websocket.send_json({"type": "transcript", "text": text})

    try:
        result = await _run_turn(db, claim, voice_session, text)
    except Exception:
        logger.exception("Conversation turn failed for claim %s", claim.ticket_id)
        await websocket.send_json({
            "type": "error",
            "detail": "Something went wrong processing that. Please try again.",
        })
        return

    await websocket.send_json({
        "type": "state_update",
        "extracted_data": result.get("extracted_data", {}),
        "missing_fields": result.get("missing_fields", []),
        "missing_documents": result.get("missing_documents", []),
        "conversation_status": result.get("conversation_status"),
    })

    agent_text = result.get("next_question", "")
    if not agent_text:
        return

    try:
        audio_bytes = synthesize(agent_text)
        await websocket.send_bytes(audio_bytes)
    except TTSError:
        # Browser client speaks the fallback text via Web Speech API
        await websocket.send_json({"type": "agent_text_fallback", "text": agent_text})

