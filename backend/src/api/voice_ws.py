"""
WebSocket endpoint for real-time voice claim conversation streaming.
One connection per claim session (ticket_id).

Architecture
============

The WebSocket receive loop NEVER blocks on STT, LLM, or TTS. It only:
  1. Reads incoming binary audio frames and puts them into an asyncio.Queue.
  2. Reads incoming JSON control messages (end_session).
  3. Forwards outgoing messages prepared by background workers.

Two asyncio background tasks run concurrently:

  ClaimantASRWorker
    Drains the audio_queue → feeds SpeechEndpointDetector → runs StreamingASRBuffer
    → emits partial transcript events (not sent to LLM) → on endpoint, finalizes
    transcript → puts finalized text into the conversation_queue.

  ConversationWorker
    Drains the conversation_queue → runs LangGraph conversation turn → sends
    agent_transcript event (directly from LLM text, no ASR) → synthesizes TTS →
    sends audio bytes → sets echo-suppression window on VoiceSession.

Both workers communicate back to the WebSocket by putting messages into an
outbound_queue. A single send_loop task drains outbound_queue and sends to client.

Protocol
========
  Client → Server: Binary PCM16 mono 16kHz audio chunks
  Client → Server: Text JSON {"type": "end_session"}
  Server → Client: Text JSON {"type": "transcript", "speaker": "claimant",
                               "segment_id": "claimant-N", "sequence": N,
                               "text": "...", "is_final": false, ...}
  Server → Client: Text JSON {"type": "transcript", "speaker": "agent",
                               "segment_id": "agent-N", "sequence": N,
                               "text": "...", "is_final": true, ...}
  Server → Client: Text JSON {"type": "state_update", ...}
  Server → Client: Binary  WAV synthesized agent response audio
  Server → Client: Text JSON {"type": "agent_text_fallback", "text": "..."}
  Server → Client: Text JSON {"type": "error", "detail": "..."}
  Server → Client: Text JSON {"type": "session_end"}
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from src.database.session import SessionLocal
from src.database.models import Claim, ConversationTurn
from src.agents.graph import build_conversation_graph
from src.voice.session import VoiceSession
from src.voice.vad import SpeechEndpointDetector
from src.voice.stt import StreamingASRBuffer
from src.voice.tts import synthesize, TTSError
from src.voice.normalizer import normalize_transcript
from src.utils.logger import app_logger

logger = app_logger
router = APIRouter()

# Maximum items in queues before applying backpressure
_AUDIO_QUEUE_MAX = 200
_CONV_QUEUE_MAX = 20
_OUTBOUND_QUEUE_MAX = 100


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _persist_turn(db: Session, claim: Claim, speaker: str, text: str, turn_number: int) -> None:
    """Persist one conversation turn. Non-fatal on failure."""
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
    """
    Run one conversation-graph turn in a thread pool (non-blocking from event loop),
    update claim record, and persist turn history.
    """
    prior_state = dict(getattr(claim, "pipeline_state", None) or {})
    turn_number = voice_session.next_turn()

    # Persist claimant turn (sync DB call — run in thread)
    await asyncio.get_event_loop().run_in_executor(
        None, _persist_turn, db, claim, "user", user_text, turn_number
    )

    graph_input = {
        **prior_state,
        "claim_text": user_text,
        "ticket_id": claim.ticket_id,
        "input_mode": "voice",
    }

    # Run LangGraph in thread to avoid blocking the event loop
    graph = build_conversation_graph()
    result = await asyncio.get_event_loop().run_in_executor(None, lambda: graph.invoke(graph_input))

    setattr(claim, "pipeline_state", dict(result))
    setattr(claim, "conversation_status", result.get("conversation_status", "collecting"))
    setattr(claim, "claim_type", result.get("extracted_data", {}).get("claim_type"))
    setattr(claim, "description", result.get("extracted_data", {}).get("damage_description"))
    setattr(claim, "claimed_amount", result.get("extracted_data", {}).get("claimed_amount"))

    if result.get("extraction_confidence") is not None:
        setattr(claim, "extraction_confidence", float(result["extraction_confidence"]))

    def _commit():
        try:
            db.commit()
        except Exception as exc:
            logger.warning("Failed to commit claim state update: %s", exc)
            db.rollback()

    await asyncio.get_event_loop().run_in_executor(None, _commit)

    agent_text = result.get("next_question", "")
    if agent_text:
        await asyncio.get_event_loop().run_in_executor(
            None, _persist_turn, db, claim, "agent", agent_text, turn_number
        )

    return result


# ---------------------------------------------------------------------------
# Background worker: Claimant ASR
# ---------------------------------------------------------------------------

async def _claimant_asr_worker(
    audio_queue: asyncio.Queue,
    conversation_queue: asyncio.Queue,
    outbound_queue: asyncio.Queue,
    voice_session: VoiceSession,
    stop_event: asyncio.Event,
    partial_interval_s: float,
) -> None:
    """
    Drains audio_queue → feeds SpeechEndpointDetector → produces partial + final transcripts.

    Partial transcripts:
      - Emitted at most once every `partial_interval_s` seconds while speech is active.
      - Sent to outbound_queue with is_final=False.
      - Do NOT go to the conversation pipeline.

    Final transcripts (on speech endpoint):
      - Emitted once per utterance when silence is detected.
      - Sent to outbound_queue with is_final=True.
      - Also placed in conversation_queue for LLM processing.

    Echo suppression:
      - While voice_session.is_echo_suppressed() is True, audio is discarded.
        This prevents agent TTS played through the speaker from being transcribed.
    """
    detector = SpeechEndpointDetector()
    asr_buffer = StreamingASRBuffer()
    last_partial_time = 0.0
    current_segment_id: Optional[str] = None
    current_sequence: Optional[int] = None
    current_start_ts: Optional[float] = None

    async def _send_partial(text: str, confidence: float) -> None:
        nonlocal last_partial_time
        if not text:
            return
        await outbound_queue.put({
            "json": {
                "type": "transcript",
                "speaker": "claimant",
                "segment_id": current_segment_id,
                "sequence": current_sequence,
                "text": text,
                "is_final": False,
                "confidence": round(confidence, 3),
                "start_ts": current_start_ts,
            }
        })
        last_partial_time = time.monotonic()

    async def _send_final(text: str, confidence: float) -> None:
        await outbound_queue.put({
            "json": {
                "type": "transcript",
                "speaker": "claimant",
                "segment_id": current_segment_id,
                "sequence": current_sequence,
                "text": text,
                "is_final": True,
                "confidence": round(confidence, 3),
                "start_ts": current_start_ts,
                "end_ts": time.time(),
            }
        })

    while not stop_event.is_set():
        try:
            chunk = await asyncio.wait_for(audio_queue.get(), timeout=0.1)
        except asyncio.TimeoutError:
            # No audio — check if we have in-progress speech for a partial
            if detector.is_in_speech and current_segment_id and (time.monotonic() - last_partial_time) >= partial_interval_s:
                partial_audio = detector.peek_partial()
                if partial_audio:
                    asr_buffer.push(b"")  # signal the rate-limit check
                    text, conf = await asyncio.get_event_loop().run_in_executor(
                        None, asr_buffer.force_partial
                    )
                    await _send_partial(text, conf)
            continue

        audio_queue.task_done()

        # Discard audio while echo-suppression window is active
        if voice_session.is_echo_suppressed():
            logger.debug("ASR: discarding %d bytes (echo-suppression active)", len(chunk))
            continue

        # Feed to VAD endpoint detector
        events = detector.feed(chunk)
        # Push to ASR buffer regardless of VAD events (continuous ASR)
        if detector.is_in_speech:
            if current_segment_id is None:
                # New utterance started — allocate a segment ID
                current_segment_id, current_sequence = voice_session.next_claimant_segment_id()
                current_start_ts = time.time()
                asr_buffer.reset()
                last_partial_time = 0.0
            asr_buffer.push(chunk)

            # Rate-limited partial transcription
            now = time.monotonic()
            if (now - last_partial_time) >= partial_interval_s:
                text, conf = await asyncio.get_event_loop().run_in_executor(
                    None, asr_buffer.partial
                )
                if text:
                    await _send_partial(text, conf)

        for _audio, is_endpoint in events:
            if is_endpoint:
                # Final transcription of the completed utterance
                text, conf = await asyncio.get_event_loop().run_in_executor(
                    None, asr_buffer.finalize
                )
                if text and text.strip():
                    # Normalize for claim extraction (raw goes to UI, normalized to LLM)
                    normalized = await asyncio.get_event_loop().run_in_executor(
                        None, normalize_transcript, text
                    )
                    await _send_final(text, conf)
                    # Only finalized transcripts trigger LLM
                    await conversation_queue.put({
                        "text": normalized if normalized else text,
                        "raw_text": text,
                        "segment_id": current_segment_id,
                        "sequence": current_sequence,
                    })
                    logger.info("ASR final: segment=%s text=%r", current_segment_id, text)
                elif current_segment_id:
                    # Silence-only segment — send final with empty text to dismiss partial
                    await _send_final("", 0.0)

                # Reset for next utterance
                current_segment_id = None
                current_sequence = None
                current_start_ts = None
                asr_buffer.reset()
                last_partial_time = 0.0

    # On stop: flush any in-progress audio
    if detector.is_in_speech and current_segment_id:
        leftover = detector.flush()
        if leftover:
            asr_buffer.push(leftover)
        text, conf = await asyncio.get_event_loop().run_in_executor(
            None, asr_buffer.finalize
        )
        if text and text.strip():
            normalized = await asyncio.get_event_loop().run_in_executor(
                None, normalize_transcript, text
            )
            await _send_final(text, conf)
            await conversation_queue.put({
                "text": normalized if normalized else text,
                "raw_text": text,
                "segment_id": current_segment_id,
                "sequence": current_sequence,
            })


# ---------------------------------------------------------------------------
# Background worker: Conversation (LLM + TTS)
# ---------------------------------------------------------------------------

async def _conversation_worker(
    conversation_queue: asyncio.Queue,
    outbound_queue: asyncio.Queue,
    db: Session,
    claim: Claim,
    voice_session: VoiceSession,
    stop_event: asyncio.Event,
) -> None:
    """
    Drains conversation_queue → runs LangGraph turn → emits agent transcript + TTS.

    Agent transcript is produced DIRECTLY from LLM-generated text — NO ASR is run on
    agent speech. This guarantees the claimant transcript can never contain agent text
    and vice versa.

    After sending TTS audio, suppresses echo for an estimated duration based on
    audio length. The ClaimantASRWorker will discard mic input during this window.
    """
    while not stop_event.is_set():
        try:
            item = await asyncio.wait_for(conversation_queue.get(), timeout=0.2)
        except asyncio.TimeoutError:
            continue

        conversation_queue.task_done()
        user_text: str = item["text"]

        try:
            result = await _run_turn(db, claim, voice_session, user_text)
        except Exception:
            logger.exception("Conversation turn failed for claim %s", claim.ticket_id)
            await outbound_queue.put({
                "json": {
                    "type": "error",
                    "detail": "We encountered an issue processing your response. Please try speaking again.",
                }
            })
            continue

        # State update
        await outbound_queue.put({
            "json": {
                "type": "state_update",
                "ticket_id": claim.ticket_id,
                "extracted_data": result.get("extracted_data", {}),
                "missing_fields": result.get("missing_fields", []),
                "field_status": result.get("field_status", {}),
                "conversation_status": result.get("conversation_status"),
                "awaiting_confirmation": result.get("awaiting_confirmation", False),
                "confirmed": result.get("confirmed", False),
                "agent_text": result.get("next_question", ""),
            }
        })

        agent_text = result.get("next_question", "")
        if not agent_text:
            continue

        # Agent transcript — emitted directly from LLM text, not from ASR
        seg_id, seq = voice_session.next_agent_segment_id()
        await outbound_queue.put({
            "json": {
                "type": "transcript",
                "speaker": "agent",
                "segment_id": seg_id,
                "sequence": seq,
                "text": agent_text,
                "is_final": True,
                "confidence": 1.0,
                "start_ts": time.time(),
                "end_ts": time.time(),
            }
        })

        # TTS synthesis — run in thread to avoid blocking event loop
        try:
            audio_bytes = await asyncio.get_event_loop().run_in_executor(None, synthesize, agent_text)

            # Estimate TTS playback duration: WAV is typically 22050Hz, 2 bytes/sample, mono
            # wav_header = 44 bytes; rest is PCM data
            pcm_bytes_count = max(0, len(audio_bytes) - 44)
            tts_duration_s = pcm_bytes_count / (22050 * 2) + 0.5  # +0.5s margin

            # Suppress echo for the estimated playback duration
            voice_session.suppress_echo_for(tts_duration_s)
            logger.debug("Echo suppression: %.1fs for agent turn %s", tts_duration_s, seg_id)

            await outbound_queue.put({"bytes": audio_bytes})
        except TTSError:
            # TTS unavailable — fall back to client-side Web Speech API
            await outbound_queue.put({
                "json": {"type": "agent_text_fallback", "text": agent_text}
            })
            # Still suppress for a reasonable duration (estimate ~100ms per 15 chars)
            est_duration = max(2.0, len(agent_text) / 15 * 0.1) + 0.5
            voice_session.suppress_echo_for(est_duration)
        except Exception as exc:
            logger.warning("TTS synthesis error: %s. Sending fallback text event.", exc)
            await outbound_queue.put({
                "json": {"type": "agent_text_fallback", "text": agent_text}
            })
            est_duration = max(2.0, len(agent_text) / 15 * 0.1) + 0.5
            voice_session.suppress_echo_for(est_duration)


# ---------------------------------------------------------------------------
# Outbound send loop
# ---------------------------------------------------------------------------

async def _send_loop(
    websocket: WebSocket,
    outbound_queue: asyncio.Queue,
    stop_event: asyncio.Event,
) -> None:
    """
    Drains outbound_queue and sends messages to the WebSocket client.
    Serializes all sends so no concurrent write contention occurs.
    """
    while not stop_event.is_set() or not outbound_queue.empty():
        try:
            item = await asyncio.wait_for(outbound_queue.get(), timeout=0.1)
        except asyncio.TimeoutError:
            continue

        outbound_queue.task_done()
        try:
            if "json" in item:
                await websocket.send_json(item["json"])
            elif "bytes" in item:
                await websocket.send_bytes(item["bytes"])
        except Exception as exc:
            logger.debug("Send failed (client may have disconnected): %s", exc)
            break


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@router.websocket("/ws/claims/{ticket_id}/voice")
async def voice_conversation(websocket: WebSocket, ticket_id: str):
    """
    WebSocket endpoint for bidirectional audio streaming.

    The receive loop is non-blocking:
      - Binary frames are placed into audio_queue immediately.
      - JSON control messages are processed immediately.
      - STT, LLM, and TTS are handled by background worker tasks.
    """
    await websocket.accept()
    db = SessionLocal()
    stop_event = asyncio.Event()

    try:
        claim = db.query(Claim).filter(Claim.ticket_id == ticket_id).first()
        if not claim:
            await websocket.send_json({"type": "error", "detail": "Claim ticket_id not found."})
            await websocket.close(code=4404)
            return

        voice_session = VoiceSession(ticket_id=ticket_id)

        audio_queue: asyncio.Queue = asyncio.Queue(maxsize=_AUDIO_QUEUE_MAX)
        conversation_queue: asyncio.Queue = asyncio.Queue(maxsize=_CONV_QUEUE_MAX)
        outbound_queue: asyncio.Queue = asyncio.Queue(maxsize=_OUTBOUND_QUEUE_MAX)

        partial_interval_s = 0.4  # minimum seconds between partial transcript events

        # Launch background workers
        asr_task = asyncio.create_task(
            _claimant_asr_worker(
                audio_queue, conversation_queue, outbound_queue,
                voice_session, stop_event, partial_interval_s
            ),
            name=f"asr-{ticket_id}",
        )
        conv_task = asyncio.create_task(
            _conversation_worker(
                conversation_queue, outbound_queue,
                db, claim, voice_session, stop_event
            ),
            name=f"conv-{ticket_id}",
        )
        send_task = asyncio.create_task(
            _send_loop(websocket, outbound_queue, stop_event),
            name=f"send-{ticket_id}",
        )

        logger.info("Voice session started: %s", ticket_id)

        try:
            while True:
                message = await websocket.receive()

                if "bytes" in message and message["bytes"] is not None:
                    chunk = message["bytes"]
                    # Non-blocking put — if queue is full, log and discard rather than block
                    try:
                        audio_queue.put_nowait(chunk)
                    except asyncio.QueueFull:
                        logger.warning("Audio queue full for %s — dropping %d bytes", ticket_id, len(chunk))

                elif "text" in message and message["text"] is not None:
                    try:
                        payload = json.loads(message["text"])
                    except json.JSONDecodeError:
                        continue

                    if payload.get("type") == "end_session":
                        logger.info("Client requested end_session for %s", ticket_id)
                        break

                    # Additional control: client can signal that it started playing TTS
                    # This provides an extra echo suppression hint from the client side.
                    elif payload.get("type") == "tts_playing":
                        duration = float(payload.get("duration_s", 3.0))
                        voice_session.suppress_echo_for(duration)

                    # Client signals it stopped playing (claimant interrupted)
                    elif payload.get("type") == "tts_stopped":
                        voice_session.clear_echo_suppression()

        except WebSocketDisconnect:
            logger.info("Voice session %s disconnected cleanly.", ticket_id)
        except Exception:
            logger.exception("Voice session %s encountered an unexpected error.", ticket_id)
            try:
                await websocket.send_json({"type": "error", "detail": "Voice connection error. Please reconnect."})
            except Exception:
                pass
        finally:
            stop_event.set()

        # Wait for workers to finish gracefully (with timeout)
        try:
            await asyncio.wait_for(
                asyncio.gather(asr_task, conv_task, send_task, return_exceptions=True),
                timeout=5.0,
            )
        except asyncio.TimeoutError:
            logger.warning("Workers for %s did not stop within timeout — cancelling.", ticket_id)
            for task in (asr_task, conv_task, send_task):
                task.cancel()

        await outbound_queue.put({"json": {"type": "session_end"}})
        logger.info("Voice session ended: %s", ticket_id)

    finally:
        db.close()
