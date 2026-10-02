"""Optional ClamAV quarantine gate for untrusted documents."""
from __future__ import annotations
import socket
from src.config import settings

def scan_bytes(content: bytes) -> tuple[bool, str]:
    if not settings.REQUIRE_MALWARE_SCAN:
        return True, "disabled"
    host = settings.CLAMAV_HOST
    if not host:
        if settings.ENVIRONMENT in ("production", "staging"):
            return False, "malware_scanner_not_configured"
        return True, "not_configured_non_production"
    try:
        with socket.create_connection((host, settings.CLAMAV_PORT), timeout=settings.CLAMAV_TIMEOUT_SECONDS) as sock:
            sock.sendall(b"zINSTREAM\0")
            for i in range(0, len(content), 1024 * 1024):
                chunk = content[i:i + 1024 * 1024]
                sock.sendall(len(chunk).to_bytes(4, "big"))
                sock.sendall(chunk)
            sock.sendall((0).to_bytes(4, "big"))
            response = sock.recv(4096).decode("utf-8", errors="replace").strip()
        if response.endswith("OK"):
            return True, "clean"
        return False, response or "malware_detected"
    except Exception:
        if settings.ENVIRONMENT in ("production", "staging"):
            return False, "malware_scanner_unavailable"
        return True, "scanner_unavailable_non_production"
