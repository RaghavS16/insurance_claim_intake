"""
Speech-to-text service using faster-whisper (CTranslate2 reimplementation of Whisper —
open-source, MIT-licensed, with automatic CUDA GPU acceleration when available,
and graceful fallback to CPU inference).

Two public interfaces are provided:

1. transcribe_pcm16(pcm_bytes) -> str
   Synchronous, one-shot transcription of a complete audio chunk.
   Used for the /flush path (connection close) and by tests.

2. ASRProvider / WhisperASRProvider
   Abstract provider interface + concrete faster-whisper implementation.
   The StreamingASRBuffer uses this internally so the ASR backend is replaceable.

3. StreamingASRBuffer
   Accumulates audio frames and runs partial + final transcriptions.
   Partial transcriptions are produced every ASR_CHUNK_MS milliseconds.
   Final transcription is requested explicitly via finalize().

The WebSocket voice pipeline uses StreamingASRBuffer through the ClaimantASRWorker.
"""
import abc
import io
import logging
import os
import sys
import time
import wave
from pathlib import Path
from typing import Optional, Tuple

from faster_whisper import WhisperModel

from src.config import settings
from src.utils.logger import app_logger

logger = app_logger

_model: Optional[WhisperModel] = None


# ---------------------------------------------------------------------------
# CUDA / GPU initialization helpers
# ---------------------------------------------------------------------------

def _setup_cuda_dll_paths() -> None:
    """On Windows, add NVIDIA package bin directories to the DLL search path."""
    if sys.platform == "win32":
        try:
            import site
            site_packages = site.getsitepackages()
            for sp in site_packages:
                sp_path = Path(sp)
                for nvidia_dir in sp_path.glob("nvidia/*"):
                    bin_dir = nvidia_dir / "bin"
                    if bin_dir.exists():
                        try:
                            os.add_dll_directory(str(bin_dir))
                            os.environ["PATH"] = f"{str(bin_dir)};{os.environ.get('PATH', '')}"
                            logger.debug("Added NVIDIA DLL directory: %s", bin_dir)
                        except Exception as e:
                            logger.debug("Could not add DLL dir %s: %s", bin_dir, e)
        except Exception as e:
            logger.debug("NVIDIA DLL setup encountered: %s", e)


def _init_whisper_model() -> WhisperModel:
    """Initialize WhisperModel with CUDA acceleration if available, fallback to CPU."""
    _setup_cuda_dll_paths()
    model_size = settings.STT_MODEL_SIZE

    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            logger.info("Testing NVIDIA CUDA GPU for faster-whisper...")
            model = WhisperModel(model_size, device="cuda", compute_type="float16")
            logger.info("faster-whisper successfully initialized on NVIDIA GPU (CUDA float16)!")
            return model
    except Exception as e:
        logger.warning("CUDA initialization failed (%s). Falling back to optimized CPU inference.", e)

    logger.info("Initializing faster-whisper on CPU (model_size=%s, compute_type=int8)...", model_size)
    return WhisperModel(model_size, device="cpu", compute_type="int8")


def get_model() -> WhisperModel:
    """Singleton getter for WhisperModel instance."""
    global _model
    if _model is None:
        _model = _init_whisper_model()
    return _model


# ---------------------------------------------------------------------------
# Low-level audio helpers
# ---------------------------------------------------------------------------

def _pcm16_to_wav_bytes(pcm_bytes: bytes, sample_rate: int = 16000) -> bytes:
    """Wraps raw PCM16 mono audio in a standard 44-byte WAV header in-memory."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    buf.seek(0)
    return buf.read()


def _is_hallucination(text: str) -> bool:
    """Check if the transcribed text matches common Whisper hallucinations during silence."""
    cleaned = text.strip().lower().rstrip(".,?!")
    hallucinations = {
        "thank you", "thank you very much", "you", "bye", "bye-bye", "bye bye",
        "um", "uh", "go ahead", "thanks", "thank you so much"
    }
    return cleaned in hallucinations


def _run_whisper(pcm_bytes: bytes, sample_rate: int = 16000) -> Tuple[str, float]:
    """
    Run faster-whisper on pcm_bytes and return (text, confidence).
    Falls back to CPU on CUDA errors. Returns ("", 0.0) on any failure.
    """
    global _model

    if len(pcm_bytes) < sample_rate * 2 * 0.2:  # < 200ms → skip
        return "", 0.0

    wav_bytes = _pcm16_to_wav_bytes(pcm_bytes, sample_rate)

    def _transcribe(model: WhisperModel) -> Tuple[str, float]:
        segments, info = model.transcribe(
            io.BytesIO(wav_bytes),
            language="en",
            vad_filter=False,   # VAD is handled upstream
            beam_size=3,
            temperature=0.0,
            no_speech_threshold=0.6,
        )
        seg_list = list(segments)
        lang_prob = getattr(info, "language_probability", 1.0)
        valid_texts = [
            seg.text.strip() for seg in seg_list
            if getattr(seg, "no_speech_prob", 0.0) <= 0.6
        ]
        confidence = lang_prob if valid_texts else 0.0
        return " ".join(valid_texts).strip(), confidence

    try:
        model = get_model()
        text, confidence = _transcribe(model)
        if _is_hallucination(text):
            logger.info("Filtered Whisper hallucination: %r (conf=%.2f)", text, confidence)
            return "", 0.0
        logger.debug("Whisper: %d bytes → %r (conf=%.2f)", len(pcm_bytes), text, confidence)
        return text, confidence
    except RuntimeError as re_err:
        err_str = str(re_err).lower()
        if any(k in err_str for k in ("cublas", "cudnn", "cuda")):
            logger.warning("CUDA runtime error: %s. Falling back to CPU model.", re_err)
            try:
                _model = WhisperModel(settings.STT_MODEL_SIZE, device="cpu", compute_type="int8")
                text, confidence = _transcribe(_model)
                if _is_hallucination(text):
                    logger.info("Filtered Whisper hallucination on CPU fallback: %r", text)
                    return "", 0.0
                return text, confidence
            except Exception as cpu_err:
                logger.exception("CPU fallback transcription failed: %s", cpu_err)
                return "", 0.0
        logger.exception("STT transcription failed with runtime error")
        return "", 0.0
    except Exception:
        logger.exception("STT transcription failed")
        return "", 0.0


# ---------------------------------------------------------------------------
# Public one-shot API (kept for backward compatibility and /flush path)
# ---------------------------------------------------------------------------

def transcribe_pcm16(pcm_bytes: bytes, sample_rate: int = 16000) -> str:
    """
    Transcribe a single complete audio chunk (already VAD-segmented).
    Returns "" on empty/silent/short input rather than raising.

    This is the legacy one-shot interface. New code should use StreamingASRBuffer
    or WhisperASRProvider directly.
    """
    if len(pcm_bytes) < sample_rate * 2 * 0.4:  # < 400ms
        return ""
    text, _ = _run_whisper(pcm_bytes, sample_rate)
    logger.info("STT transcribed %d bytes → %r", len(pcm_bytes), text)
    return text


# ---------------------------------------------------------------------------
# ASRProvider abstraction — makes the ASR backend replaceable
# ---------------------------------------------------------------------------

class ASRProvider(abc.ABC):
    """
    Abstract interface for a streaming-capable ASR provider.

    Implementations must be thread-safe for concurrent partial/final calls.
    The WhisperASRProvider uses the global singleton WhisperModel.
    """

    @abc.abstractmethod
    def transcribe(self, pcm_bytes: bytes, sample_rate: int = 16000) -> Tuple[str, float]:
        """
        Transcribe pcm_bytes and return (text, confidence).
        confidence is 0.0 – 1.0; 0.0 means no speech detected.
        """
        ...


class WhisperASRProvider(ASRProvider):
    """
    ASRProvider backed by faster-whisper (singleton model).
    This is the default production provider.
    """

    def transcribe(self, pcm_bytes: bytes, sample_rate: int = 16000) -> Tuple[str, float]:
        return _run_whisper(pcm_bytes, sample_rate)


# ---------------------------------------------------------------------------
# StreamingASRBuffer — progressive partial → final transcription
# ---------------------------------------------------------------------------

class StreamingASRBuffer:
    """
    Accumulates raw PCM16 audio and provides progressive ASR results.

    Usage pattern (driven by ClaimantASRWorker):

        buf = StreamingASRBuffer()
        buf.push(audio_chunk)            # feed raw audio
        text, conf = buf.partial()       # get partial transcript (rate-limited internally)
        text, conf = buf.finalize()      # get final transcript and reset buffer

    The partial() method is rate-limited: it only runs Whisper if at least
    ASR_CHUNK_MS ms of new audio has been added since the last partial call.

    finalize() always runs Whisper regardless of how much audio is present.
    After finalize(), the buffer is reset and ready for the next utterance.

    Parameters
    ----------
    provider : ASRProvider
        The ASR backend to use (default: WhisperASRProvider).
    sample_rate : int
        Audio sample rate in Hz (must match the mic capture rate — 16000).
    chunk_ms : int
        Minimum ms of new audio before a partial transcription is attempted.
    """

    def __init__(
        self,
        provider: Optional[ASRProvider] = None,
        sample_rate: int = 16000,
        chunk_ms: Optional[int] = None,
    ):
        self._provider = provider or WhisperASRProvider()
        self._sample_rate = sample_rate
        self._chunk_ms = chunk_ms if chunk_ms is not None else settings.ASR_CHUNK_MS
        # bytes required for one chunk window
        self._chunk_bytes = int(sample_rate * 2 * (self._chunk_ms / 1000.0))
        self._buffer = b""
        self._last_partial_bytes = 0  # how many bytes were in the buffer at last partial call
        self._accumulated_text = ""   # confirmed prefix transcript reconciled so far
        self._last_confidence = 0.0

    @staticmethod
    def reconcile_transcripts(prefix: str, suffix: str) -> str:
        """
        Finds the best overlap between the end of prefix and the start of suffix and joins them.
        Handles strict word-level matches and falls back to anchor word matching or containment.
        """
        p_words = prefix.strip().split()
        s_words = suffix.strip().split()
        if not p_words:
            return suffix
        if not s_words:
            return prefix

        # 1. Try strict word match overlap
        max_overlap = min(len(p_words), len(s_words))
        for n in range(max_overlap, 0, -1):
            p_slice = [w.lower().strip(".,?!") for w in p_words[-n:]]
            s_slice = [w.lower().strip(".,?!") for w in s_words[:n]]
            if p_slice == s_slice:
                return " ".join(p_words[:-n] + s_words)

        # 2. Look for the first word of suffix in the last few words of prefix (fuzzy anchor)
        for i in range(max(0, len(p_words) - 5), len(p_words)):
            p_word_lower = p_words[i].lower().strip(".,?!")
            s_word_lower = s_words[0].lower().strip(".,?!")
            if p_word_lower == s_word_lower:
                overlap_len = len(p_words) - i
                if overlap_len <= len(s_words):
                    return " ".join(p_words[:i] + s_words)

        # 3. Containment fallback
        p_lower = prefix.lower()
        s_lower = suffix.lower()
        if s_lower in p_lower:
            return prefix
        if p_lower in s_lower:
            return suffix

        # 4. No overlap found, concatenate
        return prefix + " " + suffix

    def push(self, pcm_bytes: bytes) -> None:
        """Append raw PCM16 audio to the buffer."""
        self._buffer += pcm_bytes

    def partial(self) -> Tuple[str, float]:
        """
        Attempt a rolling-window partial transcription if enough new audio has accumulated.
        Only transcribes the last 3 seconds of the audio buffer to keep latency low,
        and reconciles the result with the previously accumulated text.
        """
        new_bytes = len(self._buffer) - self._last_partial_bytes
        if new_bytes < self._chunk_bytes:
            return self._accumulated_text, self._last_confidence

        self._last_partial_bytes = len(self._buffer)
        return self.force_partial()

    def force_partial(self) -> Tuple[str, float]:
        """
        Run a rolling-window partial transcription unconditionally on the tail of the buffer.
        """
        if not self._buffer:
            return "", 0.0

        # Define rolling window size: last 3000ms of audio
        window_ms = 3000
        window_bytes = int(self._sample_rate * 2 * (window_ms / 1000.0))

        if len(self._buffer) <= window_bytes:
            # Buffer is short, transcribe the entire thing
            text, conf = self._provider.transcribe(self._buffer, self._sample_rate)
            self._accumulated_text = text
            self._last_confidence = conf
        else:
            # Transcribe only the last 3 seconds of audio (sliding window)
            window_audio = self._buffer[-window_bytes:]
            suffix_text, conf = self._provider.transcribe(window_audio, self._sample_rate)
            
            # Reconcile new window text with previously accumulated text
            self._accumulated_text = self.reconcile_transcripts(self._accumulated_text, suffix_text)
            self._last_confidence = conf

        return self._accumulated_text, self._last_confidence

    def finalize(self) -> Tuple[str, float]:
        """
        Run final transcription on the complete buffer, then reset.
        Always runs Whisper on the full audio to ensure maximum accuracy.
        """
        pcm = self._buffer
        self.reset()
        if not pcm:
            return "", 0.0
        return self._provider.transcribe(pcm, self._sample_rate)

    def reset(self) -> None:
        """Discard buffered audio and reset the accumulated transcript."""
        self._buffer = b""
        self._last_partial_bytes = 0
        self._accumulated_text = ""
        self._last_confidence = 0.0

    @property
    def buffered_ms(self) -> float:
        """Duration of buffered audio in milliseconds."""
        if not self._buffer:
            return 0.0
        return (len(self._buffer) / 2.0 / self._sample_rate) * 1000.0
