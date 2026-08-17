"""
WebSocket endpoint for real-time voice claim conversation streaming.
One connection per claim session (ticket_id).

Decoupled Ingestion & Inference Architecture
===========================================

1. Ingestion Worker (_claimant_audio_ingester):
   - Non-blocking: drains `audio_queue` frame-by-frame.
   - Runs WebRTC VAD to track claimant speech onset (barge-in) and silence endpoint.
   - Decoupled from Whisper: puts audio chunks and control triggers into `asr_inference_queue`.
   - Preemption: On claimant speech onset during TTS playback, it immediately clears echo
     suppression, cancels `active_turn_task`, drains all queues, increments `generation_id`,
     and sends a `"barge_in"` event to the frontend.

2. ASR Inference Worker (_asr_inference_worker):
   - Drains `asr_inference_queue` sequentially.
   - Whisper runs in a thread pool (`run_in_executor`) on small rolling windows (<3s) to reduce latency.
   - Filters out stale events by checking `generation_id`.
   - Sends partial transcripts reconciled via overlap matching and puts final transcripts into `conversation_queue`.

3. Conversation Worker (_conversation_worker):
   - Drains `conversation_queue`.
   - Launches a sub-task (`_process_turn_task`) to run LLM (LangGraph) and TTS, saving a reference
     to `active_turn_task` so it can be preemptively cancelled.
   - Filters out stale responses using `generation_id` versioning before writing to outbound queue.

Protocol
========
  Client → Server: Binary PCM16 mono 16kHz audio chunks
  Client → Server: Text JSON {"type": "end_session"}
  Client → Server: Text JSON {"type": "tts_started"} / {"type": "tts_stopped"}
  Server → Client: Text JSON {"type": "barge_in", "global_seq": N, "timestamp": T}
  Server → Client: Text JSON {"type": "transcript", "speaker": "claimant",
                               "segment_id": "claimant-N", "sequence": N,
                               "text": "...", "is_final": false, "global_seq": G, "timestamp": T}
  Server → Client: Text JSON {"type": "state_update", ...}
  Server → Client: Binary WAV synthesized agent response audio
  Server → Client: Text JSON {"type": "agent_text_fallback", "text": "...", "generation_id": G}
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
# Background worker: Claimant Audio Ingester (VAD + Ingestion)
# ---------------------------------------------------------------------------

async def _claimant_audio_ingester(
    audio_queue: asyncio.Queue,
    asr_inference_queue: asyncio.Queue,
    conversation_queue: asyncio.Queue,
    outbound_queue: asyncio.Queue,
    voice_session: VoiceSession,
    session_context: dict,
    stop_event: asyncio.Event,
    partial_interval_s: float,
) -> None:
    """
    Ingests audio, runs VAD frame-by-frame, and manages preemption/barge-in commands.
    This task never blocks on Whisper, keeping VAD execution extremely low-latency.
    """
    detector = SpeechEndpointDetector()
    last_partial_time = 0.0
    current_segment_id: Optional[str] = None
    current_sequence: Optional[int] = None
    current_start_ts: Optional[float] = None

    while not stop_event.is_set():
        try:
            chunk = await asyncio.wait_for(audio_queue.get(), timeout=0.1)
        except asyncio.TimeoutError:
            # Trigger a partial ASR request if speaking and time window elapsed
            if detector.is_in_speech and current_segment_id and (time.monotonic() - last_partial_time) >= partial_interval_s:
                await asr_inference_queue.put({
                    "type": "partial_trigger",
                    "generation_id": voice_session.generation_id
                })
                last_partial_time = time.monotonic()
            continue

        audio_queue.task_done()

        # Run VAD on incoming chunk. We process this even during TTS to support barge-in.
        was_in_speech = detector.is_in_speech
        events = detector.feed(chunk)
        is_in_speech = detector.is_in_speech

        # Barge-in Detection: transition from silent/listening to speech onset
        if is_in_speech and not was_in_speech:
            # 1. Increment generation version to void active/queued runs
            gen_id = voice_session.increment_generation()
            
            # 2. Preemptively cancel active turn task
            active_task = session_context.get("active_turn_task")
            if active_task and not active_task.done():
                active_task.cancel()
                logger.info("Barge-in: cancelled active turn task for generation_id %d", gen_id)
            
            # 3. Drain conversation queue
            while not conversation_queue.empty():
                try:
                    conversation_queue.get_nowait()
                    conversation_queue.task_done()
                except asyncio.QueueEmpty:
                    break

            # 4. Drain ASR inference queue
            while not asr_inference_queue.empty():
                try:
                    asr_inference_queue.get_nowait()
                    asr_inference_queue.task_done()
                except asyncio.QueueEmpty:
                    break

            # 5. Clear echo suppression window
            voice_session.clear_echo_suppression()

            # 6. Send barge_in notification to client immediately
            await outbound_queue.put({
                "json": {
                    "type": "barge_in",
                    "global_seq": voice_session.next_global_sequence(),
                    "timestamp": time.time()
                }
            })

            # 7. Start new claimant segment
            current_segment_id, current_sequence = voice_session.next_claimant_segment_id()
            current_start_ts = time.time()
            last_partial_time = 0.0

            # 8. Reset ASR buffer on the inference worker
            await asr_inference_queue.put({
                "type": "reset",
                "segment_id": current_segment_id,
                "sequence": current_sequence,
                "start_ts": current_start_ts,
                "generation_id": gen_id
            })

        # Append audio data to the ASR inference worker's buffer if speaking
        if is_in_speech:
            await asr_inference_queue.put({
                "type": "chunk",
                "audio": chunk,
                "generation_id": voice_session.generation_id
            })

            # Check if we should trigger a partial Whisper run
            now = time.monotonic()
            if (now - last_partial_time) >= partial_interval_s:
                await asr_inference_queue.put({
                    "type": "partial_trigger",
                    "generation_id": voice_session.generation_id
                })
                last_partial_time = now

        for _audio, is_endpoint in events:
            if is_endpoint:
                # Trigger final ASR transcription for the completed utterance
                await asr_inference_queue.put({
                    "type": "final_trigger",
                    "generation_id": voice_session.generation_id
                })
                current_segment_id = None
                current_sequence = None
                current_start_ts = None
                last_partial_time = 0.0

    # On stop event, flush remaining audio
    if detector.is_in_speech:
        leftover = detector.flush()
        if leftover:
            await asr_inference_queue.put({
                "type": "chunk",
                "audio": leftover,
                "generation_id": voice_session.generation_id
            })
        await asr_inference_queue.put({
            "type": "final_trigger",
            "generation_id": voice_session.generation_id
        })


# ---------------------------------------------------------------------------
# Background worker: ASR Inference (Whisper)
# ---------------------------------------------------------------------------

async def _asr_inference_worker(
    asr_inference_queue: asyncio.Queue,
    conversation_queue: asyncio.Queue,
    outbound_queue: asyncio.Queue,
    voice_session: VoiceSession,
    stop_event: asyncio.Event,
) -> None:
    """
    Drains asr_inference_queue and runs Whisper transcription in a thread pool.
    Filters out stale/preempted requests using generation_id checks.
    """
    asr_buffer = StreamingASRBuffer()
    current_segment_id: Optional[str] = None
    current_sequence: Optional[int] = None
    current_start_ts: Optional[float] = None

    async def _send_partial(text: str, confidence: float) -> None:
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
                "global_seq": voice_session.next_global_sequence(),
                "timestamp": time.time()
            }
        })

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
                "global_seq": voice_session.next_global_sequence(),
                "timestamp": time.time()
            }
        })

    while not stop_event.is_set():
        try:
            item = await asyncio.wait_for(asr_inference_queue.get(), timeout=0.2)
        except asyncio.TimeoutError:
            continue

        asr_inference_queue.task_done()

        # Check generation version: discard stale items instantly
        if item.get("generation_id") != voice_session.generation_id:
            logger.debug("ASR worker: discarding stale queue item of type %s", item.get("type"))
            continue

        msg_type = item["type"]

        if msg_type == "reset":
            current_segment_id = item["segment_id"]
            current_sequence = item["sequence"]
            current_start_ts = item["start_ts"]
            asr_buffer.reset()

        elif msg_type == "chunk":
            asr_buffer.push(item["audio"])

        elif msg_type == "partial_trigger":
            if current_segment_id:
                text, conf = await asyncio.get_event_loop().run_in_executor(
                    None, asr_buffer.partial
                )
                if text:
                    await _send_partial(text, conf)

        elif msg_type == "final_trigger":
            if current_segment_id:
                text, conf = await asyncio.get_event_loop().run_in_executor(
                    None, asr_buffer.finalize
                )
                if text and text.strip():
                    normalized = await asyncio.get_event_loop().run_in_executor(
                        None, normalize_transcript, text
                    )
                    await _send_final(text, conf)
                    # Trigger LLM conversation worker
                    await conversation_queue.put({
                        "text": normalized if normalized else text,
                        "raw_text": text,
                        "segment_id": current_segment_id,
                        "sequence": current_sequence,
                        "generation_id": voice_session.generation_id
                    })
                    logger.info("ASR final (decoupled): segment=%s text=%r", current_segment_id, text)
                else:
                    await _send_final("", 0.0)

            current_segment_id = None
            current_sequence = None
            current_start_ts = None
            asr_buffer.reset()


# ---------------------------------------------------------------------------
# Background worker: Conversation Coordinator
# ---------------------------------------------------------------------------

async def _conversation_worker(
    conversation_queue: asyncio.Queue,
    outbound_queue: asyncio.Queue,
    db: Session,
    claim: Claim,
    voice_session: VoiceSession,
    session_context: dict,
    stop_event: asyncio.Event,
) -> None:
    """
    Drains conversation_queue. Delegates turn processing to a sub-task,
    allowing clean preemption/cancellation on barge-in.
    """
    while not stop_event.is_set():
        try:
            item = await asyncio.wait_for(conversation_queue.get(), timeout=0.2)
        except asyncio.TimeoutError:
            continue

        conversation_queue.task_done()

        # Check generation version
        if item.get("generation_id") != voice_session.generation_id:
            logger.debug("Conversation: ignoring stale turn item")
            continue

        # Run turn processing inside a cancellable task
        turn_task = asyncio.create_task(_process_turn_task(
            db, claim, voice_session, item["text"], item["segment_id"],
            item["generation_id"], outbound_queue
        ))
        session_context["active_turn_task"] = turn_task

        try:
            await turn_task
        except asyncio.CancelledError:
            logger.info("Conversation: turn task cancelled for generation_id %d", item["generation_id"])
        finally:
            if session_context.get("active_turn_task") == turn_task:
                session_context["active_turn_task"] = None


async def _process_turn_task(
    db: Session,
    claim: Claim,
    voice_session: VoiceSession,
    user_text: str,
    segment_id: str,
    generation_id: int,
    outbound_queue: asyncio.Queue,
) -> None:
    """Process a single turn task, updating state and running TTS."""
    try:
        result = await _run_turn(db, claim, voice_session, user_text)
    except Exception:
        logger.exception("Conversation turn failed for claim %s", claim.ticket_id)
        if generation_id == voice_session.generation_id:
            await outbound_queue.put({
                "json": {
                    "type": "error",
                    "detail": "We encountered an issue processing your response. Please try speaking again.",
                }
            })
        return

    # Check generation again after LLM completes
    if generation_id != voice_session.generation_id:
        return

    # Put state update to outbound queue
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
        return

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
            "global_seq": voice_session.next_global_sequence(),
            "timestamp": time.time()
        }
    })

    # Synthesize speech
    try:
        audio_bytes = await asyncio.get_event_loop().run_in_executor(None, synthesize, agent_text)
        
        # Check generation again before queuing audio bytes
        if generation_id != voice_session.generation_id:
            return

        await outbound_queue.put({
            "bytes": audio_bytes,
            "generation_id": generation_id
        })
    except Exception as exc:
        logger.warning("TTS synthesis error: %s. Sending fallback text event.", exc)
        await outbound_queue.put({
            "json": {
                "type": "agent_text_fallback",
                "text": agent_text,
                "generation_id": generation_id
            }
        })


# ---------------------------------------------------------------------------
# Outbound send loop
# ---------------------------------------------------------------------------

async def _send_loop(
    websocket: WebSocket,
    outbound_queue: asyncio.Queue,
    voice_session: VoiceSession,
    stop_event: asyncio.Event,
) -> None:
    """
    Drains outbound_queue and sends messages to the WebSocket client.
    Serializes all sends and drops stale messages (outdated generation_id).
    """
    while not stop_event.is_set() or not outbound_queue.empty():
        try:
            item = await asyncio.wait_for(outbound_queue.get(), timeout=0.1)
        except asyncio.TimeoutError:
            continue

        outbound_queue.task_done()

        # Drop stale messages from previous cancelled generations
        if "generation_id" in item and item["generation_id"] != voice_session.generation_id:
            logger.debug("Send loop: discarding stale payload for generation %s", item["generation_id"])
            continue

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
    Decoupled queue worker pattern prevents any STT/LLM/TTS latency from blocking audio ingestion.
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
        asr_inference_queue: asyncio.Queue = asyncio.Queue(maxsize=_AUDIO_QUEUE_MAX)
        conversation_queue: asyncio.Queue = asyncio.Queue(maxsize=_CONV_QUEUE_MAX)
        outbound_queue: asyncio.Queue = asyncio.Queue(maxsize=_OUTBOUND_QUEUE_MAX)

        # Context to share mutable state (like active turn task) between workers
        session_context = {"active_turn_task": None}
        partial_interval_s = 0.4  # minimum seconds between partial transcript events

        # Launch decoupled background workers
        ingest_task = asyncio.create_task(
            _claimant_audio_ingester(
                audio_queue, asr_inference_queue, conversation_queue, outbound_queue,
                voice_session, session_context, stop_event, partial_interval_s
            ),
            name=f"ingest-{ticket_id}",
        )
        asr_task = asyncio.create_task(
            _asr_inference_worker(
                asr_inference_queue, conversation_queue, outbound_queue,
                voice_session, stop_event
            ),
            name=f"asr-{ticket_id}",
        )
        conv_task = asyncio.create_task(
            _conversation_worker(
                conversation_queue, outbound_queue,
                db, claim, voice_session, session_context, stop_event
            ),
            name=f"conv-{ticket_id}",
        )
        send_task = asyncio.create_task(
            _send_loop(websocket, outbound_queue, voice_session, stop_event),
            name=f"send-{ticket_id}",
        )

        logger.info("Voice session started: %s", ticket_id)

        try:
            while True:
                message = await websocket.receive()

                if "bytes" in message and message["bytes"] is not None:
                    chunk = message["bytes"]
                    try:
                        audio_queue.put_nowait(chunk)
                    except asyncio.QueueFull:
                        logger.warning("Audio queue full for %s — dropping %d bytes", ticket_id, len(chunk))

                elif "text" in message and message["text"] is not None:
                    try:
                        payload = json.loads(message["text"])
                    except json.JSONDecodeError:
                        continue

                    msg_type = payload.get("type")

                    if msg_type == "end_session":
                        logger.info("Client requested end_session for %s", ticket_id)
                        break

                    # Precise control: client signals that TTS playback has physically started
                    elif msg_type == "tts_started":
                        # Suppress VAD trigger of TTS playback echo.
                        # Disabling is cleared explicitly when tts_stopped is sent,
                        # or on barge-in speech onset.
                        voice_session.suppress_echo_for(1800.0)  # 30-min safety timeout

                    # Precise control: client signals that TTS playback finished or stopped
                    elif msg_type == "tts_stopped":
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

        # Wait for workers to finish gracefully
        try:
            await asyncio.wait_for(
                asyncio.gather(ingest_task, asr_task, conv_task, send_task, return_exceptions=True),
                timeout=5.0,
            )
        except asyncio.TimeoutError:
            logger.warning("Workers for %s did not stop within timeout — cancelling.", ticket_id)
            for task in (ingest_task, asr_task, conv_task, send_task):
                task.cancel()

        await outbound_queue.put({"json": {"type": "session_end"}})
        logger.info("Voice session ended: %s", ticket_id)

    finally:
        db.close()
