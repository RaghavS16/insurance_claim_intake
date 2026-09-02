"""
Correlation ID context management and distributed tracing middleware.
Tracks requests across HTTP REST endpoints and asynchronous WebSocket sessions.
"""
import uuid
from contextvars import ContextVar
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# Global contextvar holding the active correlation ID for the current async task
_correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="")

HEADER_CORRELATION_ID = "X-Correlation-ID"
HEADER_REQUEST_ID = "X-Request-ID"


def get_correlation_id() -> str:
    """Get the correlation ID of the active request or context."""
    cid = _correlation_id_ctx.get()
    return cid if cid else ""


def set_correlation_id(cid: str) -> None:
    """Set the correlation ID for the active request or context."""
    _correlation_id_ctx.set(cid)


def generate_correlation_id(prefix: str = "req") -> str:
    """Generate a unique random correlation ID."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    FastAPI / Starlette middleware that extracts or generates a correlation ID,
    stores it in the contextvar, and attaches it to response headers.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        header_cid = (
            request.headers.get(HEADER_CORRELATION_ID)
            or request.headers.get(HEADER_REQUEST_ID)
            or request.query_params.get("correlation_id")
        )

        cid = header_cid if header_cid else generate_correlation_id("req")
        set_correlation_id(cid)

        # Attach to request state for handler access
        request.state.correlation_id = cid

        response = await call_next(request)
        response.headers[HEADER_CORRELATION_ID] = cid
        return response
