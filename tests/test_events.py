import pytest
from unittest.mock import AsyncMock, MagicMock

VALID_EVENT = {
    "event_type": "login_attempt",
    "source_ip": "192.168.1.100",
    "status": "failed",
    "user_id": "user-42",
    "timestamp": "2026-04-15T10:00:00Z",
}


@pytest.mark.asyncio
async def test_ingest_event_success(client):
    resp = await client.post("/events", json=VALID_EVENT)
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "accepted"
    assert "event_id" in data


@pytest.mark.asyncio
async def test_ingest_event_no_api_key(client):
    resp = await client.post("/events", json=VALID_EVENT)
    # With no key this should 401 — but conftest always injects the key via fixture;
    # this test uses a separate client without the header
    from httpx import AsyncClient, ASGITransport
    from backend.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/events", json=VALID_EVENT)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_ingest_event_wrong_api_key(client):
    from httpx import AsyncClient, ASGITransport
    from backend.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/events", json=VALID_EVENT, headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_ingest_event_invalid_ip(client):
    bad = {**VALID_EVENT, "source_ip": "not-an-ip"}
    resp = await client.post("/events", json=bad)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ingest_event_invalid_event_type_injection(client):
    """SQL/NoSQL injection attempt in event_type must be rejected."""
    bad = {**VALID_EVENT, "event_type": "login'; DROP TABLE events; --"}
    resp = await client.post("/events", json=bad)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ingest_event_invalid_status(client):
    bad = {**VALID_EVENT, "status": "hacked"}
    resp = await client.post("/events", json=bad)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ingest_event_missing_required_fields(client):
    resp = await client.post("/events", json={"event_type": "login_attempt"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_events(client):
    resp = await client.get("/events")
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data
    assert "count" in data


@pytest.mark.asyncio
async def test_list_events_limit_cap(client):
    """limit > 200 must be silently capped to 200."""
    resp = await client.get("/events?limit=9999")
    assert resp.status_code == 200


# ── Alert deduplication ───────────────────────────────────────────────────────
#
# NOTE: mock_mongo.events and mock_mongo.alerts both point to the same
# fake_collection object (see conftest.py). Setting one's count_documents
# overwrites the other. Tests that need different return values for detection
# queries vs. dedup queries must use a side_effect that inspects the query dict.
#
# Detection queries (on db.events) have keys like event_type / timestamp.
# Dedup queries (on db.alerts inside events.py) have key "alert_type".


def _count_side_effect(detection_count: int, dedup_count: int):
    """
    Return an async callable that returns `detection_count` for detection-engine
    queries (no "alert_type" key) and `dedup_count` for dedup queries ("alert_type" key).
    """
    async def _side_effect(query):
        if "alert_type" in query:
            return dedup_count
        return detection_count
    return _side_effect


@pytest.mark.asyncio
async def test_dedup_suppresses_duplicate_alert(client, mock_mongo):
    """When an open alert of the same type+IP already exists, no new alert is inserted."""
    # Detection sees 10 events → brute-force threshold (5) exceeded → rule fires.
    # Dedup check returns 1 → duplicate open alert exists → skip insertion.
    mock_mongo.events.count_documents = AsyncMock(
        side_effect=_count_side_effect(detection_count=10, dedup_count=1)
    )

    resp = await client.post("/events", json=VALID_EVENT)
    assert resp.status_code == 202
    assert resp.json()["alerts_triggered"] == 0


@pytest.mark.asyncio
async def test_dedup_allows_first_alert(client, mock_mongo):
    """When no matching open alert exists, the alert is created normally."""
    # Detection sees 10 → brute-force fires. Dedup sees 0 → no duplicate → insert.
    mock_mongo.events.count_documents = AsyncMock(
        side_effect=_count_side_effect(detection_count=10, dedup_count=0)
    )

    resp = await client.post("/events", json=VALID_EVENT)
    assert resp.status_code == 202
    assert resp.json()["alerts_triggered"] >= 1


@pytest.mark.asyncio
async def test_dedup_check_uses_alert_type_and_ip(client, mock_mongo):
    """The dedup query must include alert_type, source_ip, and resolved=False."""
    mock_mongo.events.count_documents = AsyncMock(
        side_effect=_count_side_effect(detection_count=10, dedup_count=0)
    )

    await client.post("/events", json=VALID_EVENT)

    all_calls = mock_mongo.events.count_documents.call_args_list
    dedup_calls = [c for c in all_calls if "alert_type" in c[0][0]]
    assert len(dedup_calls) >= 1, "Expected at least one dedup count_documents call"
    query = dedup_calls[0][0][0]
    assert query.get("resolved") is False
    assert "alert_type" in query
    assert "source_ip" in query


@pytest.mark.asyncio
async def test_ingest_returns_alerts_triggered_zero_when_no_rules_fire(client, mock_mongo):
    """When no detection rule threshold is met, alerts_triggered is 0."""
    # count_documents returns 0 → below all rule thresholds → no alerts
    mock_mongo.events.count_documents = AsyncMock(return_value=0)

    resp = await client.post("/events", json=VALID_EVENT)
    assert resp.status_code == 202
    assert resp.json()["alerts_triggered"] == 0
