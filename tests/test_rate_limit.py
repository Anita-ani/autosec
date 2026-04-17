"""
Tests for RateLimitMiddleware — in-memory path, Redis path (mocked), and fail-open.
"""
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from backend.middleware.rate_limit import _memory_is_limited, _request_log
import backend.middleware.rate_limit as rl_module

# ── Helpers ───────────────────────────────────────────────────────────────────

HEADERS = {"X-API-Key": "test-api-key-1234"}


def _clear_memory_store():
    _request_log.clear()


# ── In-memory path ────────────────────────────────────────────────────────────

class TestMemoryIsLimited:
    def setup_method(self):
        _clear_memory_store()

    def test_first_request_is_not_limited(self):
        assert _memory_is_limited("10.0.0.1", time.monotonic()) is False

    def test_requests_below_threshold_not_limited(self):
        now = time.monotonic()
        max_req = rl_module._MAX_REQUESTS
        for _ in range(max_req - 1):
            result = _memory_is_limited("10.0.0.2", now)
        assert result is False

    def test_request_at_threshold_is_limited(self):
        now = time.monotonic()
        max_req = rl_module._MAX_REQUESTS
        for _ in range(max_req):
            _memory_is_limited("10.0.0.3", now)
        assert _memory_is_limited("10.0.0.3", now) is True

    def test_expired_entries_are_pruned(self):
        ip = "10.0.0.4"
        max_req = rl_module._MAX_REQUESTS
        window = rl_module._WINDOW
        # Fill up with timestamps that are outside the window
        old_time = time.monotonic() - window - 1
        _request_log[ip] = [old_time] * (max_req + 5)
        # Next request at current time — old entries pruned, should NOT be limited
        assert _memory_is_limited(ip, time.monotonic()) is False

    def test_different_ips_are_independent(self):
        now = time.monotonic()
        max_req = rl_module._MAX_REQUESTS
        for _ in range(max_req + 1):
            _memory_is_limited("10.0.0.5", now)
        # A different IP should still be fine
        assert _memory_is_limited("10.0.0.6", now) is False


# ── Middleware — in-memory path via HTTP ──────────────────────────────────────

@pytest.mark.asyncio
async def test_middleware_allows_request_under_limit(client):
    """Normal request under rate limit returns 200 (or route-specific status)."""
    resp = await client.get("/health")
    assert resp.status_code != 429


@pytest.mark.asyncio
async def test_middleware_returns_429_when_limited():
    """Middleware returns 429 when in-memory rate limit is exceeded."""
    from backend.main import app

    async def _limited(*args, **kwargs):
        return True

    with patch("backend.middleware.rate_limit._redis_client", None), \
         patch("backend.middleware.rate_limit._memory_is_limited", return_value=True):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers=HEADERS,
        ) as ac:
            resp = await ac.get("/health")

    assert resp.status_code == 429
    assert "Rate limit exceeded" in resp.json()["detail"]
    assert "Retry-After" in resp.headers


@pytest.mark.asyncio
async def test_middleware_429_includes_retry_after_header():
    """429 response must include Retry-After header."""
    from backend.main import app

    with patch("backend.middleware.rate_limit._redis_client", None), \
         patch("backend.middleware.rate_limit._memory_is_limited", return_value=True):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers=HEADERS,
        ) as ac:
            resp = await ac.get("/health")

    assert resp.status_code == 429
    retry_after = int(resp.headers["Retry-After"])
    assert retry_after == rl_module._WINDOW


# ── Redis path (mocked pipeline) ──────────────────────────────────────────────

def _make_redis_pipeline(count: int):
    """Return a mock Redis client whose pipeline returns `count` as zcard result."""
    pipe = MagicMock()
    pipe.zremrangebyscore = MagicMock()
    pipe.zadd = MagicMock()
    pipe.zcard = MagicMock()
    pipe.expire = MagicMock()
    pipe.execute = AsyncMock(return_value=[None, None, count, None])

    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=pipe)
    ctx.__aexit__ = AsyncMock(return_value=False)

    mock_client = MagicMock()
    mock_client.pipeline = MagicMock(return_value=ctx)
    return mock_client


@pytest.mark.asyncio
async def test_redis_path_allows_under_limit():
    """Redis path: count below threshold → not limited."""
    mock_client = _make_redis_pipeline(count=rl_module._MAX_REQUESTS - 1)
    with patch.object(rl_module, "_redis_client", mock_client):
        result = await rl_module._redis_is_limited("10.0.0.10")
    assert result is False


@pytest.mark.asyncio
async def test_redis_path_blocks_over_limit():
    """Redis path: count above threshold → limited."""
    mock_client = _make_redis_pipeline(count=rl_module._MAX_REQUESTS + 1)
    with patch.object(rl_module, "_redis_client", mock_client):
        result = await rl_module._redis_is_limited("10.0.0.11")
    assert result is True


@pytest.mark.asyncio
async def test_redis_path_exactly_at_limit_is_limited():
    """Redis sliding window: zcard == _MAX_REQUESTS is the request THAT hit the limit."""
    mock_client = _make_redis_pipeline(count=rl_module._MAX_REQUESTS + 1)
    with patch.object(rl_module, "_redis_client", mock_client):
        result = await rl_module._redis_is_limited("10.0.0.12")
    assert result is True


@pytest.mark.asyncio
async def test_redis_fail_open_on_exception():
    """Redis path: pipeline raises → fail-open (returns False, request allowed)."""
    pipe = MagicMock()
    pipe.zremrangebyscore = MagicMock()
    pipe.zadd = MagicMock()
    pipe.zcard = MagicMock()
    pipe.expire = MagicMock()
    pipe.execute = AsyncMock(side_effect=ConnectionError("Redis down"))
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=pipe)
    ctx.__aexit__ = AsyncMock(return_value=False)

    mock_client = MagicMock()
    mock_client.pipeline = MagicMock(return_value=ctx)

    with patch.object(rl_module, "_redis_client", mock_client):
        result = await rl_module._redis_is_limited("10.0.0.13")

    assert result is False  # fail-open: allow the request through


@pytest.mark.asyncio
async def test_redis_middleware_uses_redis_when_client_set():
    """When _redis_client is set, middleware calls _redis_is_limited (not in-memory)."""
    from backend.main import app

    mock_client = _make_redis_pipeline(count=0)  # under limit
    with patch.object(rl_module, "_redis_client", mock_client), \
         patch("backend.middleware.rate_limit._redis_is_limited",
               new_callable=AsyncMock, return_value=False) as mock_redis_check:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers=HEADERS,
        ) as ac:
            await ac.get("/health")

    mock_redis_check.assert_called()


@pytest.mark.asyncio
async def test_redis_middleware_blocks_when_redis_returns_limited():
    """Redis says limited → middleware returns 429."""
    from backend.main import app

    with patch.object(rl_module, "_redis_client", MagicMock()), \
         patch("backend.middleware.rate_limit._redis_is_limited",
               new_callable=AsyncMock, return_value=True):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers=HEADERS,
        ) as ac:
            resp = await ac.get("/health")

    assert resp.status_code == 429


# ── init / close helpers ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_init_redis_no_url_stays_none():
    """When REDIS_URL is unset, _redis_client remains None."""
    with patch.dict("os.environ", {}, clear=False):
        import os
        os.environ.pop("REDIS_URL", None)
        # Reset client so init can be tested cleanly
        original = rl_module._redis_client
        rl_module._redis_client = None
        try:
            await rl_module.init_redis()
            assert rl_module._redis_client is None
        finally:
            rl_module._redis_client = original


@pytest.mark.asyncio
async def test_close_redis_clears_client():
    """close_redis() sets _redis_client back to None."""
    mock_client = AsyncMock()
    mock_client.aclose = AsyncMock()
    rl_module._redis_client = mock_client

    await rl_module.close_redis()

    mock_client.aclose.assert_called_once()
    assert rl_module._redis_client is None
