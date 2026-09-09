"""
Distributed rate limiter with sliding window tracking.
Supports Redis for multi-worker / cluster deployments with automatic,
graceful fallback to in-memory sliding window when Redis is unavailable.
"""
import threading
import time
from collections import defaultdict, deque
from typing import Dict, Optional, Tuple
from fastapi import HTTPException, Request, status

from src.config import settings
from src.utils.logger import app_logger

logger = app_logger


class InMemorySlidingWindowRateLimiter:
    """
    Thread-safe in-memory sliding window rate limiter.
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
        now = time.time()
        window_start = now - window_seconds

        with self._lock:
            queue = self._requests[key]
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
        with self._lock:
            if key:
                self._requests.pop(key, None)
            else:
                self._requests.clear()


class RedisSlidingWindowRateLimiter:
    """
    Distributed sliding window rate limiter using Redis sorted sets (ZSET).
    Falls back transparently to in-memory limiter on connection errors.
    """

    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._redis_client = None
        self._fallback = InMemorySlidingWindowRateLimiter()
        self._connect()

    def _connect(self):
        try:
            import importlib
            redis_mod = importlib.import_module("redis")
            self._redis_client = redis_mod.Redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
            )
            # Quick ping to verify connectivity
            self._redis_client.ping()
            logger.info("Connected to Redis for distributed rate limiting at %s", self._redis_url)
        except Exception as exc:
            logger.warning("Redis rate limiter unavailable (%s). Falling back to in-memory mode.", exc)
            self._redis_client = None

    def is_allowed(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> Tuple[bool, int, int]:
        if not self._redis_client:
            return self._fallback.is_allowed(key, max_requests, window_seconds)

        now = time.time()
        window_start = now - window_seconds
        redis_key = f"rate_limit:{key}"

        try:
            pipe = self._redis_client.pipeline()
            # 1. Remove old timestamps outside sliding window
            pipe.zremrangebyscore(redis_key, 0, window_start)
            # 2. Count remaining requests in current window
            pipe.zcard(redis_key)
            # 3. Get oldest timestamp in current window for Retry-After calculation
            pipe.zrange(redis_key, 0, 0, withscores=True)
            results = pipe.execute()

            current_count = results[1]
            oldest_record = results[2]

            if current_count < max_requests:
                # Add current timestamp to window
                p2 = self._redis_client.pipeline()
                p2.zadd(redis_key, {str(now): now})
                p2.expire(redis_key, window_seconds + 5)
                p2.execute()
                return True, max_requests - (current_count + 1), 0
            else:
                if oldest_record:
                    oldest_ts = oldest_record[0][1]
                    retry_after = max(1, int(oldest_ts + window_seconds - now))
                else:
                    retry_after = window_seconds
                return False, 0, retry_after
        except Exception as exc:
            logger.warning("Redis rate limiter error (%s). Falling back to in-memory mode.", exc)
            return self._fallback.is_allowed(key, max_requests, window_seconds)

    def reset(self, key: Optional[str] = None):
        if self._redis_client:
            try:
                if key:
                    self._redis_client.delete(f"rate_limit:{key}")
                else:
                    keys = self._redis_client.keys("rate_limit:*")
                    if keys:
                        self._redis_client.delete(*keys)
            except Exception:
                pass
        self._fallback.reset(key)


def _build_limiter():
    if getattr(settings, "REDIS_URL", None):
        return RedisSlidingWindowRateLimiter(settings.REDIS_URL)
    return InMemorySlidingWindowRateLimiter()


limiter = _build_limiter()


def enforce_rate_limit(
    request: Request,
    action: str,
    max_requests: int = 5,
    window_seconds: int = 60,
    allow_test_bypass: bool = True,
) -> None:
    """
    Enforce rate limiting on an incoming HTTP request.
    Raises HTTPException(429) with Retry-After header if threshold exceeded.
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
