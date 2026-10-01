"""Self-hosted Pipecat voice pipeline for claimant claim intake.

Pipecat owns realtime media, local STT/TTS orchestration, interruptions and
transport lifecycle. The existing claim agent remains authoritative for every
insurance business action.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import aiohttp
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import TextFrame, TranscriptionFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.piper.tts import PiperHttpTTSService
from pipecat.services.whisper.stt import WhisperSTTService
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

from src.agents.turn_processor import process_claimant_turn
from src.config import settings
from src.database.models import Claim
from src.database.session import SessionLocal
from src.utils.logger import app_logger
from src.voice.events import make_event

logger = app_logger


class ClaimVoiceProcessor(FrameProcessor):
    """Convert final local-STT turns into authoritative claim-agent replies."""

    def __init__(self, *, ticket_id: str, call_id: str, user_id: str, events: Any) -> None:
        super().__init__()
        self.ticket_id = ticket_id
        self.call_id = call_id
        self.user_id = user_id
        self.events = events
        self._turn_lock = asyncio.Lock()
        self._turn_count = 0

    async def _publish(self, event_type: str, **payload: Any) -> None:
        await self.events.publish(
            self.ticket_id,
            make_event(
                event_type,
                self.ticket_id,
                call_id=self.call_id,
                **payload,
            ),
        )

    async def _process_transcript(self, transcript: str) -> str:
        transcript = " ".join(transcript.split()).strip()
        if not transcript:
            return ""

        self._turn_count += 1
        await self._publish(
            "voice.user.final",
            item_id=f"stt-{self.call_id}-{self._turn_count}",
            text=transcript,
        )
        await self._publish("voice.state", state="thinking")

        async with self._turn_lock:
            db = SessionLocal()
            try:
                claim = db.query(Claim).filter(Claim.ticket_id == self.ticket_id).first()
                if not claim:
                    raise RuntimeError("Claim session no longer exists.")

                result = await process_claimant_turn(
                    db,
                    claim,
                    transcript,
                    "voice",
                    self._turn_count,
                )

                await self._publish(
                    "voice.claim.state",
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
                )

                response_text = str(
                    result.get("next_question")
                    or result.get("message")
                    or ""
                ).strip()

                if response_text:
                    await self._publish("voice.agent.final", text=response_text)
                return response_text
            finally:
                db.close()

    async def process_frame(self, frame: Any, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame):
            text = str(frame.text or "").strip()
            if not text:
                return
            try:
                response_text = await self._process_transcript(text)
                if response_text:
                    await self.push_frame(
                        TextFrame(response_text),
                        FrameDirection.DOWNSTREAM,
                    )
                    await self._publish("voice.state", state="speaking")
            except Exception as exc:
                logger.exception("Claim voice turn failed for %s", self.ticket_id)
                await self._publish(
                    "voice.error",
                    error_type=type(exc).__name__,
                )
                await self.push_frame(
                    TextFrame(
                        "I couldn't process that voice request right now. "
                        "Please try again, or continue by typing."
                    ),
                    FrameDirection.DOWNSTREAM,
                )
        elif frame.__class__.__name__ == "UserStartedSpeakingFrame":
            await self._publish("voice.state", state="listening")
        elif frame.__class__.__name__ == "UserStoppedSpeakingFrame":
            await self._publish("voice.state", state="transcribing")


async def build_voice_pipeline(
    *,
    connection: SmallWebRTCConnection,
    ticket_id: str,
    call_id: str,
    user_id: str,
    events: Any,
):
    """Build the local-only media → STT → claim-agent → TTS → media path."""
    http_session = aiohttp.ClientSession()
    try:
        transport = SmallWebRTCTransport(
            connection,
            TransportParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                audio_in_sample_rate=16000,
                audio_out_sample_rate=24000,
                audio_out_auto_silence=True,
                audio_out_end_silence_secs=0,
            ),
        )

        stt = WhisperSTTService(
            model=settings.VOICE_STT_MODEL,
            device=settings.VOICE_STT_DEVICE,
            compute_type=settings.VOICE_STT_COMPUTE_TYPE,
            language=settings.VOICE_STT_LANGUAGE,
            no_speech_prob=settings.VOICE_STT_NO_SPEECH_PROB,
            vad_analyzer=SileroVADAnalyzer(
                sample_rate=16000,
            ),
        )

        tts = PiperHttpTTSService(
            base_url=settings.VOICE_TTS_BASE_URL.rstrip("/"),
            aiohttp_session=http_session,
            voice_id=settings.VOICE_TTS_VOICE_ID,
        )

        claim_processor = ClaimVoiceProcessor(
            ticket_id=ticket_id,
            call_id=call_id,
            user_id=user_id,
            events=events,
        )

        pipeline = Pipeline(
            [
                transport.input(),
                stt,
                claim_processor,
                tts,
                transport.output(),
            ]
        )

        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                allow_interruptions=True,
                audio_in_sample_rate=16000,
                audio_out_sample_rate=24000,
                enable_heartbeats=True,
            ),
            cancel_on_idle_timeout=True,
            idle_timeout_secs=settings.VOICE_PIPELINE_IDLE_TIMEOUT_SECONDS,
            conversation_id=call_id,
        )
        return transport, task, http_session
    except Exception:
        await http_session.close()
        raise


async def run_voice_pipeline(
    *,
    connection: SmallWebRTCConnection,
    ticket_id: str,
    call_id: str,
    user_id: str,
    events: Any,
) -> None:
    """Run one isolated pipeline and clean all resources on termination."""
    transport = None
    task = None
    http_session = None
    runner = PipelineRunner(
        name=f"claim-voice-{call_id}",
        handle_sigint=False,
    )

    try:
        transport, task, http_session = await build_voice_pipeline(
            connection=connection,
            ticket_id=ticket_id,
            call_id=call_id,
            user_id=user_id,
            events=events,
        )

        @transport.event_handler("on_client_connected")
        async def _on_connected(_transport, _client):
            await self._set_session_status(call_id, "active")
            await events.publish(
                ticket_id,
                make_event(
                    "voice.session.ready",
                    ticket_id,
                    call_id=call_id,
                    provider="pipecat_local",
                    model=settings.VOICE_STT_MODEL,
                ),
            )
            await events.publish(
                ticket_id,
                make_event(
                    "voice.state",
                    ticket_id,
                    call_id=call_id,
                    state="listening",
                ),
            )

        @transport.event_handler("on_client_disconnected")
        async def _on_disconnected(_transport, _client):
            await events.publish(
                ticket_id,
                make_event(
                    "voice.session.disconnecting",
                    ticket_id,
                    call_id=call_id,
                ),
            )
            await runner.cancel()

        await runner.run(task)
    finally:
        if connection is not None:
            try:
                await connection.disconnect()
            except Exception:
                logger.debug("Failed to disconnect WebRTC connection.", exc_info=True)
        if http_session is not None:
            try:
                await http_session.close()
            except Exception:
                logger.debug("Failed to close Piper HTTP session.", exc_info=True)


async def _set_session_status(call_id: str, status: str) -> None:
    """Best-effort status update for the persisted voice session."""
    db = SessionLocal()
    try:
        from src.database.models import VoiceSession
        row = db.query(VoiceSession).filter(VoiceSession.call_id == call_id).first()
        if row:
            row.status = status
            if status == "active" and row.started_at is None:
                row.started_at = datetime.now(timezone.utc)
            db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to update voice session status.")
    finally:
        db.close()


__all__ = [
    "ClaimVoiceProcessor",
    "SileroVADAnalyzer",
    "SmallWebRTCConnection",
    "build_voice_pipeline",
    "run_voice_pipeline",
]
