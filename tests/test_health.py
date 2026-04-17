import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

import backend.middleware.rate_limit as rl_module


@pytest.mark.asyncio
async def test_health_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "degraded")
    assert "mongo" in data
    assert "redis" in data
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_health_no_auth_required(client):
    """Health endpoint must be publicly accessible — no API key needed."""
    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_health_redis_disabled_when_no_client(client):
    """When REDIS_URL is unset, redis field is 'disabled' and status is still ok."""
    with patch.object(rl_module, "_redis_client", None):
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["redis"] == "disabled"
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_health_redis_connected(client):
    """When Redis is reachable, redis field is 'connected'."""
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    with patch.object(rl_module, "_redis_client", mock_redis):
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["redis"] == "connected"
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_health_redis_unreachable_returns_degraded(client):
    """When Redis ping fails, redis is 'unreachable' and status is 'degraded'."""
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(side_effect=ConnectionError("Redis down"))
    with patch.object(rl_module, "_redis_client", mock_redis):
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["redis"] == "unreachable"
    assert data["status"] == "degraded"


@pytest.mark.asyncio
async def test_health_mongo_unreachable_returns_degraded(client):
    """When MongoDB ping fails, mongo is 'unreachable' and status is 'degraded'."""
    from backend.main import app

    with patch("backend.services.mongo.get_client") as mock_get_client:
        mock_admin = MagicMock()
        mock_admin.command = AsyncMock(side_effect=Exception("Mongo down"))
        mock_client = MagicMock()
        mock_client.admin = mock_admin
        mock_get_client.return_value = mock_client

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            resp = await ac.get("/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["mongo"] == "unreachable"
    assert data["status"] == "degraded"


@pytest.mark.asyncio
async def test_health_response_includes_timestamp(client):
    """Timestamp must be present and ISO-formatted."""
    resp = await client.get("/health")
    data = resp.json()
    assert "T" in data["timestamp"]  # ISO 8601 contains 'T' separator
    assert data["timestamp"].endswith("+00:00") or data["timestamp"].endswith("Z") or "+" in data["timestamp"]
