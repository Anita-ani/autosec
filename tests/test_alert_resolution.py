"""
Alert resolution flow tests.

Covers:
  - PATCH /alerts/{id}/resolve → 200, fires alert.resolved webhook
  - 404 for unknown alert ID
  - 400 for invalid alert ID format
  - Analyst JWT cannot resolve (403)
  - Operator JWT can resolve
"""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

from backend.main import app
from tests.conftest import HEADERS, jwt_headers

OPERATOR_HEADERS = jwt_headers("operator")
ANALYST_HEADERS  = jwt_headers("analyst")


@pytest.mark.asyncio
async def test_resolve_alert_returns_200(mock_mongo, mock_n8n):
    alert_id = str(ObjectId())
    with patch("backend.services.webhooks.fire", new_callable=AsyncMock) as mock_fire:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                               headers=HEADERS) as ac:
            r = await ac.patch(f"/alerts/{alert_id}/resolve")
    assert r.status_code == 200
    assert r.json()["status"] == "resolved"
    assert r.json()["alert_id"] == alert_id


@pytest.mark.asyncio
async def test_resolve_fires_webhook(mock_mongo, mock_n8n):
    alert_id = str(ObjectId())
    with patch("backend.services.webhooks.fire", new_callable=AsyncMock) as mock_fire:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                               headers=HEADERS) as ac:
            await ac.patch(f"/alerts/{alert_id}/resolve")
    mock_fire.assert_awaited_once()
    call_args = mock_fire.call_args
    assert call_args[0][0] == "alert.resolved"
    assert call_args[0][1]["alert_id"] == alert_id


@pytest.mark.asyncio
async def test_resolve_not_found(mock_mongo, mock_n8n):
    mock_mongo.alerts.update_one = AsyncMock(
        return_value=MagicMock(matched_count=0)
    )
    alert_id = str(ObjectId())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           headers=HEADERS) as ac:
        r = await ac.patch(f"/alerts/{alert_id}/resolve")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_resolve_invalid_id(mock_mongo, mock_n8n):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           headers=HEADERS) as ac:
        r = await ac.patch("/alerts/not-an-objectid/resolve")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_resolve_requires_operator_not_analyst(mock_mongo, mock_n8n):
    alert_id = str(ObjectId())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.patch(f"/alerts/{alert_id}/resolve", headers=ANALYST_HEADERS)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_resolve_operator_jwt_succeeds(mock_mongo, mock_n8n):
    alert_id = str(ObjectId())
    with patch("backend.services.webhooks.fire", new_callable=AsyncMock):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.patch(f"/alerts/{alert_id}/resolve", headers=OPERATOR_HEADERS)
    assert r.status_code == 200
