"""
Token-bucket rate limiter per IP address.
Defaults: 60 requests / 60 seconds per IP.
Override via env: RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SECONDS.

Storage backends (selected automatically):
  Redis   — when REDIS_URL is set; sliding window via sorted sets; works across
             multiple workers; keys auto-expire so no cleanup task is needed.
  In-memory — fallback when REDIS_URL is unset (dev / test). Same sliding window
               logic but per-process only. Background cleanup task evicts stale
               entries to prevent unbounded growth.

Fail-open: if the Redis call raises for any reason the request is allowed through
and a warning is logged. Prefer availability over accidental total lockout.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import defaultdict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

_MAX_REQUESTS = int(os.environ.get("RATE_LIMIT_REQUESTS", "60"))
_WINDOW = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))

# ── Redis client (set by init_redis(), cleared by close_redis()) ──────────────

_redis_client = None


async def init_redis() -> None:
    global _redis_client
    url = os.environ.get("REDIS_URL", "").strip()
    if not url:
        logger.info("REDIS_URL not set — rate limiter using in-memory fallback")
        return
    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url(url, decode_responses=True, socket_connect_timeout=3)
        await client.ping()
        _redis_client = client
        logger.info("Rate limiter connected to Redis at %s", url)
    except Exception as exc:
        logger.warning("Redis connection failed (%s) — falling back to in-memory rate limiter", exc)


async def close_redis() -> None:
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None


# ── Redis path — sliding window via sorted sets ───────────────────────────────

async def _redis_is_limited(ip: str) -> bool:
    """
    Returns True if the IP is over the rate limit.
    Uses a Redis sorted set keyed by `rl:{ip}`.
    Fails open (returns False) on any Redis error.
    """
    now = time.time()
    window_start = now - _WINDOW
    key = f"rl:{ip}"
    member = str(now)

    try:
        async with _redis_client.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, "-inf", window_start)   # evict expired entries
            pipe.zadd(key, {member: now})                       # record this request
            pipe.zcard(key)                                     # count in window
            pipe.expire(key, _WINDOW + 1)                       # auto-cleanup
            results = await pipe.execute()
        count: int = results[2]
        return count > _MAX_REQUESTS
    except Exception as exc:
        logger.warning("Redis rate limit check failed (fail-open): %s", exc)
        return False


# ── In-memory fallback — sliding window per process ───────────────────────────

_request_log: dict[str, list[float]] = defaultdict(list)
_lock = asyncio.Lock()


def _memory_is_limited(ip: str, now: float) -> bool:
    """Mutates _request_log. Must be called inside _lock."""
    pruned = [t for t in _request_log[ip] if now - t < _WINDOW]
    if len(pruned) >= _MAX_REQUESTS:
        _request_log[ip] = pruned
        return True
    pruned.append(now)
    if pruned:
        _request_log[ip] = pruned
    else:
        _request_log.pop(ip, None)
    return False


async def cleanup_stale_ips() -> None:
    """
    Background task for the in-memory fallback only.
    Evicts IP entries that have fully aged out of the window.
    Called from app lifespan; exits when the task is cancelled.
    """
    while True:
        await asyncio.sleep(_WINDOW)
        if _redis_client:
            return  # Redis handles its own expiry — nothing to do
        now = time.monotonic()
        async with _lock:
            stale = [
                ip for ip, ts in _request_log.items()
                if not any(now - t < _WINDOW for t in ts)
            ]
            for ip in stale:
                del _request_log[ip]
        if stale:
            logger.debug("Rate limiter: evicted %d stale in-memory IP entries", len(stale))


# ── Middleware ────────────────────────────────────────────────────────────────

def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        ip = _client_ip(request)

        if _redis_client is not None:
            limited = await _redis_is_limited(ip)
        else:
            now = time.monotonic()
            async with _lock:
                limited = _memory_is_limited(ip, now)

        if limited:
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit exceeded: {_MAX_REQUESTS} requests per {_WINDOW}s"},
                headers={"Retry-After": str(_WINDOW)},
            )

        return await call_next(request)
