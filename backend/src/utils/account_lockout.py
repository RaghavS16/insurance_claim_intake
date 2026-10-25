"""Account failure counter and temporary lockout for authentication routes."""
from __future__ import annotations

import hashlib
import threading
import time
from typing import Dict, Tuple
from fastapi import HTTPException, status
from src.config import settings
from src.utils.logger import app_logger

logger = app_logger

LOCKOUT_WINDOW_SECONDS = 15 * 60  # 15 minutes
LOCKOUT_MAX_FAILURES = 5          # 5 failures
LOCKOUT_DURATION_SECONDS = 15 * 60 # 15 minutes lock


class InMemoryAccountLockout:
    def __init__(self):
        self._lock = threading.Lock()
        # key -> (failure_count, first_failure_time, locked_until)
        self._records: Dict[str, Tuple[int, float, float]] = {}

    def is_locked(self, key: str) -> Tuple[bool, int]:
        now = time.time()
        with self._lock:
            rec = self._records.get(key)
            if not rec:
                return False, 0
            count, first_time, locked_until = rec
            if locked_until > now:
                return True, max(1, int(locked_until - now))
            # Clean expired window
            if now - first_time > LOCKOUT_WINDOW_SECONDS:
                self._records.pop(key, None)
                return False, 0
            if count >= LOCKOUT_MAX_FAILURES:
                # Lock expired
                self._records.pop(key, None)
                return False, 0
            return False, 0

    def record_failure(self, key: str) -> int:
        now = time.time()
        with self._lock:
            rec = self._records.get(key)
            if not rec:
                self._records[key] = (1, now, 0)
                return 1
            count, first_time, locked_until = rec
            if now - first_time > LOCKOUT_WINDOW_SECONDS:
                count = 1
                first_time = now
                locked_until = 0
            else:
                count += 1
                if count >= LOCKOUT_MAX_FAILURES:
                    locked_until = now + LOCKOUT_DURATION_SECONDS
            self._records[key] = (count, first_time, locked_until)
            return count

    def record_success(self, key: str) -> None:
        with self._lock:
            self._records.pop(key, None)

    def unlock(self, key: str) -> None:
        with self._lock:
            self._records.pop(key, None)


class RedisAccountLockout:
    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._redis_client = None
        self._fallback = InMemoryAccountLockout()
        self._connect()

    def _connect(self):
        try:
            import redis
            self._redis_client = redis.Redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
            )
            self._redis_client.ping()
        except Exception as exc:
            logger.warning("Redis account lockout unavailable: %s", type(exc).__name__)
            self._redis_client = None

    def is_locked(self, key: str) -> Tuple[bool, int]:
        if not self._redis_client:
            if settings.ENVIRONMENT in ("production", "staging") and settings.SECURITY_FAIL_CLOSED:
                raise HTTPException(status_code=503, detail="Authentication service temporarily unavailable.")
            return self._fallback.is_locked(key)
        try:
            lock_key = f"auth_lock:{key}"
            ttl = self._redis_client.ttl(lock_key)
            if ttl is not None and ttl > 0:
                return True, int(ttl)
            fail_key = f"auth_fail:{key}"
            count_str = self._redis_client.get(fail_key)
            if count_str and int(count_str) >= LOCKOUT_MAX_FAILURES:
                fail_ttl = self._redis_client.ttl(fail_key)
                return True, max(1, int(fail_ttl if fail_ttl and fail_ttl > 0 else LOCKOUT_DURATION_SECONDS))
            return False, 0
        except Exception as exc:
            logger.exception("Redis account lockout check failure")
            if settings.ENVIRONMENT in ("production", "staging") and settings.SECURITY_FAIL_CLOSED:
                raise HTTPException(status_code=503, detail="Authentication service temporarily unavailable.") from exc
            return self._fallback.is_locked(key)

    def record_failure(self, key: str) -> int:
        if not self._redis_client:
            if settings.ENVIRONMENT in ("production", "staging") and settings.SECURITY_FAIL_CLOSED:
                raise HTTPException(status_code=503, detail="Authentication service temporarily unavailable.")
            return self._fallback.record_failure(key)
        try:
            fail_key = f"auth_fail:{key}"
            pipe = self._redis_client.pipeline()
            pipe.incr(fail_key)
            pipe.ttl(fail_key)
            results = pipe.execute()
            count = int(results[0])
            ttl = int(results[1])
            if ttl == -1 or count == 1:
                self._redis_client.expire(fail_key, LOCKOUT_WINDOW_SECONDS)
            if count >= LOCKOUT_MAX_FAILURES:
                lock_key = f"auth_lock:{key}"
                self._redis_client.set(lock_key, "locked", ex=LOCKOUT_DURATION_SECONDS)
            return count
        except Exception as exc:
            logger.exception("Redis record failure error")
            if settings.ENVIRONMENT in ("production", "staging") and settings.SECURITY_FAIL_CLOSED:
                raise HTTPException(status_code=503, detail="Authentication service temporarily unavailable.") from exc
            return self._fallback.record_failure(key)

    def record_success(self, key: str) -> None:
        if self._redis_client:
            try:
                self._redis_client.delete(f"auth_fail:{key}", f"auth_lock:{key}")
            except Exception:
                pass
        self._fallback.record_success(key)

    def unlock(self, key: str) -> None:
        if self._redis_client:
            try:
                self._redis_client.delete(f"auth_fail:{key}", f"auth_lock:{key}")
            except Exception:
                pass
        self._fallback.unlock(key)


def _build_lockout_manager():
    if settings.REDIS_URL:
        return RedisAccountLockout(settings.REDIS_URL)
    return InMemoryAccountLockout()


lockout_manager = _build_lockout_manager()


def hash_identifier(identifier: str) -> str:
    return hashlib.sha256(identifier.lower().strip().encode("utf-8")).hexdigest()


def check_account_lock(action: str, identifier: str) -> None:
    """Check if account is temporarily locked due to repeated failures."""
    key = f"{action}:{hash_identifier(identifier)}"
    locked, retry_after = lockout_manager.is_locked(key)
    if locked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts. Account is temporarily locked. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )


def record_auth_failure(action: str, identifier: str) -> int:
    """Record a failure for the account and trigger lock if threshold reached."""
    key = f"{action}:{hash_identifier(identifier)}"
    return lockout_manager.record_failure(key)


def record_auth_success(action: str, identifier: str) -> None:
    """Clear failure counter and lock for the account."""
    key = f"{action}:{hash_identifier(identifier)}"
    lockout_manager.record_success(key)


def unlock_account(action: str, identifier: str) -> None:
    """Explicitly unlock an account."""
    key = f"{action}:{hash_identifier(identifier)}"
    lockout_manager.unlock(key)
