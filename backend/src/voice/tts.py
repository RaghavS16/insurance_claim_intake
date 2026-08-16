"""
Text-to-speech using Piper (open-source, fast, self-hostable neural TTS from
the Rhasspy project). Piper ships as a CLI binary + ONNX voice models; shell
out to it rather than depend on an unofficial Python binding, since the
official interface is the `piper` executable.

Requires:
  - `piper` binary on PATH (or PIPER_BIN env var pointing to it)
  - a downloaded voice model, e.g. en_US-lessac-medium.onnx (+ .onnx.json)
    referenced via PIPER_VOICE_MODEL env var
"""
import logging
import os
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

PIPER_BIN = os.getenv("PIPER_BIN", "piper")
PIPER_VOICE_MODEL = os.getenv("PIPER_VOICE_MODEL")  # path to .onnx file


class TTSError(Exception):
    pass


def synthesize(text: str) -> bytes:
    """
    Synthesize `text` to 22050Hz mono WAV bytes via Piper. Raises TTSError on
    failure so callers (the WebSocket handler) can fall back to text-only
    display rather than silently sending empty audio.
    """
    if not PIPER_VOICE_MODEL:
        raise TTSError("PIPER_VOICE_MODEL environment variable is not set.")
    if not text or not text.strip():
        raise TTSError("Cannot synthesize empty text.")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        out_path = Path(tmp.name)

    try:
        result = subprocess.run(
            [PIPER_BIN, "--model", PIPER_VOICE_MODEL, "--output_file", str(out_path)],
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
        raise TTSError(f"piper binary not found at '{PIPER_BIN}'. Set PIPER_BIN or install piper on PATH.")
    finally:
        out_path.unlink(missing_ok=True)
