"""Pipecat voice pipeline for real-time insurance claim intake."""

from __future__ import annotations

import io
import json
import os
import site
import sys
import wave
from typing import Any

def _ensure_nvidia_dll_paths() -> None:
    """Ensure Windows can locate NVIDIA CUDA/cuDNN DLLs from installed site-packages."""
    if sys.platform != "win32":
        return
    search_dirs = list(site.getsitepackages())
    if hasattr(site, "getusersitepackages"):
        search_dirs.append(site.getusersitepackages())
    for sp in search_dirs:
        nvidia_dir = os.path.join(sp, "nvidia")
        if os.path.isdir(nvidia_dir):
            for sub in os.listdir(nvidia_dir):
                bin_dir = os.path.join(nvidia_dir, sub, "bin")
                if os.path.isdir(bin_dir):
                    if hasattr(os, "add_dll_directory"):
                        try:
                            os.add_dll_directory(bin_dir)
                        except Exception:
                            pass
                    if bin_dir not in os.environ.get("PATH", ""):
                        os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")

_ensure_nvidia_dll_paths()

import aiohttp
import webrtcvad
from pipecat.audio.vad.vad_analyzer import VADAnalyzer, VADParams
from pipecat.audio.utils import pcm_to_wav
from pipecat.frames.frames import (
    Frame,
    InputAudioRawFrame,
    InterimTranscriptionFrame,
    InterruptionFrame,
    OutputAudioRawFrame,
    OutputTransportMessageFrame,
    TextFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    TTSSpeakFrame,
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
    """Serialize PCM16 input and browser-playable WAV output."""

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
    """Pipecat VAD adapter backed by WebRTC VAD."""

    def __init__(self, aggressiveness: int = 1, *, sample_rate: int = 16000):
        params = VADParams(confidence=0.5, start_secs=0.08, stop_secs=0.25, min_volume=0.0)
        super().__init__(sample_rate=sample_rate, params=params)
        self._vad = webrtcvad.Vad(aggressiveness)

    def num_frames_required(self) -> int:
        return int(self.sample_rate * 0.02)

    def voice_confidence(self, buffer: bytes) -> float:
        return 1.0 if self._vad.is_speech(buffer, self.sample_rate) else 0.0


from pathlib import Path

def _find_piper_model_path(configured_path: str | None) -> str | None:
    """Resolve the location of a local Piper ONNX model file."""
    if not configured_path:
        return None
    candidates = [
        Path(configured_path),
        Path("backend") / configured_path,
        Path.cwd() / configured_path,
        Path.cwd() / "backend" / configured_path,
        Path(__file__).resolve().parent.parent.parent / configured_path,
        Path(__file__).resolve().parent.parent.parent / "backend" / configured_path,
        Path(__file__).resolve().parent.parent.parent / "piper" / "en_US-ryan-medium.onnx",
    ]
    for p in candidates:
        if p.is_file():
            return str(p.resolve())
    return None


class PiperNativeTTSService(TTSService):
    """Pipecat TTS service executing Piper in-process without an external HTTP server."""

    def __init__(self, *, model_path: str, config_path: str | None = None, **kwargs: Any):
        super().__init__(settings=TTSSettings(model=model_path, voice=None, language=None), **kwargs)
        self._model_path = model_path
        self._config_path = config_path or f"{model_path}.json"
        self._voice: Any = None

    async def setup(self, setup):
        await super().setup(setup)
        try:
            import asyncio
            from piper import PiperVoice
            if os.path.exists(self._model_path):
                self._voice = await asyncio.to_thread(
                    PiperVoice.load, self._model_path, self._config_path
                )
                logger.info("Loaded native Piper TTS model from %s", self._model_path)
        except Exception as exc:
            logger.warning("Could not pre-load native Piper model: %s", exc)

    async def run_tts(self, text: str, context_id: str):
        import asyncio
        from pipecat.frames.frames import ErrorFrame, TTSStoppedFrame

        if not self._voice:
            try:
                from piper import PiperVoice
                if os.path.exists(self._model_path):
                    self._voice = await asyncio.to_thread(
                        PiperVoice.load, self._model_path, self._config_path
                    )
            except Exception as exc:
                logger.exception("Failed to load native Piper voice: %s", exc)
                yield ErrorFrame(error=f"Native Piper load failed: {exc}")
                yield TTSStoppedFrame(context_id=context_id)
                return

        if not self._voice:
            yield ErrorFrame(error=f"Piper ONNX model not found at {self._model_path}")
            yield TTSStoppedFrame(context_id=context_id)
            return

        try:
            def _synth():
                return list(self._voice.synthesize(text))

            chunks = await asyncio.to_thread(_synth)
            combined_pcm = bytearray()
            sample_rate = 22050
            sample_channels = 1
            for chunk in chunks:
                audio_bytes = getattr(chunk, "audio_int16_bytes", None)
                if audio_bytes:
                    combined_pcm.extend(audio_bytes)
                    sample_rate = getattr(chunk, "sample_rate", sample_rate)
                    sample_channels = getattr(chunk, "sample_channels", sample_channels)

            if combined_pcm:
                yield TTSAudioRawFrame(
                    audio=bytes(combined_pcm),
                    sample_rate=sample_rate,
                    num_channels=sample_channels,
                    context_id=context_id,
                )
        except Exception as exc:
            logger.exception("Native Piper synthesis failed")
            yield ErrorFrame(error=f"Native Piper synthesis failed: {type(exc).__name__}")
        finally:
            yield TTSStoppedFrame(context_id=context_id)


class PiperHTTPSettings(TTSSettings):
    """Configuration for the external Piper HTTP service."""


class PiperHTTPService(TTSService):
    """Pipecat TTS adapter for a separately running Piper HTTP server."""

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
                wav_bytes = await response.read()
                with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
                    audio = wav_file.readframes(wav_file.getnframes())
                    sample_rate = wav_file.getframerate()
                    channels = wav_file.getnchannels()
                yield TTSAudioRawFrame(
                    audio=audio,
                    sample_rate=sample_rate,
                    num_channels=channels,
                    context_id=context_id,
                )
        except Exception as exc:
            logger.exception("Piper HTTP synthesis failed")
            yield ErrorFrame(error=f"Piper HTTP synthesis failed: {type(exc).__name__}")
        finally:
            yield TTSStoppedFrame(context_id=context_id)


class ClaimAgentProcessor(FrameProcessor):
    """Bridge Pipecat transcription and interruption frames to claim logic."""

    def __init__(self, claim: Claim, *, input_mode: str = "voice"):
        super().__init__()
        self._claim = claim
        self._input_mode = input_mode
        self._db = SessionLocal()
        self._turn_number = 0
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
            await self.push_frame(OutputTransportMessageFrame(message={
                "type": "transcript", "speaker": "claimant", "text": frame.text,
                "is_final": False, "segment_id": f"claimant-{self._segment_number}",
            }), direction)
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, TranscriptionFrame) and frame.text.strip():
            await self._handle_final_transcript(frame.text.strip())
            return
        await self.push_frame(frame, direction)

    async def _handle_final_transcript(self, text: str):
        segment_id = f"claimant-{self._segment_number or 1}"
        await self.push_frame(OutputTransportMessageFrame(message={
            "type": "transcript", "speaker": "claimant", "text": text,
            "is_final": True, "segment_id": segment_id,
        }))
        self._turn_number += 1
        result = await process_claimant_turn(self._db, self._claim, text, self._input_mode, self._turn_number)
        await self.push_frame(OutputTransportMessageFrame(message={
            "type": "state_update",
            "extracted_data": result.get("extracted_data", {}) or {},
            "missing_fields": result.get("missing_fields", []),
            "field_status": result.get("field_status", {}),
            "awaiting_confirmation": result.get("awaiting_confirmation", False),
            "confirmed": result.get("confirmed", False),
            "conversation_status": result.get("conversation_status"),
        }))
        agent_text = result.get("next_question") or result.get("message", "")
        if agent_text:
            await self.push_frame(OutputTransportMessageFrame(message={
                "type": "transcript", "speaker": "agent", "text": agent_text,
                "is_final": True, "segment_id": f"agent-{self._turn_number}",
            }))
            await self.push_frame(TTSSpeakFrame(text=agent_text))


def build_voice_pipeline(
    transport: BaseTransport,
    claim: Claim,
    *,
    stt_model: str = "small",
    stt_device: str = "cuda",
    stt_compute_type: str = "float16",
    vad_aggressiveness: int = 1,
    piper_model_path: str | None = None,
    piper_url: str | None = None,
    piper_voice: str | None = None,
) -> PipelineWorker:
    """Build the Pipecat worker used by the insurance voice endpoint."""
    vad = VADProcessor(vad_analyzer=WebRTCVADAnalyzer(vad_aggressiveness))
    try:
        stt = WhisperSTTService(
            device=stt_device,
            compute_type=stt_compute_type,
            settings=WhisperSTTService.Settings(model=stt_model, language="en"),
        )
    except Exception as exc:
        logger.warning(
            "Failed to initialize WhisperSTTService on device=%s (%s). Falling back to CPU.",
            stt_device,
            exc,
        )
        stt = WhisperSTTService(
            device="cpu",
            compute_type="default",
            settings=WhisperSTTService.Settings(model=stt_model, language="en"),
        )
    agent = ClaimAgentProcessor(claim)

    resolved_model = _find_piper_model_path(piper_model_path)
    if resolved_model:
        tts = PiperNativeTTSService(model_path=resolved_model)
    elif piper_url:
        tts = PiperHTTPService(base_url=piper_url, voice=piper_voice)
    else:
        # Fallback to local default model location if exists
        default_model = _find_piper_model_path("piper/en_US-ryan-medium.onnx")
        if default_model:
            tts = PiperNativeTTSService(model_path=default_model)
        else:
            tts = PiperHTTPService(base_url="http://localhost:5000/synthesize", voice=piper_voice)

    pipeline = Pipeline([transport.input(), vad, stt, agent, tts, transport.output()])
    return PipelineWorker(pipeline, processor_unusable_policy=ProcessorUnusablePolicy.END)


def websocket_transport(websocket) -> FastAPIWebsocketTransport:
    """Create the Pipecat WebSocket transport."""
    return FastAPIWebsocketTransport(websocket, FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        serializer=PCM16WebSocketSerializer(),
        add_wav_header=False,
    ))
