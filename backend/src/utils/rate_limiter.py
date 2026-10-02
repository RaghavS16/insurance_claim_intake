"""Distributed, atomic rate limiting."""
import threading
import time
from collections import defaultdict, deque
from typing import Dict, Optional, Tuple
from fastapi import HTTPException, Request, status
from src.config import settings
from src.utils.logger import app_logger

logger = app_logger

class InMemorySlidingWindowRateLimiter:
    def __init__(self):
        self._lock = threading.Lock()
        self._requests: Dict[str, deque] = defaultdict(deque)
    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> Tuple[bool, int, int]:
        now=time.time(); start=now-window_seconds
        with self._lock:
            q=self._requests[key]
            while q and q[0] <= start: q.popleft()
            if len(q) < max_requests:
                q.append(now); return True, max_requests-len(q), 0
            return False, 0, max(1, int(q[0]+window_seconds-now))
    def reset(self,key:Optional[str]=None):
        with self._lock:
            self._requests.pop(key,None) if key else self._requests.clear()

class RedisSlidingWindowRateLimiter:
    def __init__(self, redis_url:str):
        self._redis_url=redis_url; self._redis_client=None; self._fallback=InMemorySlidingWindowRateLimiter(); self._connect()
    def _connect(self):
        try:
            import redis
            self._redis_client=redis.Redis.from_url(self._redis_url,decode_responses=True,socket_timeout=2.0,socket_connect_timeout=2.0)
            self._redis_client.ping()
        except Exception as exc:
            logger.warning("Redis rate limiter unavailable: %s",type(exc).__name__)
            self._redis_client=None
    def is_allowed(self,key:str,max_requests:int,window_seconds:int)->Tuple[bool,int,int]:
        if not self._redis_client:
            if settings.ENVIRONMENT in ("production","staging") and settings.SECURITY_FAIL_CLOSED:
                raise HTTPException(status_code=503,detail="Rate limiting service temporarily unavailable.")
            return self._fallback.is_allowed(key,max_requests,window_seconds)
        now=time.time(); redis_key=f"rate_limit:{key}"
        script="""
        local key=KEYS[1]
        local now=tonumber(ARGV[1])
        local start=tonumber(ARGV[2])
        local limit=tonumber(ARGV[3])
        local window=tonumber(ARGV[4])
        redis.call('ZREMRANGEBYSCORE',key,0,start)
        local count=redis.call('ZCARD',key)
        if count >= limit then
          local oldest=redis.call('ZRANGE',key,0,0,'WITHSCORES')
          local retry=window
          if oldest[2] then retry=math.max(1,math.ceil(tonumber(oldest[2])+window-now)) end
          return {0,0,retry}
        end
        local member=tostring(now)..':'..tostring(math.random())
        redis.call('ZADD',key,now,member)
        redis.call('EXPIRE',key,window+5)
        return {1,limit-count-1,0}
        """
        try:
            allowed,remaining,retry=self._redis_client.eval(script,1,redis_key,now,now-window_seconds,max_requests,window_seconds)
            return bool(allowed),int(remaining),int(retry)
        except Exception as exc:
            logger.exception("Redis rate limiter failure.")
            if settings.ENVIRONMENT in ("production","staging") and settings.SECURITY_FAIL_CLOSED:
                raise HTTPException(status_code=503,detail="Rate limiting service temporarily unavailable.") from exc
            return self._fallback.is_allowed(key,max_requests,window_seconds)
    def reset(self,key:Optional[str]=None):
        if self._redis_client:
            try:
                if key: self._redis_client.delete(f"rate_limit:{key}")
            except Exception: logger.debug("Rate limiter reset failed.",exc_info=True)
        self._fallback.reset(key)

def _build_limiter():
    return RedisSlidingWindowRateLimiter(settings.REDIS_URL) if settings.REDIS_URL else InMemorySlidingWindowRateLimiter()
limiter=_build_limiter()

def enforce_rate_limit(request:Request,action:str,max_requests:int=5,window_seconds:int=60,allow_test_bypass:bool=True)->None:
    if allow_test_bypass and settings.ENVIRONMENT=="test" and not request.headers.get("X-Test-Enforce-Rate-Limit"): return
    ip=request.client.host if request.client else "unknown"
    # Account-aware routes can add X-Rate-Limit-Identity from trusted server code.
    identity=request.headers.get("X-Rate-Limit-Identity") or ip
    allowed,remaining,retry=limiter.is_allowed(f"{action}:{identity}",max_requests,window_seconds)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,detail="Too many requests. Please try again later.",headers={"Retry-After":str(retry)})
