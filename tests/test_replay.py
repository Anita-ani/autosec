"""
Tests for POST /replay and the replay service.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta

import backend.services.replay as replay_svc

SINCE = "2026-04-15T00:00:00Z"
UNTIL = "2026-04-15T01:00:00Z"


# ── Route-level tests ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_replay_dry_run_returns_200(client):
    with patch("backend.services.replay.run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = {
            "window": {"since": SINCE, "until": UNTIL},
            "dry_run": True,
            "events_scanned": 10,
            "rules_fired": {"brute_force": 2},
            "alerts_created": 0,
            "alerts_skipped_dedup": 1,
        }
        resp = await client.post("/replay", json={"since": SINCE, "until": UNTIL})

    assert resp.status_code == 200
    data = resp.json()
    assert data["dry_run"] is True
    assert data["events_scanned"] == 10
    assert data["alerts_created"] == 0


@pytest.mark.asyncio
async def test_replay_live_run_creates_alerts(client):
    with patch("backend.services.replay.run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = {
            "window": {"since": SINCE, "until": UNTIL},
            "dry_run": False,
            "events_scanned": 5,
            "rules_fired": {"brute_force": 1},
            "alerts_created": 1,
            "alerts_skipped_dedup": 0,
        }
        resp = await client.post("/replay", json={
            "since": SINCE, "until": UNTIL, "dry_run": False
        })

    assert resp.status_code == 200
    assert resp.json()["alerts_created"] == 1


@pytest.mark.asyncio
async def test_replay_since_equals_until_returns_422(client):
    resp = await client.post("/replay", json={
        "since": SINCE, "until": SINCE
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_replay_window_over_72h_returns_422(client):
    far_future = "2026-04-19T00:00:00Z"
    resp = await client.post("/replay", json={"since": SINCE, "until": far_future})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_replay_requires_auth(client):
    from httpx import AsyncClient, ASGITransport
    from backend.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/replay", json={"since": SINCE, "until": UNTIL})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_replay_until_defaults_to_now(client):
    with patch("backend.services.replay.run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = {
            "window": {"since": SINCE, "until": "2026-04-16T00:00:00+00:00"},
            "dry_run": True, "events_scanned": 0,
            "rules_fired": {}, "alerts_created": 0, "alerts_skipped_dedup": 0,
        }
        resp = await client.post("/replay", json={"since": SINCE})
    assert resp.status_code == 200
    _, call_kwargs = mock_run.call_args
    assert call_kwargs["until"] is not None


# ── Service-level tests ───────────────────────────────────────────────────────

def _make_db(events: list[dict], dedup_count: int = 0):
    """Build a minimal fake db whose events cursor yields the given list."""
    from tests.conftest import _async_cursor

    fake_col = MagicMock()
    fake_col.find = MagicMock(return_value=_async_cursor(events))
    fake_col.count_documents = AsyncMock(return_value=dedup_count)
    fake_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="abc"))

    fake_db = MagicMock()
    fake_db.events = fake_col
    fake_db.alerts = fake_col
    fake_db.audit_logs = fake_col
    return fake_db


@pytest.mark.asyncio
async def test_service_returns_zero_when_no_events():
    db = _make_db([])
    since = datetime(2026, 4, 15, 0, 0, tzinfo=timezone.utc)
    until = datetime(2026, 4, 15, 1, 0, tzinfo=timezone.utc)

    with patch("backend.services.replay.mongo.get_db", return_value=db):
        result = await replay_svc.run(since, until, dry_run=True)

    assert result["events_scanned"] == 0
    assert result["alerts_created"] == 0
    assert result["rules_fired"] == {}


@pytest.mark.asyncio
async def test_service_dry_run_does_not_insert():
    event = {
        "_id": "64f1a2b3c4d5e6f7a8b9c0d1",
        "event_type": "login_attempt",
        "source_ip": "10.0.0.1",
        "status": "failed",
        "timestamp": datetime(2026, 4, 15, 0, 30, tzinfo=timezone.utc),
    }
    db = _make_db([event], dedup_count=0)

    alert = {
        "alert_type": "brute_force_detected",
        "source_ip": "10.0.0.1",
        "severity": "high",
        "message": "5 failed logins",
        "rule": "brute_force",
    }

    with patch("backend.services.replay.mongo.get_db", return_value=db), \
         patch("backend.services.replay.detection.evaluate",
               new_callable=AsyncMock, return_value=[alert]):
        result = await replay_svc.run(since=event["timestamp"],
                                      until=datetime(2026, 4, 15, 1, 0, tzinfo=timezone.utc),
                                      dry_run=True)

    assert result["alerts_created"] == 1
    assert result["dry_run"] is True
    # insert_one must NOT have been called during a dry run
    db.alerts.insert_one.assert_not_called()


@pytest.mark.asyncio
async def test_service_live_run_inserts_alert():
    event = {
        "_id": "64f1a2b3c4d5e6f7a8b9c0d1",
        "event_type": "login_attempt",
        "source_ip": "10.0.0.2",
        "status": "failed",
        "timestamp": datetime(2026, 4, 15, 0, 30, tzinfo=timezone.utc),
    }
    db = _make_db([event], dedup_count=0)

    alert = {
        "alert_type": "brute_force_detected",
        "source_ip": "10.0.0.2",
        "severity": "high",
        "message": "5 failed logins",
        "rule": "brute_force",
    }

    with patch("backend.services.replay.mongo.get_db", return_value=db), \
         patch("backend.services.replay.detection.evaluate",
               new_callable=AsyncMock, return_value=[alert]):
        result = await replay_svc.run(since=event["timestamp"],
                                      until=datetime(2026, 4, 15, 1, 0, tzinfo=timezone.utc),
                                      dry_run=False)

    assert result["alerts_created"] == 1
    # insert_one is shared by alerts + audit_logs (same fake_col); called twice total
    assert db.alerts.insert_one.call_count == 2


@pytest.mark.asyncio
async def test_service_dedup_skips_existing_open_alert():
    event = {
        "_id": "64f1a2b3c4d5e6f7a8b9c0d2",
        "event_type": "login_attempt",
        "source_ip": "10.0.0.3",
        "status": "failed",
        "timestamp": datetime(2026, 4, 15, 0, 30, tzinfo=timezone.utc),
    }
    db = _make_db([event], dedup_count=1)  # duplicate exists

    alert = {
        "alert_type": "brute_force_detected",
        "source_ip": "10.0.0.3",
        "severity": "high",
        "message": "5 failed logins",
        "rule": "brute_force",
    }

    with patch("backend.services.replay.mongo.get_db", return_value=db), \
         patch("backend.services.replay.detection.evaluate",
               new_callable=AsyncMock, return_value=[alert]):
        result = await replay_svc.run(since=event["timestamp"],
                                      until=datetime(2026, 4, 15, 1, 0, tzinfo=timezone.utc),
                                      dry_run=False)

    assert result["alerts_skipped_dedup"] == 1
    assert result["alerts_created"] == 0
    db.alerts.insert_one.assert_not_called()


@pytest.mark.asyncio
async def test_service_raises_on_invalid_window():
    t = datetime(2026, 4, 15, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="since must be before until"):
        await replay_svc.run(since=t, until=t)
