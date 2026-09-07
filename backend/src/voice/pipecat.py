"""Pipecat voice pipeline for real-time insurance claim intake."""

from __future__ import annotations

import json
from typing import Any

import aiohttp
import webrtcvad
from pipecat.audio.vad.vad_analyzer import VADAnalyzer, VADParams
from pipecat.frames.frames import (
    Frame,
    InputAudioRawFrame,
    InterimTranscriptionFrame,
    OutputAudioRawFrame,
    OutputTransportMessageFrame,
    TextFrame,
    TranscriptionFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineWorker, ProcessorUnusablePolicy
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.settings import TTSSettings
from pipecat.services.tts_service import TTSService
from pipecat.services.whisper.stt import WhisperSTTService
from pipecat.serializers.base_serializer import FrameSerializer
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport

from src.agents.turn_processor import process_claimant_turn
from src.database.models import Claim
from src.database.session import SessionLocal
from src.utils.logger import app_logger

logger = app_logger


class PCM16WebSocketSerializer(FrameSerializer):
    """Serialize raw mono PCM16 audio and JSON control messages."""

    async def serialize(self, frame: Frame) -> str | bytes | None:
        if isinstance(frame, OutputAudioRawFrame):
            return frame.audio
        if isinstance(frame, OutputTransportMessageFrame):
            return json.dumps(frame.message)
        return None

    async def deserialize(self, data: str | bytes) -> Frame | None:
        if isinstance(data, bytes):
            return InputAudioRawFrame(audio=data, sample_rate=16000, num_channels=1)
        return None


class WebRTCVADAnalyzer(VADAnalyzer):
    """Pipecat VAD adapter backed by WebRTC VAD."""

    def __init__(self, aggressiveness: int = 1, *, sample_rate: int = 16000):
        params = VADParams(confidence=0.5, start_secs=0.1, stop_secs=0.6, min_volume=0.0)
        super().__init__(sample_rate=sample_rate, params=params)
        self._vad = webrtcvad.Vad(aggressiveness)

    def num_frames_required(self) -> int:
        return int(self.sample_rate * 0.02)

    def voice_confidence(self, buffer: bytes) -> float:
        return 1.0 if self._vad.is_speech(buffer, self.sample_rate) else 0.0


class PiperHTTPSettings(TTSSettings):
    """Configuration for the external Piper HTTP service."""


class PiperHTTPService(TTSService):
    """Small Pipecat TTS adapter for a separately running Piper HTTP server."""

    Settings = PiperHTTPSettings

    def __init__(self, *, base_url: str, voice: str | None = None, **kwargs: Any):
        super().__init__(settings=self.Settings(model=None, voice=voice, language=None), **kwargs)
        self._base_url = base_url.rstrip("/")
        self._session: aiohttp.ClientSession | None = None

    async def setup(self, setup):
        await super().setup(setup)
        self._session = aiohttp.ClientSession()

    async def cleanup(self):
        if self._session and not self._session.closed:
            await self._session.close()
        await super().cleanup()

    async def run_tts(self, text: str, context_id: str):
        from pipecat.frames.frames import ErrorFrame, TTSStoppedFrame

        if not self._session:
            yield ErrorFrame(error="Piper HTTP session is not initialized")
            return
        try:
            payload = {"text": text}
            if self._settings.voice:
                payload["voice"] = self._settings.voice
            async with self._session.post(self._base_url, json=payload) as response:
                if response.status != 200:
                    yield ErrorFrame(error=f"Piper HTTP server returned {response.status}")
                    return
                wav = await response.read()
                if wav.startswith(b"RIFF") and len(wav) > 44:
                    wav = wav[44:]
                async for frame in self._stream_audio_frames_from_iterator(
                    self._one_chunk(wav), context_id=context_id
                ):
                    yield frame
        except Exception as exc:
            logger.exception("Piper HTTP synthesis failed")
            yield ErrorFrame(error=f"Piper HTTP synthesis failed: {type(exc).__name__}")
        finally:
            yield TTSStoppedFrame(context_id=context_id)

    @staticmethod
    async def _one_chunk(audio: bytes):
        yield audio


class ClaimAgentProcessor(FrameProcessor):
    """Bridge Pipecat transcription frames to the existing insurance agent."""

    def __init__(self, claim: Claim, *, input_mode: str = "voice"):
        super().__init__()
        self._claim = claim
        self._input_mode = input_mode
        self._db = SessionLocal()
        self._turn_number = 0

    async def cleanup(self):
        self._db.close()
        await super().cleanup()

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, InterimTranscriptionFrame):
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, TranscriptionFrame) and frame.text.strip():
            await self._handle_final_transcript(frame.text.strip())
            return
        await self.push_frame(frame, direction)

    async def _handle_final_transcript(self, text: str):
        self._turn_number += 1
        result = await process_claimant_turn(
            self._db, self._claim, text, self._input_mode, self._turn_number
        )
        extracted = result.get("extracted_data", {}) or {}
        await self.push_frame(OutputTransportMessageFrame(message={
            "type": "state_update",
            "extracted_data": extracted,
            "missing_fields": result.get("missing_fields", []),
            "field_status": result.get("field_status", {}),
            "awaiting_confirmation": result.get("awaiting_confirmation", False),
            "confirmed": result.get("confirmed", False),
            "conversation_status": result.get("conversation_status"),
        }))
        agent_text = result.get("next_question") or result.get("message", "")
        if agent_text:
            await self.push_frame(OutputTransportMessageFrame(message={
                "type": "transcript",
                "speaker": "agent",
                "text": agent_text,
            }))
            await self.push_frame(TextFrame(text=agent_text))


def build_voice_pipeline(
    transport: BaseTransport,
    claim: Claim,
    *,
    stt_model: str = "small",
    vad_aggressiveness: int = 1,
    piper_url: str,
    piper_voice: str | None = None,
) -> PipelineWorker:
    """Build the Pipecat worker used by the insurance voice endpoint."""
    vad = VADProcessor(vad_analyzer=WebRTCVADAnalyzer(vad_aggressiveness))
    stt = WhisperSTTService(
        settings=WhisperSTTService.Settings(model=stt_model, language="en")
    )
    agent = ClaimAgentProcessor(claim)
    tts = PiperHTTPService(base_url=piper_url, voice=piper_voice)
    pipeline = Pipeline([
        transport.input(),
        vad,
        stt,
        agent,
        tts,
        transport.output(),
    ])
    return PipelineWorker(pipeline, processor_unusable_policy=ProcessorUnusablePolicy.END)


def websocket_transport(websocket) -> FastAPIWebsocketTransport:
    """Create the Pipecat WebSocket transport."""
    params = FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        serializer=PCM16WebSocketSerializer(),
        add_wav_header=False,
    )
    return FastAPIWebsocketTransport(websocket, params)
