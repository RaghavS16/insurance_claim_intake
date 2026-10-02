"""Streaming upload guards.

Never call UploadFile.read() without a bounded read for untrusted uploads.
"""
from __future__ import annotations

from typing import BinaryIO

async def read_limited(upload, max_bytes: int, chunk_size: int = 1024 * 1024) -> bytes:
    total = 0
    chunks: list[bytes] = []
    while True:
        chunk = await upload.read(min(chunk_size, max_bytes + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ValueError(f"Upload exceeds the {max_bytes} byte limit.")
        chunks.append(chunk)
    return b"".join(chunks)

def validate_declared_size(content_length: str | None, max_bytes: int) -> None:
    if content_length is None:
        return
    try:
        size = int(content_length)
    except ValueError as exc:
        raise ValueError("Invalid content length.") from exc
    if size > max_bytes:
        raise ValueError("Upload exceeds the configured size limit.")
