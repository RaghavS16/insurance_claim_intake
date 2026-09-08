"""Pipecat voice pipeline for real-time insurance claim intake.

Production mode prefers streaming Deepgram STT for low latency when configured;
local Whisper remains an explicit offline/development fallback.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import site
import sys
import threading
import wave
from pathlib import Path
from typing import Any

from pipecat.audio.vad.vad_analyzer import VADAnalyzer, VADParams
from pipecat.audio.utils import pcm_to_wav
from pipecat.frames.frames import (
    ErrorFrame,
    Frame,
    InputAudioRawFrame,
    InterruptionFrame,
    InterimTranscriptionFrame,
    OutputAudioRawFrame,
    OutputTransportMessageFrame,
    TranscriptionFrame,
    TTSStoppedFrame,
    TTSAudioRawFrame,
    TTSSpeakFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineWorker, ProcessorUnusablePolicy
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.serializers.base_serializer import FrameSerializer
from pipecat.services.settings import TTSSettings
from pipecat.services.tts_service import TTSService
from pipecat.services.whisper.stt import WhisperSTTService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport
import webrtcvad

from src.agents.turn_processor import process_claimant_turn
from src.config import settings
from src.database.models import Claim
from src.database.session import SessionLocal
from src.utils.logger import app_logger

logger = app_logger


def _ensure_nvidia_dll_paths() -> None:
    if sys.platform != "win32":
        return
    search_dirs = list(site.getsitepackages())
    if hasattr(site, "getusersitepackages"):
        search_dirs.append(site.getusersitepackages())
    for sp in search_dirs:
        nvidia_dir = os.path.join(sp, "nvidia")
        if not os.path.isdir(nvidia_dir):
            continue
        for sub in os.listdir(nvidia_dir):
            bin_dir = os.path.join(nvidia_dir, sub, "bin")
            if os.path.isdir(bin_dir):
                try:
                    if hasattr(os, "add_dll_directory"):
                        os.add_dll_directory(bin_dir)
                except Exception:
                    pass
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")


_ensure_nvidia_dll_paths()


class PCM16WebSocketSerializer(FrameSerializer):
    async def serialize(self, frame: Frame) -> str | bytes | None:
        if isinstance(frame, OutputAudioRawFrame):
            return pcm_to_wav(frame.audio, frame.sample_rate, frame.num_channels)
        if isinstance(frame, OutputTransportMessageFrame):
            return json.dumps(frame.message)
        return None

    async def deserialize(self, data: str | bytes) -> Frame | None:
        if isinstance(data, bytes):
            return InputAudioRawFrame(audio=data, sample_rate=16000, num_channels=1)
        return None


class WebRTCVADAnalyzer(VADAnalyzer):
    def __init__(self, aggressiveness: int = 1, *, sample_rate: int = 16000):
        super().__init__(
            sample_rate=sample_rate,
            params=VADParams(confidence=0.5, start_secs=0.08, stop_secs=0.24, min_volume=0.0),
        )
        self._vad = webrtcvad.Vad(max(0, min(3, aggressiveness)))

    def num_frames_required(self) -> int:
        return int(self.sample_rate * 0.02)

    def voice_confidence(self, buffer: bytes) -> float:
        try:
            return 1.0 if self._vad.is_speech(buffer, self.sample_rate) else 0.0
        except Exception:
            return 0.0


def _find_piper_model_path(configured_path: str | None) -> str | None:
    if not configured_path:
        return None
    candidates = [
        Path(configured_path),
        Path("backend") / configured_path,
        Path.cwd() / configured_path,
        Path.cwd() / "backend" / configured_path,
        Path(__file__).resolve().parents[2] / configured_path,
        Path(__file__).resolve().parents[2] / "backend" / configured_path,
    ]
    for path in candidates:
        if path.is_file():
            return str(path.resolve())
    return None


class PiperNativeTTSService(TTSService):
    def __init__(self, *, model_path: str, config_path: str | None = None, **kwargs: Any):
        super().__init__(settings=TTSSettings(model=model_path, voice=None, language=None), **kwargs)
        self._model_path = model_path
        self._config_path = config_path or f"{model_path}.json"
        self._voice: Any = None

    async def setup(self, setup):
        await super().setup(setup)
        try:
            from piper import PiperVoice
            if os.path.exists(self._model_path):
                self._voice = await asyncio.to_thread(PiperVoice.load, self._model_path, self._config_path)
                logger.info("Loaded native Piper TTS model from %s", self._model_path)
        except Exception as exc:
            logger.warning("Could not preload native Piper model: %s", exc)

    async def run_tts(self, text: str, context_id: str):
        if not self._voice:
            yield ErrorFrame(error=f"Piper ONNX model not available at {self._model_path}")
            yield TTSStoppedFrame(context_id=context_id)
            return
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Any] = asyncio.Queue()
        sentinel = object()

        def synthesize():
            try:
                for chunk in self._voice.synthesize(text):
                    audio = getattr(chunk, "audio_int16_bytes", None)
                    if audio:
                        loop.call_soon_threadsafe(
                            queue.put_nowait,
                            (bytes(audio), int(getattr(chunk, "sample_rate", 22050)), int(getattr(chunk, "sample_channels", 1))),
                        )
            except Exception as exc:
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, sentinel)

        threading.Thread(target=synthesize, name="piper-synthesis", daemon=True).start()
        try:
            while True:
                item = await queue.get()
                if item is sentinel:
                    break
                if isinstance(item, Exception):
                    logger.error("Native Piper synthesis failed: %s", item)
                    yield ErrorFrame(error=f"Native Piper synthesis failed: {type(item).__name__}")
                    break
                audio, sample_rate, channels = item
                yield TTSAudioRawFrame(audio=audio, sample_rate=sample_rate, num_channels=channels, context_id=context_id)
        finally:
            yield TTSStoppedFrame(context_id=context_id)


class PiperHTTPSettings(TTSSettings):
    pass


class PiperHTTPService(TTSService):
    Settings = PiperHTTPSettings

    def __init__(self, *, base_url: str, voice: str | None = None, **kwargs: Any):
        super().__init__(settings=self.Settings(model=None, voice=voice, language=None), **kwargs)
        self._base_url = base_url.rstrip("/")
        self._session = None

    async def setup(self, setup):
        await super().setup(setup)
        import aiohttp
        self._session = aiohttp.ClientSession()

    async def cleanup(self):
        if self._session and not self._session.closed:
            await self._session.close()
        await super().cleanup()

    async def run_tts(self, text: str, context_id: str):
        if not self._session:
            yield ErrorFrame(error="Piper HTTP session is not initialized")
            yield TTSStoppedFrame(context_id=context_id)
            return
        try:
            payload = {"text": text}
            if self._settings.voice:
                payload["voice"] = self._settings.voice
            async with self._session.post(self._base_url, json=payload) as response:
                if response.status != 200:
                    yield ErrorFrame(error=f"Piper HTTP server returned {response.status}")
                else:
                    wav_bytes = await response.read()
                    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
                        audio = wav_file.readframes(wav_file.getnframes())
                        sample_rate = wav_file.getframerate()
                        channels = wav_file.getnchannels()
                    yield TTSAudioRawFrame(audio=audio, sample_rate=sample_rate, num_channels=channels, context_id=context_id)
        except Exception as exc:
            logger.exception("Piper HTTP synthesis failed")
            yield ErrorFrame(error=f"Piper HTTP synthesis failed: {type(exc).__name__}")
        finally:
            yield TTSStoppedFrame(context_id=context_id)


class ClaimAgentProcessor(FrameProcessor):
    """Bridge Pipecat frames to the persistent claim conversation domain."""

    def __init__(self, claim: Claim, *, input_mode: str = "voice"):
        super().__init__()
        self._db = SessionLocal()
        self._ticket_id = claim.ticket_id
        self._input_mode = input_mode
        self._segment_number = 0

    async def cleanup(self):
        self._db.close()
        await super().cleanup()

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, InterruptionFrame):
            await self.push_frame(OutputTransportMessageFrame(message={"type": "barge_in"}), direction)
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, InterimTranscriptionFrame):
            self._segment_number += 1
            await self.push_frame(
                OutputTransportMessageFrame(
                    message={
                        "type": "transcript",
                        "speaker": "claimant",
                        "text": frame.text,
                        "is_final": False,
                        "segment_id": f"claimant-{self._segment_number}",
                    }
                ),
                direction,
            )
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, TranscriptionFrame) and frame.text.strip():
            await self._handle_final_transcript(frame.text.strip(), direction)
            return
        await self.push_frame(frame, direction)

    async def _handle_final_transcript(self, text: str, direction: FrameDirection):
        segment_id = f"claimant-{self._segment_number or 1}"
        await self.push_frame(
            OutputTransportMessageFrame(
                message={"type": "transcript", "speaker": "claimant", "text": text, "is_final": True, "segment_id": segment_id}
            ),
            direction,
        )
        await self.push_frame(OutputTransportMessageFrame(message={"type": "agent_state", "state": "thinking"}), direction)
        claim = self._db.query(Claim).filter(Claim.ticket_id == self._ticket_id).first()
        if not claim:
            await self.push_frame(OutputTransportMessageFrame(message={"type": "error", "message": "Claim session is no longer available."}), direction)
            return
        result = await process_claimant_turn(self._db, claim, text, self._input_mode)
        await self.push_frame(
            OutputTransportMessageFrame(
                message={
                    "type": "state_update",
                    "extracted_data": result.get("extracted_data", {}) or {},
                    "missing_fields": result.get("missing_fields", []),
                    "field_status": result.get("field_status", {}),
                    "awaiting_confirmation": result.get("awaiting_confirmation", False),
                    "confirmed": result.get("confirmed", False),
                    "conversation_status": result.get("conversation_status"),
                }
            ),
            direction,
        )
        agent_text = result.get("next_question") or result.get("message", "")
        if agent_text:
            await self.push_frame(
                OutputTransportMessageFrame(
                    message={"type": "transcript", "speaker": "agent", "text": agent_text, "is_final": True, "segment_id": f"agent-{self._segment_number}"}
                ),
                direction,
            )
            await self.push_frame(TTSSpeakFrame(text=agent_text), direction)


def _build_stt(*, model: str, device: str, compute_type: str):
    provider = (settings.STT_PROVIDER or "auto").lower().strip()
    if provider in {"deepgram", "auto"} and settings.DEEPGRAM_API_KEY:
        try:
            from pipecat.services.deepgram.stt import DeepgramSTTService
            stt = DeepgramSTTService(
                api_key=settings.DEEPGRAM_API_KEY,
                settings=DeepgramSTTService.Settings(
                    model=settings.DEEPGRAM_MODEL,
                    language=settings.STT_LANGUAGE,
                    interim_results=True,
                    punctuate=True,
                    smart_format=True,
                    endpointing=250,
                    utterance_end_ms=800,
                ),
            )
            logger.info("Using streaming Deepgram STT for production voice")
            return stt
        except Exception as exc:
            if provider == "deepgram":
                raise RuntimeError(f"Deepgram STT could not be initialized: {type(exc).__name__}") from exc
            logger.warning("Deepgram STT unavailable; falling back to Whisper: %s", exc)
    try:
        logger.info("Using local Whisper STT fallback")
        return WhisperSTTService(
            device=device,
            compute_type=compute_type,
            settings=WhisperSTTService.Settings(model=model, language=settings.STT_LANGUAGE),
        )
    except Exception as exc:
        logger.warning("Whisper initialization failed on %s/%s: %s; using CPU fallback", device, compute_type, exc)
        return WhisperSTTService(
            device="cpu",
            compute_type="default",
            settings=WhisperSTTService.Settings(model=model, language=settings.STT_LANGUAGE),
        )


def build_voice_pipeline(
    transport: BaseTransport,
    claim: Claim,
    *,
    stt_model: str | None = None,
    stt_device: str | None = None,
    stt_compute_type: str | None = None,
    vad_aggressiveness: int | None = None,
    piper_model_path: str | None = None,
    piper_url: str | None = None,
    piper_voice: str | None = None,
) -> PipelineWorker:
    model = stt_model or settings.STT_MODEL_SIZE
    device = stt_device or settings.STT_DEVICE
    compute_type = stt_compute_type or settings.STT_COMPUTE_TYPE
    vad_level = settings.VAD_AGGRESSIVENESS if vad_aggressiveness is None else vad_aggressiveness
    vad = VADProcessor(vad_analyzer=WebRTCVADAnalyzer(vad_level))
    stt = _build_stt(model=model, device=device, compute_type=compute_type)
    agent = ClaimAgentProcessor(claim)
    resolved_model = _find_piper_model_path(piper_model_path or settings.PIPER_MODEL_PATH)
    if resolved_model:
        tts = PiperNativeTTSService(model_path=resolved_model)
    elif piper_url or settings.PIPER_HTTP_URL:
        tts = PiperHTTPService(
            base_url=piper_url or settings.PIPER_HTTP_URL or "http://localhost:5000/synthesize",
            voice=piper_voice or settings.PIPER_VOICE,
        )
    else:
        raise RuntimeError("No Piper TTS configuration is available")
    return PipelineWorker(
        Pipeline([transport.input(), vad, stt, agent, tts, transport.output()]),
        processor_unusable_policy=ProcessorUnusablePolicy.END,
    )


def websocket_transport(websocket) -> FastAPIWebsocketTransport:
    return FastAPIWebsocketTransport(
        websocket,
        FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            serializer=PCM16WebSocketSerializer(),
            add_wav_header=False,
        ),
    )
