"""
Speech-to-text using faster-whisper (CTranslate2 reimplementation of Whisper —
open-source, MIT-licensed, with automatic CUDA GPU acceleration when available,
and graceful fallback to CPU inference).
"""
import io
import logging
import os
import sys
import wave
from pathlib import Path
from typing import Optional

from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

_MODEL_SIZE = "small"
_model: Optional[WhisperModel] = None


def _setup_cuda_dll_paths():
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

    # Try CUDA on GPU first
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            logger.info("Testing NVIDIA CUDA GPU for faster-whisper...")
            model = WhisperModel(_MODEL_SIZE, device="cuda", compute_type="float16")
            logger.info("faster-whisper successfully initialized on NVIDIA GPU (CUDA float16)!")
            return model
    except Exception as e:
        logger.warning("CUDA initialization failed (%s). Falling back to optimized CPU inference.", e)

    # Fallback to CPU int8
    logger.info("Initializing faster-whisper on CPU (compute_type=int8)...")
    return WhisperModel(_MODEL_SIZE, device="cpu", compute_type="int8")


def get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = _init_whisper_model()
    return _model


def _pcm16_to_wav_bytes(pcm_bytes: bytes, sample_rate: int = 16000) -> bytes:
    """faster-whisper's transcribe() accepts a file path or file-like object;
    wrapping raw PCM in a WAV header lets us hand it an in-memory buffer."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    buf.seek(0)
    return buf.read()


def transcribe_pcm16(pcm_bytes: bytes, sample_rate: int = 16000) -> str:
    """
    Transcribe a single utterance (already VAD-segmented) of raw PCM16 mono
    audio. Returns "" on empty/silent input rather than raising.
    """
    global _model
    # Ignore audio shorter than 400ms to avoid false noise triggers
    if len(pcm_bytes) < sample_rate * 2 * 0.4:
        return ""

    wav_bytes = _pcm16_to_wav_bytes(pcm_bytes, sample_rate)

    try:
        model = get_model()
        segments, info = model.transcribe(
            io.BytesIO(wav_bytes),
            language="en",       # English language pin
            vad_filter=False,    # already VAD-segmented upstream
            beam_size=3,
            temperature=0.0,
            no_speech_threshold=0.6,
        )
        seg_list = list(segments)
        valid_texts = [
            seg.text.strip() for seg in seg_list
            if getattr(seg, "no_speech_prob", 0.0) <= 0.6
        ]
        text = " ".join(valid_texts).strip()
        logger.info("STT transcribed %d bytes -> %r (lang_prob=%.2f)", len(pcm_bytes), text, getattr(info, "language_probability", 1.0))
        return text
    except RuntimeError as re:
        if "cublas" in str(re).lower() or "cudnn" in str(re).lower() or "cuda" in str(re).lower():
            logger.warning("CUDA runtime error encountered during transcription: %s. Falling back to CPU model.", re)
            try:
                _model = WhisperModel(_MODEL_SIZE, device="cpu", compute_type="int8")
                segments, info = _model.transcribe(
                    io.BytesIO(wav_bytes),
                    language="en",
                    vad_filter=False,
                    beam_size=3,
                    temperature=0.0,
                    no_speech_threshold=0.6,
                )
                seg_list = list(segments)
                valid_texts = [
                    seg.text.strip() for seg in seg_list
                    if getattr(seg, "no_speech_prob", 0.0) <= 0.6
                ]
                text = " ".join(valid_texts).strip()
                logger.info("STT fallback transcribed %d bytes -> %r", len(pcm_bytes), text)
                return text
            except Exception as cpu_err:
                logger.exception("CPU fallback transcription failed: %s", cpu_err)
                return ""
        logger.exception("STT transcription failed with runtime error")
        return ""
    except Exception:
        logger.exception("STT transcription failed")
        return ""
