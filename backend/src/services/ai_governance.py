"""Centralized AI governance, tenant quotas, concurrency controls, and model allowlisting."""
from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from collections import defaultdict

from fastapi import HTTPException

from src.config import settings

_local_windows: dict[str, list[float]] = defaultdict(list)
_local_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_local_concurrency: dict[str, int] = defaultdict(int)
_local_budget: dict[str, int] = defaultdict(int)


def assert_model_allowed(model_name: str) -> None:
    allowed = settings.ai_allowed_models_list
    if settings.ENVIRONMENT in {"production", "staging"} and settings.AI_REQUIRE_MODEL_GOVERNANCE_IN_PRODUCTION:
        if not allowed:
            raise RuntimeError("No approved AI models are configured.")
        if model_name not in allowed:
            raise RuntimeError(f"AI model '{model_name}' is not approved for this environment.")


async def _redis_client():
    if not settings.REDIS_URL:
        return None
    import redis.asyncio as redis
    try:
        client = redis.from_url(settings.REDIS_URL, decode_responses=True, socket_timeout=2.0, socket_connect_timeout=2.0)
        await client.ping()
        return client
    except Exception:
        return None


async def _consume_window(tenant_id: str, operation: str, limit: int, window_seconds: int) -> None:
    redis_client = await _redis_client()
    key = f"ai:rate:{tenant_id}:{operation}"
    now = time.time()
    if redis_client is not None:
        try:
            script = """
            local key=KEYS[1]
            local now=tonumber(ARGV[1])
            local window=tonumber(ARGV[2])
            local limit=tonumber(ARGV[3])
            redis.call('ZREMRANGEBYSCORE',key,0,now-window)
            local count=redis.call('ZCARD',key)
            if count >= limit then return 0 end
            redis.call('ZADD',key,now,tostring(now)..':'..tostring(math.random()))
            redis.call('EXPIRE',key,window+5)
            return 1
            """
            ok = await redis_client.eval(script, 1, key, now, window_seconds, limit)
            await redis_client.close()
            if int(ok or 0) != 1:
                raise HTTPException(status_code=429, detail="AI request quota exceeded for this tenant.")
            return
        except HTTPException:
            raise
        except Exception:
            try:
                await redis_client.close()
            except Exception:
                pass
            if settings.ENVIRONMENT in {"production", "staging"} and settings.SECURITY_FAIL_CLOSED:
                raise HTTPException(status_code=503, detail="AI quota service temporarily unavailable.")

    async with _local_locks[key]:
        values = [stamp for stamp in _local_windows[key] if stamp > now - window_seconds]
        if len(values) >= limit:
            raise HTTPException(status_code=429, detail="AI request quota exceeded for this tenant.")
        values.append(now)
        _local_windows[key] = values

async def _reserve_budget(tenant_id: str, estimated_tokens: int) -> None:
    if estimated_tokens <= 0:
        return
    key = f"ai:budget:{tenant_id}"
    limit = settings.AI_MAX_ESTIMATED_TOKENS_PER_TENANT_PER_DAY
    redis_client = await _redis_client()
    if redis_client is not None:
        try:
            current = await redis_client.incrby(key, int(estimated_tokens))
            now = time.time()
            seconds_until_reset = max(60, int(86400 - (now % 86400)))
            await redis_client.expire(key, seconds_until_reset)
            if int(current) > limit:
                await redis_client.decrby(key, int(estimated_tokens))
                raise HTTPException(status_code=429, detail="AI daily token budget exceeded for this tenant.")
        finally:
            await redis_client.close()
        return
    async with _local_locks[key]:
        current = _local_budget[key]
        if current + estimated_tokens > limit:
            raise HTTPException(status_code=429, detail="AI daily token budget exceeded for this tenant.")
        _local_budget[key] = current + estimated_tokens


@asynccontextmanager
async def tenant_ai_guard(tenant_id: str, *, operation: str = "claim_turn", max_requests: int | None = None, max_concurrent: int | None = None, estimated_tokens: int = 0):
    tenant = str(tenant_id or "").strip()
    if not tenant:
        raise HTTPException(status_code=403, detail="Tenant context is required for AI operations.")
    rate_limit = max_requests or (
        settings.AI_MAX_RAG_REQUESTS_PER_TENANT_PER_MINUTE
        if operation.startswith("rag")
        else settings.AI_MAX_TURNS_PER_TENANT_PER_MINUTE
    )
    concurrency_limit = max_concurrent or settings.AI_MAX_CONCURRENT_TURNS_PER_TENANT

    await _consume_window(tenant, operation, rate_limit, 60)
    await _reserve_budget(tenant, estimated_tokens)
    lock_key = f"{tenant}:{operation}:concurrency"
    redis_client = await _redis_client()
    acquired = False
    if redis_client is not None:
        try:
            lease = await redis_client.incr(lock_key)
            await redis_client.expire(lock_key, 120)
            if int(lease) > concurrency_limit:
                await redis_client.decr(lock_key)
                raise HTTPException(status_code=429, detail="AI concurrency limit reached for this tenant.")
            acquired = True
        finally:
            await redis_client.close()
    else:
        async with _local_locks[lock_key]:
            current = _local_concurrency[lock_key]
            if current >= concurrency_limit:
                raise HTTPException(status_code=429, detail="AI concurrency limit reached for this tenant.")
            _local_concurrency[lock_key] = current + 1
            acquired = True
    try:
        yield
    finally:
        if not acquired:
            return
        if settings.REDIS_URL:
            client = await _redis_client()
            if client is not None:
                try:
                    await client.decr(lock_key)
                finally:
                    await client.close()
        else:
            async with _local_locks[lock_key]:
                _local_concurrency[lock_key] = max(0, _local_concurrency[lock_key] - 1)
