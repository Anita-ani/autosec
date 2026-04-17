"""
Tests for GET /stats endpoint (backend/routes/stats.py).

All MongoDB calls (count_documents, aggregate) are controlled via the
mock_mongo fixture from conftest.py — no real database required.

Mock targeting:
  mock_mongo         = fake_db
  mock_mongo.events  = fake_collection  (shared across all collections)
  mock_mongo.alerts  = fake_collection  (same object)
  mock_mongo.blocked_ips = fake_collection  (same object)

The stats route makes 5 aggregate calls in this order:
  1. db.alerts.aggregate(severity_pipeline)
  2. db.alerts.aggregate(alert_type_pipeline)
  3. db.events.aggregate(type_pipeline)         — events_by_type_24h
  4. db.events.aggregate(country_pipeline)      — top_source_countries (Phase 5)
  5. db.blocked_ips.aggregate(top_blocked_pipeline)

Tests that need specific results per call use a side_effect list ordered accordingly.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cursor(results: list):
    """Build a fake Motor aggregate cursor that returns `results` from to_list()."""
    c = MagicMock()
    c.to_list = AsyncMock(return_value=results)
    return c


def _set_aggregate_sequence(mock_mongo, *result_lists):
    """
    Set up aggregate to return each list in order across all collection calls.
    Because all collections share the same fake_collection, every call to
    .aggregate() on any collection consumes the next item in the sequence.
    """
    mock_mongo.events.aggregate = MagicMock(
        side_effect=[_cursor(r) for r in result_lists]
    )


# ── Basic structure ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stats_returns_200(client):
    resp = await client.get("/stats")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_stats_response_shape(client):
    resp = await client.get("/stats")
    data = resp.json()
    assert "totals" in data
    assert "alerts_by_severity" in data
    assert "open_alerts_by_type" in data
    assert "events_by_type_24h" in data
    assert "top_source_countries" in data
    assert "top_blocked_ips" in data


@pytest.mark.asyncio
async def test_stats_totals_shape(client):
    totals = (await client.get("/stats")).json()["totals"]
    for key in ("events", "events_24h", "alerts", "open_alerts", "blocked_ips"):
        assert key in totals


# ── Total counts ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stats_totals_reflect_count_documents(client, mock_mongo):
    # count_documents is on the collection, not on fake_db itself
    mock_mongo.events.count_documents = AsyncMock(return_value=42)
    resp = await client.get("/stats")
    totals = resp.json()["totals"]
    assert totals["events"] == 42
    assert totals["alerts"] == 42
    assert totals["open_alerts"] == 42
    assert totals["blocked_ips"] == 42


@pytest.mark.asyncio
async def test_stats_totals_zero_when_empty(client, mock_mongo):
    mock_mongo.events.count_documents = AsyncMock(return_value=0)
    totals = (await client.get("/stats")).json()["totals"]
    assert totals["events"] == 0
    assert totals["open_alerts"] == 0
    assert totals["blocked_ips"] == 0


# ── Alerts by severity ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stats_alerts_by_severity(client, mock_mongo):
    _set_aggregate_sequence(
        mock_mongo,
        [{"_id": "critical", "count": 3}, {"_id": "high", "count": 7}],  # severity
        [],   # open_alerts_by_type
        [],   # events_by_type_24h
        [],   # top_source_countries
        [],   # top_blocked_ips
    )
    data = (await client.get("/stats")).json()
    assert data["alerts_by_severity"]["critical"] == 3
    assert data["alerts_by_severity"]["high"] == 7


@pytest.mark.asyncio
async def test_stats_alerts_by_severity_empty(client, mock_mongo):
    _set_aggregate_sequence(mock_mongo, [], [], [], [], [])
    assert (await client.get("/stats")).json()["alerts_by_severity"] == {}


# ── Open alerts by type ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stats_open_alerts_by_type(client, mock_mongo):
    _set_aggregate_sequence(
        mock_mongo,
        [],  # severity
        [{"_id": "brute_force_detected", "count": 5}, {"_id": "port_scan_detected", "count": 2}],
        [],  # events_by_type_24h
        [],  # top_source_countries
        [],  # top_blocked_ips
    )
    data = (await client.get("/stats")).json()
    assert data["open_alerts_by_type"]["brute_force_detected"] == 5
    assert data["open_alerts_by_type"]["port_scan_detected"] == 2


@pytest.mark.asyncio
async def test_stats_open_alerts_by_type_empty(client, mock_mongo):
    _set_aggregate_sequence(mock_mongo, [], [], [], [], [])
    assert (await client.get("/stats")).json()["open_alerts_by_type"] == {}


# ── Events by type 24h ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stats_events_by_type_24h(client, mock_mongo):
    _set_aggregate_sequence(
        mock_mongo,
        [],   # severity
        [],   # open_alerts_by_type
        [{"_id": "login_attempt", "count": 200}, {"_id": "port_scan", "count": 15}],
        [],   # top_source_countries
        [],   # top_blocked_ips
    )
    data = (await client.get("/stats")).json()
    assert data["events_by_type_24h"]["login_attempt"] == 200
    assert data["events_by_type_24h"]["port_scan"] == 15


@pytest.mark.asyncio
async def test_stats_events_by_type_24h_empty(client, mock_mongo):
    _set_aggregate_sequence(mock_mongo, [], [], [], [], [])
    assert (await client.get("/stats")).json()["events_by_type_24h"] == {}


# ── Top blocked IPs ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stats_top_blocked_ips(client, mock_mongo):
    _set_aggregate_sequence(
        mock_mongo,
        [],  # severity
        [],  # open_alerts_by_type
        [],  # events_by_type_24h
        [],  # top_source_countries
        [{"ip": "10.0.0.1", "reason": "brute force", "triggered_by": "detection_engine"}],
    )
    blocked = (await client.get("/stats")).json()["top_blocked_ips"]
    assert len(blocked) == 1
    assert blocked[0]["ip"] == "10.0.0.1"


@pytest.mark.asyncio
async def test_stats_top_blocked_ips_empty(client, mock_mongo):
    _set_aggregate_sequence(mock_mongo, [], [], [], [], [])
    assert (await client.get("/stats")).json()["top_blocked_ips"] == []


# ── Top source countries (Phase 5 geo-enrichment) ────────────────────────────

@pytest.mark.asyncio
async def test_stats_top_source_countries(client, mock_mongo):
    _set_aggregate_sequence(
        mock_mongo,
        [],  # severity
        [],  # open_alerts_by_type
        [],  # events_by_type_24h
        [{"_id": {"code": "US", "name": "United States"}, "count": 120},
         {"_id": {"code": "CN", "name": "China"}, "count": 45}],
        [],  # top_blocked_ips
    )
    countries = (await client.get("/stats")).json()["top_source_countries"]
    assert len(countries) == 2
    assert countries[0]["country_code"] == "US"
    assert countries[0]["count"] == 120


@pytest.mark.asyncio
async def test_stats_top_source_countries_empty(client, mock_mongo):
    _set_aggregate_sequence(mock_mongo, [], [], [], [], [])
    assert (await client.get("/stats")).json()["top_source_countries"] == []


# ── Auth ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stats_requires_auth():
    from httpx import AsyncClient, ASGITransport
    from backend.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/stats")
    assert resp.status_code == 401
