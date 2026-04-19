"""
Role-based access control tests.

Covers:
  - API key (service account) → operator-level access on all routes
  - JWT operator role → full access
  - JWT analyst role → read-only (GET allowed, POST/PATCH/DELETE → 403)
  - No credentials → 401/403 on protected routes
  - Invalid/expired JWT → 401
  - Public routes remain accessible without any auth
"""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from bson import ObjectId

from backend.main import app
from tests.conftest import HEADERS, jwt_headers, make_jwt


# ── Helpers ───────────────────────────────────────────────────────────────────

OPERATOR_HEADERS = jwt_headers("operator")
ANALYST_HEADERS  = jwt_headers("analyst")
NO_AUTH_HEADERS  = {}


@pytest.fixture
def valid_alert_id():
    return str(ObjectId())


@pytest.fixture
def valid_webhook_id():
    return str(ObjectId())


# ── Public routes (no auth required) ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_is_public(mock_mongo, mock_n8n):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/health")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_auth_token_is_public(mock_mongo, mock_n8n):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Wrong credentials — still not a 401 from middleware
        r = await ac.post("/auth/token", json={"username": "x", "password": "y"})
    assert r.status_code == 401   # from route, not middleware


# ── No credentials → 401 ─────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,body", [
    ("GET",    "/events",   None),
    ("POST",   "/events",   {"event_type": "login_failed", "source_ip": "1.2.3.4", "status": "failed"}),
    ("GET",    "/alerts",   None),
    ("GET",    "/stats",    None),
    ("GET",    "/webhooks", None),
    ("GET",    "/block-ip", None),
])
async def test_no_auth_rejected(method, path, body, mock_mongo, mock_n8n, mock_geo):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        if method == "GET":
            r = await ac.get(path, headers=NO_AUTH_HEADERS)
        else:
            r = await ac.post(path, json=body, headers=NO_AUTH_HEADERS)
    assert r.status_code in (401, 403)


# ── Invalid JWT → 401 ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalid_jwt_rejected(mock_mongo, mock_n8n):
    bad_headers = {"Authorization": "Bearer not.a.valid.token"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/alerts", headers=bad_headers)
    assert r.status_code == 401


# ── API key (service account) has operator access ────────────────────────────

@pytest.mark.asyncio
async def test_api_key_can_post_event(mock_mongo, mock_n8n, mock_geo):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           headers=HEADERS) as ac:
        r = await ac.post("/events", json={
            "event_type": "login_failed", "source_ip": "1.2.3.4", "status": "failed"
        })
    assert r.status_code == 202


@pytest.mark.asyncio
async def test_api_key_can_get_stats(mock_mongo, mock_n8n):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           headers=HEADERS) as ac:
        r = await ac.get("/stats")
    assert r.status_code == 200


# ── JWT operator has full access ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_operator_jwt_can_post_event(mock_mongo, mock_n8n, mock_geo):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post("/events", json={
            "event_type": "login_failed", "source_ip": "1.2.3.4", "status": "failed"
        }, headers=OPERATOR_HEADERS)
    assert r.status_code == 202


@pytest.mark.asyncio
async def test_operator_jwt_can_get_alerts(mock_mongo, mock_n8n):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/alerts", headers=OPERATOR_HEADERS)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_operator_jwt_can_block_ip(mock_mongo, mock_n8n):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post("/block-ip",
                          json={"ip": "5.6.7.8", "reason": "test"},
                          headers=OPERATOR_HEADERS)
    assert r.status_code == 201


# ── JWT analyst has read-only access ─────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/events", "/alerts", "/stats", "/webhooks", "/block-ip"])
async def test_analyst_can_read(path, mock_mongo, mock_n8n):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get(path, headers=ANALYST_HEADERS)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_analyst_cannot_post_event(mock_mongo, mock_n8n, mock_geo):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post("/events", json={
            "event_type": "login_failed", "source_ip": "1.2.3.4", "status": "failed"
        }, headers=ANALYST_HEADERS)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_analyst_cannot_block_ip(mock_mongo, mock_n8n):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post("/block-ip",
                          json={"ip": "5.6.7.8", "reason": "test"},
                          headers=ANALYST_HEADERS)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_analyst_cannot_create_alert(mock_mongo, mock_n8n):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post("/alerts", json={
            "alert_type": "brute_force", "source_ip": "1.2.3.4",
            "severity": "high", "message": "test"
        }, headers=ANALYST_HEADERS)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_analyst_cannot_resolve_alert(mock_mongo, mock_n8n, valid_alert_id):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.patch(f"/alerts/{valid_alert_id}/resolve", headers=ANALYST_HEADERS)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_analyst_cannot_create_webhook(mock_mongo, mock_n8n):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post("/webhooks", json={
            "url": "https://example.com/hook", "events": ["alert.created"]
        }, headers=ANALYST_HEADERS)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_analyst_cannot_delete_webhook(mock_mongo, mock_n8n, valid_webhook_id):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.delete(f"/webhooks/{valid_webhook_id}", headers=ANALYST_HEADERS)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_analyst_cannot_replay(mock_mongo, mock_n8n):
    with patch("backend.services.replay.run", new_callable=AsyncMock,
               return_value={"events_scanned": 0, "rules_fired": [], "dry_run": True}):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.post("/replay", json={
                "since": "2026-01-01T00:00:00Z", "until": "2026-01-01T01:00:00Z"
            }, headers=ANALYST_HEADERS)
    assert r.status_code == 403
