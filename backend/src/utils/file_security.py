"""File security utilities: download headers, media type allowlist, magic byte verification."""
from __future__ import annotations

import os
import re
import urllib.parse
from pathlib import Path

MEDIA_TYPE_ALLOWLIST = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def get_safe_media_type(filename: str) -> str:
    ext = Path(filename or "").suffix.lower()
    return MEDIA_TYPE_ALLOWLIST.get(ext, "application/octet-stream")


def sanitize_filename(filename: str) -> str:
    raw = os.path.basename(filename or "file")
    # Strip quotes, CR/LF, path separators and control characters
    cleaned = re.sub(r'[\r\n"\\/\x00-\x1f\x7f]', "", raw).strip()
    return cleaned or "download"


def build_attachment_headers(filename: str) -> dict[str, str]:
    clean = sanitize_filename(filename)
    ascii_name = clean.encode("ascii", "replace").decode("ascii").replace('"', "").replace(";", "")
    encoded_name = urllib.parse.quote(clean, safe="")
    return {
        "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded_name}",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox; default-src 'none'",
    }


def verify_upload_magic_bytes(content: bytes, filename: str) -> tuple[bool, str]:
    """Verify magic bytes match the extension for pdf, images and docx; reject mismatches."""
    if not content:
        return False, "Uploaded file is empty."
    ext = Path(filename or "").suffix.lower()
    if ext == ".pdf":
        if not content.startswith(b"%PDF-"):
            return False, "File content does not match expected PDF signature."
    elif ext in {".jpg", ".jpeg"}:
        if not content.startswith(b"\xff\xd8\xff"):
            return False, "File content does not match expected JPEG signature."
    elif ext == ".png":
        if not content.startswith(b"\x89PNG\r\n\x1a\n"):
            return False, "File content does not match expected PNG signature."
    elif ext == ".webp":
        if not (content.startswith(b"RIFF") and len(content) >= 12 and content[8:12] == b"WEBP"):
            return False, "File content does not match expected WEBP signature."
    elif ext == ".docx":
        if not content.startswith(b"PK\x03\x04"):
            return False, "File content does not match expected DOCX signature."
    return True, ""
