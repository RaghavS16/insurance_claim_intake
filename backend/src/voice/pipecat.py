"""Pipecat voice pipeline for real-time insurance claim intake."""
from __future__ import annotations
import asyncio, io, json, os, site, sys, threading, time, wave
from pathlib import Path
from typing import Any
from pipecat.audio.vad.vad_analyzer import VADAnalyzer, VADParams
from pipecat.audio.utils import pcm_to_wav
from pipecat.frames.frames import (
    ErrorFrame,
    Frame,
    InputAudioRawFrame,
    InputTransportMessageFrame,
    InterruptionFrame,
    InterimTranscriptionFrame,
    OutputAudioRawFrame,
    OutputTransportMessageFrame,
    TTSStoppedFrame,
    TTSAudioRawFrame,
    TTSSpeakFrame,
    TranscriptionFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
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
    if sys.platform != "win32": return
    search_dirs = list(site.getsitepackages())
    if hasattr(site, "getusersitepackages"): search_dirs.append(site.getusersitepackages())
    for sp in search_dirs:
        nvidia_dir = os.path.join(sp, "nvidia")
        if not os.path.isdir(nvidia_dir): continue
        for sub in os.listdir(nvidia_dir):
            bin_dir = os.path.join(nvidia_dir, sub, "bin")
            if os.path.isdir(bin_dir):
                try:
                    if hasattr(os, "add_dll_directory"): os.add_dll_directory(bin_dir)
                except Exception: pass
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
_ensure_nvidia_dll_paths()

class PCM16WebSocketSerializer(FrameSerializer):
    async def serialize(self, frame: Frame) -> str | bytes | None:
        if isinstance(frame, OutputAudioRawFrame): return pcm_to_wav(frame.audio, frame.sample_rate, frame.num_channels)
        if isinstance(frame, OutputTransportMessageFrame): return json.dumps(frame.message)
        return None
    async def deserialize(self, data: str | bytes) -> Frame | None:
        if isinstance(data, bytes):
            return InputAudioRawFrame(audio=data, sample_rate=16000, num_channels=1)
        if isinstance(data, str):
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                return None
            if isinstance(message, dict):
                return InputTransportMessageFrame(message=message)
        return None

class WebRTCVADAnalyzer(VADAnalyzer):
    def __init__(self, aggressiveness: int = 1, *, sample_rate: int = 16000):
        super().__init__(sample_rate=sample_rate, params=VADParams(confidence=0.5, start_secs=0.08, stop_secs=0.65, min_volume=0.0))
        self._vad = webrtcvad.Vad(max(0, min(3, aggressiveness))); self._frame_samples = int(sample_rate * 0.02)
    def num_frames_required(self) -> int: return self._frame_samples
    def voice_confidence(self, buffer: bytes) -> float:
        try: return 1.0 if self._vad.is_speech(buffer, self.sample_rate) else 0.0
        except Exception: return 0.0

def _find_piper_model_path(configured_path: str | None) -> str | None:
    if not configured_path: return None
    candidates = [Path(configured_path), Path("backend") / configured_path, Path.cwd() / configured_path, Path.cwd() / "backend" / configured_path, Path(__file__).resolve().parents[2] / configured_path, Path(__file__).resolve().parents[2] / "backend" / configured_path]
    for path in candidates:
        if path.is_file(): return str(path.resolve())
    return None

class PiperNativeTTSService(TTSService):
    def __init__(self, *, model_path: str, config_path: str | None = None, **kwargs: Any):
        super().__init__(settings=TTSSettings(model=model_path, voice=None, language=None), **kwargs); self._model_path=model_path; self._config_path=config_path or f"{model_path}.json"; self._voice=None
    async def setup(self, setup):
        await super().setup(setup)
        try:
            from piper import PiperVoice
            if os.path.exists(self._model_path): self._voice = await asyncio.to_thread(PiperVoice.load, self._model_path, self._config_path)
        except Exception as exc: logger.warning("Could not preload native Piper model: %s", exc)
    async def run_tts(self, text: str, context_id: str):
        if not self._voice: yield ErrorFrame(error=f"Piper ONNX model not available at {self._model_path}"); yield TTSStoppedFrame(context_id=context_id); return
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Any] = asyncio.Queue()
        sentinel = object()
        def synthesize():
            try:
                for chunk in self._voice.synthesize(text):
                    audio=getattr(chunk,"audio_int16_bytes",None)
                    if audio: loop.call_soon_threadsafe(queue.put_nowait,(bytes(audio),int(getattr(chunk,"sample_rate",22050)),int(getattr(chunk,"sample_channels",1))))
            except Exception as exc: loop.call_soon_threadsafe(queue.put_nowait,exc)
            finally: loop.call_soon_threadsafe(queue.put_nowait,sentinel)
        threading.Thread(target=synthesize,name="piper-synthesis",daemon=True).start()
        try:
            while True:
                item=await queue.get()
                if item is sentinel: break
                if isinstance(item,Exception): yield ErrorFrame(error=f"Native Piper synthesis failed: {type(item).__name__}"); break
                audio,sample_rate,channels=item; yield TTSAudioRawFrame(audio=audio,sample_rate=sample_rate,num_channels=channels,context_id=context_id)
        finally: yield TTSStoppedFrame(context_id=context_id)

class PiperHTTPSettings(TTSSettings): pass
class PiperHTTPService(TTSService):
    Settings=PiperHTTPSettings
    def __init__(self, *, base_url: str, voice: str | None = None, **kwargs: Any): super().__init__(settings=self.Settings(model=None,voice=voice,language=None),**kwargs); self._base_url=base_url.rstrip("/"); self._session=None
    async def setup(self, setup): await super().setup(setup); import aiohttp; self._session=aiohttp.ClientSession()
    async def cleanup(self):
        if self._session and not self._session.closed: await self._session.close()
        await super().cleanup()
    async def run_tts(self,text:str,context_id:str):
        if not self._session: yield ErrorFrame(error="Piper HTTP session is not initialized"); yield TTSStoppedFrame(context_id=context_id); return
        try:
            payload={"text":text};
            if self._settings.voice: payload["voice"]=self._settings.voice
            async with self._session.post(self._base_url,json=payload) as response:
                if response.status!=200: yield ErrorFrame(error=f"Piper HTTP server returned {response.status}")
                else:
                    wav_bytes=await response.read()
                    with wave.open(io.BytesIO(wav_bytes),"rb") as wav_file: audio=wav_file.readframes(wav_file.getnframes()); sample_rate=wav_file.getframerate(); channels=wav_file.getnchannels()
                    yield TTSAudioRawFrame(audio=audio,sample_rate=sample_rate,num_channels=channels,context_id=context_id)
        except Exception as exc: yield ErrorFrame(error=f"Piper HTTP synthesis failed: {type(exc).__name__}")
        finally: yield TTSStoppedFrame(context_id=context_id)

class ClaimAgentProcessor(FrameProcessor):
    """Gate claimant turns on real VAD silence and make voice turns interruptible."""

    FINAL_DEBOUNCE_SECONDS = settings.VOICE_TURN_SILENCE_SECONDS
    DUPLICATE_TRANSCRIPT_WINDOW_SECONDS = 1.5

    def __init__(self, claim: Claim, *, input_mode: str = "voice"):
        super().__init__()
        self._db = SessionLocal()
        self._ticket_id = claim.ticket_id
        self._input_mode = input_mode
        self._segment_number = 0
        self._pending_text = ""
        self._pending_at = 0.0
        self._debounce_task: asyncio.Task | None = None
        self._turn_queue = asyncio.Queue(maxsize=settings.VOICE_MAX_QUEUED_TURNS)
        self._worker_task = asyncio.create_task(self._turn_worker())
        self._generation = 0
        self._user_speaking = False
        self._last_final_text = ""
        self._last_final_at = 0.0

    async def cleanup(self):
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
        self._db.close()
        await super().cleanup()

    async def _cancel_debounce(self):
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
        self._debounce_task = None

    async def _interrupt_for_user_speech(self, direction: FrameDirection):
        self._generation += 1
        self._pending_text = ""
        await self._cancel_debounce()
        try:
            while not self._turn_queue.empty():
                _, _, _ = self._turn_queue.get_nowait()
                self._turn_queue.task_done()
        except asyncio.QueueEmpty:
            pass
        # Pipecat treats InterruptionFrame as a system-level preemption signal;
        # broadcasting it reaches the TTS/output transport immediately.
        await self.broadcast_interruption()
        await self.push_frame(
            OutputTransportMessageFrame(
                message={"type": "barge_in", "generation": self._generation}
            ),
            direction,
        )

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, InputTransportMessageFrame):
            message = frame.message if isinstance(frame.message, dict) else {}
            if message.get("type") == "barge_in":
                await self._interrupt_for_user_speech(direction)
                return
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, VADUserStartedSpeakingFrame):
            self._user_speaking = True
            await self._interrupt_for_user_speech(direction)
            return

        if isinstance(frame, VADUserStoppedSpeakingFrame):
            self._user_speaking = False
            self._pending_at = time.monotonic()
            if self._pending_text:
                await self._cancel_debounce()
                self._debounce_task = asyncio.create_task(self._flush_after_pause(direction))
            return

        if isinstance(frame, InterruptionFrame):
            self._generation += 1
            self._pending_text = ""
            await self._cancel_debounce()
            await self.push_frame(
                OutputTransportMessageFrame(
                    message={"type": "barge_in", "generation": self._generation}
                ),
                direction,
            )
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
                        "segment_id": f"claimant-live-{self._segment_number}",
                    }
                ),
                direction,
            )
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, TranscriptionFrame) and frame.text.strip():
            text = " ".join(frame.text.split()).strip()
            now = time.monotonic()
            if (
                text.casefold() == self._last_final_text.casefold()
                and now - self._last_final_at < self.DUPLICATE_TRANSCRIPT_WINDOW_SECONDS
            ):
                return
            self._last_final_text = text
            self._last_final_at = now
            self._pending_text = f"{self._pending_text} {text}".strip()
            self._pending_at = now
            # Never finalize from STT punctuation/finalization alone. Whisper can
            # emit final chunks while the claimant is still speaking. VAD stop is
            # the turn boundary; the short debounce only protects against trailing
            # transcription packets.
            if not self._user_speaking:
                await self._cancel_debounce()
                self._debounce_task = asyncio.create_task(self._flush_after_pause(direction))
            return

        await self.push_frame(frame, direction)

    async def _flush_after_pause(self, direction: FrameDirection):
        try:
            while self._pending_text:
                if self._user_speaking:
                    return
                wait = self.FINAL_DEBOUNCE_SECONDS - (time.monotonic() - self._pending_at)
                if wait > 0:
                    await asyncio.sleep(wait)
                    continue
                if self._user_speaking:
                    return
                text = self._pending_text.strip()
                self._pending_text = ""
                if text:
                    try:
                        while self._turn_queue.full():
                            _, _, _ = self._turn_queue.get_nowait()
                            self._turn_queue.task_done()
                    except asyncio.QueueEmpty:
                        pass
                    await self._turn_queue.put((text, direction, self._generation))
                return
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("Debounced voice turn failed")

    async def _turn_worker(self):
        try:
            while True:
                text, direction, generation = await self._turn_queue.get()
                try:
                    await self._handle_final_transcript(text, direction, generation)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Queued voice turn failed")
                finally:
                    self._turn_queue.task_done()
        except asyncio.CancelledError:
            return

    async def _handle_final_transcript(self, text, direction, generation):
        if generation != self._generation:
            return
        segment_id = f"claimant-{self._segment_number or 1}"
        await self.push_frame(
            OutputTransportMessageFrame(
                message={
                    "type": "transcript",
                    "speaker": "claimant",
                    "text": text,
                    "is_final": True,
                    "segment_id": segment_id,
                    "generation": generation,
                }
            ),
            direction,
        )
        await self.push_frame(
            OutputTransportMessageFrame(
                message={"type": "agent_state", "state": "thinking"}
            ),
            direction,
        )
        db = SessionLocal()
        try:
            claim = db.query(Claim).filter(Claim.ticket_id == self._ticket_id).first()
            if not claim:
                return
            result = await process_claimant_turn(db, claim, text, self._input_mode)
        finally:
            db.close()
        if generation != self._generation:
            return
        await self.push_frame(
            OutputTransportMessageFrame(
                message={
                    "type": "state_update",
                    "extracted_data": result.get("extracted_data", {}) or {},
                    "missing_fields": result.get("missing_fields", []),
                    "field_status": result.get("field_status", {}),
                    "awaiting_confirmation": result.get("awaiting_confirmation", False),
                    "confirmed": result.get("confirmed", False),
                    "status": result.get("status"),
                    "conversation_status": result.get("conversation_status"),
                    "missing_evidence": result.get("missing_evidence", []),
                    "evidence": result.get("evidence", []),
                }
            ),
            direction,
        )
        agent_text = result.get("next_question") or result.get("message", "")
        if agent_text and generation == self._generation:
            await self.push_frame(
                OutputTransportMessageFrame(
                    message={
                        "type": "transcript",
                        "speaker": "agent",
                        "text": agent_text,
                        "is_final": True,
                        "segment_id": f"agent-{self._segment_number}",
                        "generation": generation,
                    }
                ),
                direction,
            )
            await self.push_frame(TTSSpeakFrame(text=agent_text), direction)

def build_voice_pipeline(transport:BaseTransport,claim:Claim,*,stt_model:str|None=None,stt_device:str|None=None,stt_compute_type:str|None=None,vad_aggressiveness:int|None=None,piper_model_path:str|None=None,piper_url:str|None=None,piper_voice:str|None=None)->PipelineWorker:
    model=stt_model or settings.STT_MODEL_SIZE; device=stt_device or settings.STT_DEVICE; compute_type=stt_compute_type or settings.STT_COMPUTE_TYPE; vad_level=settings.VAD_AGGRESSIVENESS if vad_aggressiveness is None else vad_aggressiveness
    vad=VADProcessor(vad_analyzer=WebRTCVADAnalyzer(vad_level))
    try: stt=WhisperSTTService(device=device,compute_type=compute_type,settings=WhisperSTTService.Settings(model=model,language=settings.STT_LANGUAGE))
    except Exception as exc: logger.warning("Whisper initialization failed on %s/%s: %s",device,compute_type,exc); stt=WhisperSTTService(device="cpu",compute_type="default",settings=WhisperSTTService.Settings(model=model,language=settings.STT_LANGUAGE))
    agent=ClaimAgentProcessor(claim); resolved_model=_find_piper_model_path(piper_model_path or settings.PIPER_MODEL_PATH)
    if resolved_model: tts=PiperNativeTTSService(model_path=resolved_model)
    elif piper_url or settings.PIPER_HTTP_URL: tts=PiperHTTPService(base_url=piper_url or settings.PIPER_HTTP_URL or "http://localhost:5000/synthesize",voice=piper_voice or settings.PIPER_VOICE)
    else: raise RuntimeError("No Piper TTS configuration is available")
    return PipelineWorker(Pipeline([transport.input(),vad,stt,agent,tts,transport.output()]),processor_unusable_policy=ProcessorUnusablePolicy.END)

def websocket_transport(websocket)->FastAPIWebsocketTransport:
    return FastAPIWebsocketTransport(websocket,FastAPIWebsocketParams(audio_in_enabled=True,audio_out_enabled=True,serializer=PCM16WebSocketSerializer(),add_wav_header=False))
