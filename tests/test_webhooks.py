"""
Tests for webhook CRUD routes and outbound delivery service.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

import backend.services.webhooks as webhook_svc

VALID_WEBHOOK = {
    "url": "https://hooks.example.com/autosec",
    "events": ["alert.created"],
}


# ── POST /webhooks ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_webhook_returns_201(client):
    resp = await client.post("/webhooks", json=VALID_WEBHOOK)
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert data["url"] == VALID_WEBHOOK["url"]


@pytest.mark.asyncio
async def test_create_webhook_invalid_url(client):
    resp = await client.post("/webhooks", json={**VALID_WEBHOOK, "url": "not-a-url"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_webhook_invalid_event_type(client):
    resp = await client.post("/webhooks", json={**VALID_WEBHOOK, "events": ["unknown.event"]})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_webhook_requires_auth(client):
    from httpx import AsyncClient, ASGITransport
    from backend.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/webhooks", json=VALID_WEBHOOK)
    assert resp.status_code == 401


# ── GET /webhooks ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_webhooks_returns_200(client):
    resp = await client.get("/webhooks")
    assert resp.status_code == 200
    data = resp.json()
    assert "webhooks" in data
    assert "count" in data


# ── DELETE /webhooks/{id} ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_webhook_returns_204(client, mock_mongo):
    mock_mongo.webhooks.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
    resp = await client.delete("/webhooks/64f1a2b3c4d5e6f7a8b9c0d1")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_webhook_not_found(client, mock_mongo):
    mock_mongo.webhooks.delete_one = AsyncMock(return_value=MagicMock(deleted_count=0))
    resp = await client.delete("/webhooks/64f1a2b3c4d5e6f7a8b9c0d1")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_webhook_invalid_id(client):
    resp = await client.delete("/webhooks/not-a-valid-id")
    assert resp.status_code == 400


# ── PATCH /webhooks/{id} ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_toggle_webhook_disable(client, mock_mongo):
    mock_mongo.webhooks.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    resp = await client.patch("/webhooks/64f1a2b3c4d5e6f7a8b9c0d1?enabled=false")
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


@pytest.mark.asyncio
async def test_toggle_webhook_not_found(client, mock_mongo):
    mock_mongo.webhooks.update_one = AsyncMock(return_value=MagicMock(matched_count=0))
    resp = await client.patch("/webhooks/64f1a2b3c4d5e6f7a8b9c0d1?enabled=true")
    assert resp.status_code == 404


# ── Delivery service ──────────────────────────────────────────────────────────
#
# We patch `_deliver` at the service level to avoid httpx context-manager
# wiring complexity. This tests the dispatch logic in `fire()` cleanly.

def _make_webhooks_db(hooks: list[dict]):
    from tests.conftest import _async_cursor
    fake_col = MagicMock()
    fake_col.find = MagicMock(return_value=_async_cursor(hooks))
    fake_db = MagicMock()
    fake_db.webhooks = fake_col
    return fake_db


@pytest.mark.asyncio
async def test_fire_delivers_to_subscribed_hook():
    """fire() calls _deliver once for each matching hook."""
    hook = {"url": "https://example.com/hook", "events": ["alert.created"], "enabled": True, "secret": None}
    db = _make_webhooks_db([hook])

    with patch("backend.services.webhooks.mongo.get_db", return_value=db), \
         patch("backend.services.webhooks._deliver", new_callable=AsyncMock) as mock_deliver:
        await webhook_svc.fire("alert.created", {"alert_type": "brute_force_detected"})

    mock_deliver.assert_called_once()
    delivered_hook = mock_deliver.call_args[0][0]
    assert delivered_hook["url"] == hook["url"]


@pytest.mark.asyncio
async def test_fire_no_hooks_registered():
    """When the cursor returns no hooks, _deliver is never called."""
    db = _make_webhooks_db([])

    with patch("backend.services.webhooks.mongo.get_db", return_value=db), \
         patch("backend.services.webhooks._deliver", new_callable=AsyncMock) as mock_deliver:
        await webhook_svc.fire("alert.created", {})

    mock_deliver.assert_not_called()


@pytest.mark.asyncio
async def test_fire_sends_secret_in_hook_dict():
    """_deliver receives the hook dict including the secret so it can set the header."""
    hook = {"url": "https://example.com/hook", "events": ["alert.created"],
            "enabled": True, "secret": "my-secret-token"}
    db = _make_webhooks_db([hook])

    with patch("backend.services.webhooks.mongo.get_db", return_value=db), \
         patch("backend.services.webhooks._deliver", new_callable=AsyncMock) as mock_deliver:
        await webhook_svc.fire("alert.created", {"alert_type": "brute_force_detected"})

    delivered_hook = mock_deliver.call_args[0][0]
    assert delivered_hook["secret"] == "my-secret-token"


@pytest.mark.asyncio
async def test_fire_does_not_raise_on_delivery_failure():
    """asyncio.gather(return_exceptions=True) swallows _deliver exceptions."""
    hook = {"url": "https://example.com/hook", "events": ["alert.created"], "enabled": True, "secret": None}
    db = _make_webhooks_db([hook])

    with patch("backend.services.webhooks.mongo.get_db", return_value=db), \
         patch("backend.services.webhooks._deliver",
               new_callable=AsyncMock, side_effect=httpx.ConnectError("refused")):
        # Must not raise
        await webhook_svc.fire("alert.created", {"alert_type": "brute_force_detected"})


@pytest.mark.asyncio
async def test_fire_delivers_to_multiple_hooks():
    """fire() calls _deliver once per matching hook."""
    hooks = [
        {"url": "https://a.example.com/hook", "events": ["alert.created"], "enabled": True, "secret": None},
        {"url": "https://b.example.com/hook", "events": ["alert.created"], "enabled": True, "secret": None},
    ]
    db = _make_webhooks_db(hooks)

    with patch("backend.services.webhooks.mongo.get_db", return_value=db), \
         patch("backend.services.webhooks._deliver", new_callable=AsyncMock) as mock_deliver:
        await webhook_svc.fire("alert.created", {"alert_type": "brute_force_detected"})

    assert mock_deliver.call_count == 2
