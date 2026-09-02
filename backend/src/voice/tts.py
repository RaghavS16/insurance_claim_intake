"""
Text-to-speech service using Piper neural TTS.

Synthesizes response text to WAV audio for voice conversation streaming.
Raises TTSError on failure so WebSocket caller can instruct client to use Web Speech API fallback.
"""
import os
import sys
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from src.config import settings
from src.utils.logger import app_logger

logger = app_logger


class TTSError(Exception):
    """Raised when text synthesis fails or Piper model is unconfigured."""
    pass


def _resolve_piper_bin() -> str:
    """Find the piper executable binary path."""
    env_bin = os.environ.get("PIPER_BIN") or getattr(settings, "PIPER_BIN", "piper")
    if env_bin and (Path(env_bin).is_file() or shutil.which(env_bin)):
        return env_bin

    # Look in the current Python environment's Scripts / bin
    venv_dir = Path(sys.executable).parent
    for candidate in [venv_dir / "piper.exe", venv_dir / "piper"]:
        if candidate.is_file():
            return str(candidate)

    which_bin = shutil.which("piper")
    if which_bin:
        return which_bin

    return env_bin or "piper"


def _resolve_model_path(configured_model: Optional[str]) -> str:
    """Resolve the ONNX voice model path from configured path or known directories."""
    if configured_model and Path(configured_model).is_file():
        return str(Path(configured_model).resolve())

    search_dirs = [
        Path(__file__).parent.parent.parent / "piper",  # backend/piper
        Path.cwd() / "piper",
        Path.cwd() / "backend" / "piper",
        Path(__file__).parent.parent.parent,
    ]

    candidates = [
        configured_model,
        "en_US-ryan-medium.onnx",
        "en_US-lessac-medium.onnx",
    ]

    for d in search_dirs:
        for c in candidates:
            if c:
                p = d / c
                if p.is_file():
                    return str(p.resolve())
        if d.is_dir():
            for f in d.glob("*.onnx"):
                if f.is_file():
                    return str(f.resolve())

    return configured_model or "en_US-ryan-medium.onnx"


def synthesize(text: str) -> bytes:
    """
    Synthesize `text` to 22050Hz mono WAV bytes via Piper. Raises TTSError on failure.
    """
    if not text or not text.strip():
        raise TTSError("Cannot synthesize empty text.")

    raw_model = os.environ.get("PIPER_VOICE_MODEL", settings.PIPER_VOICE_MODEL)
    resolved_model = _resolve_model_path(raw_model)
    if not resolved_model or not Path(resolved_model).is_file():
        raise TTSError(f"Piper voice model not found: '{resolved_model}'.")

    piper_bin = _resolve_piper_bin()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        out_path = Path(tmp.name)

    try:
        result = subprocess.run(
            [piper_bin, "--model", str(resolved_model), "--output_file", str(out_path)],
            input=text.encode("utf-8"),
            capture_output=True,
            timeout=15,
        )
        if result.returncode != 0:
            raise TTSError(f"piper exited with code {result.returncode}: {result.stderr.decode(errors='replace')}")

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


async def synthesize_async(text: str) -> bytes:
    """
    Asynchronously synthesize response text to WAV audio via threadpool.
    Ensures that Piper subprocess spawning does not block the asyncio event loop.
    """
    import asyncio
    return await asyncio.to_thread(synthesize, text)
