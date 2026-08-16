"""
Text-to-speech using Piper (open-source neural TTS).

Synthesizes response text to WAV audio for voice conversation streaming.
Falls back to TTSError so WebSocket caller can instruct client to use Web Speech API.
"""
import logging
import os
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class TTSError(Exception):
    """Raised when text synthesis fails or Piper model is unconfigured."""
    pass


def synthesize(text: str) -> bytes:
    """
    Synthesize `text` to 22050Hz mono WAV bytes via Piper. Raises TTSError on failure.
    """
    if not text or not text.strip():
        raise TTSError("Cannot synthesize empty text.")

    piper_bin = os.getenv("PIPER_BIN", "piper")
    piper_voice_model = os.getenv("PIPER_VOICE_MODEL")

    if not piper_voice_model:
        raise TTSError("PIPER_VOICE_MODEL environment variable is not set.")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        out_path = Path(tmp.name)

    try:
        result = subprocess.run(
            [piper_bin, "--model", piper_voice_model, "--output_file", str(out_path)],
            input=text.encode("utf-8"),
            capture_output=True,
            timeout=15,
        )
        if result.returncode != 0:
            raise TTSError(f"piper exited {result.returncode}: {result.stderr.decode(errors='replace')}")

        audio_bytes = out_path.read_bytes()
        if not audio_bytes:
            raise TTSError("piper produced empty audio output.")
        return audio_bytes
    except subprocess.TimeoutExpired:
        raise TTSError("piper synthesis timed out.")
    except FileNotFoundError:
        raise TTSError(f"piper binary not found at '{piper_bin}'. Set PIPER_BIN or install piper on PATH.")
    finally:
        out_path.unlink(missing_ok=True)
