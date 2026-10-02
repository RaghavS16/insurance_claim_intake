"""Production HTTP middleware.

Security controls live here so every route gets the same protections.
"""
from __future__ import annotations

import time
import uuid
from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import settings
from src.utils.logger import app_logger

logger = app_logger


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(self), geolocation=()")
        if settings.ENVIRONMENT in {"production", "staging"}:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        response.headers.setdefault("Cache-Control", "no-store" if request.url.path.startswith("/api/") else "private")
        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        # This is an early guard; upload handlers still enforce their own exact limits.
        raw = request.headers.get("content-length")
        if raw:
            try:
                length = int(raw)
            except ValueError:
                return JSONResponse(status_code=400, content={"error": {"code": "INVALID_CONTENT_LENGTH"}})
            if length > settings.MAX_REQUEST_BODY_BYTES:
                return JSONResponse(status_code=413, content={"error": {"code": "REQUEST_TOO_LARGE"}})
        return await call_next(request)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("Unhandled request error request_id=%s method=%s path=%s", request_id, request.method, request.url.path)
            raise
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-ms"] = f"{(time.perf_counter()-started)*1000:.1f}"
        return response
