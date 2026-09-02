"""
In-memory thread-safe rate limiter with sliding window tracking.
Provides brute-force and credential-stuffing protection for sensitive endpoints.
"""
import threading
import time
from collections import defaultdict, deque
from typing import Dict, Optional, Tuple
from fastapi import HTTPException, Request, status

from src.config import settings
from src.utils.logger import app_logger

logger = app_logger


class SlidingWindowRateLimiter:
    """
    Thread-safe sliding window rate limiter.
    Tracks timestamps of requests for each identifier (e.g. IP + endpoint).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._requests: Dict[str, deque] = defaultdict(deque)

    def is_allowed(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> Tuple[bool, int, int]:
        """
        Check if a request is allowed.
        Returns:
            (allowed: bool, remaining_requests: int, retry_after_seconds: int)
        """
        now = time.time()
        window_start = now - window_seconds

        with self._lock:
            queue = self._requests[key]
            # Evict timestamps older than window_start
            while queue and queue[0] <= window_start:
                queue.popleft()

            if len(queue) < max_requests:
                queue.append(now)
                remaining = max_requests - len(queue)
                return True, remaining, 0
            else:
                oldest = queue[0]
                retry_after = max(1, int(oldest + window_seconds - now))
                return False, 0, retry_after

    def reset(self, key: Optional[str] = None):
        """Reset history for a specific key or all keys (useful for testing)."""
        with self._lock:
            if key:
                self._requests.pop(key, None)
            else:
                self._requests.clear()


# Global in-memory rate limiter instance
limiter = SlidingWindowRateLimiter()


def enforce_rate_limit(
    request: Request,
    action: str,
    max_requests: int = 5,
    window_seconds: int = 60,
    allow_test_bypass: bool = True,
) -> None:
    """
    Enforce rate limiting on an incoming HTTP request.
    Raises HTTPException(429) if threshold exceeded.
    """
    # Allow tests to selectively bypass rate limits unless testing rate limits explicitly
    if allow_test_bypass and settings.ENVIRONMENT == "test":
        if not request.headers.get("X-Test-Enforce-Rate-Limit"):
            return

    client_ip = request.client.host if request.client else "unknown"
    key = f"{action}:{client_ip}"

    allowed, remaining, retry_after = limiter.is_allowed(key, max_requests, window_seconds)
    if not allowed:
        logger.warning(
            "Rate limit exceeded for IP %s on action '%s'. Retry after %d seconds.",
            client_ip,
            action,
            retry_after,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many attempts for '{action}'. Please try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )
