"""
Tests for the backend detection engine (backend/services/detection.py).

All MongoDB calls are replaced with AsyncMock so no real database is needed.
Each test controls the return value of count_documents / aggregate to simulate
event history above or below each rule's threshold.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from backend.services.detection import (
    BruteForceRule,
    PortScanRule,
    CredentialStuffingRule,
    APIAbuseRule,
    DataExfiltrationRule,
    evaluate,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_db(count_return=0, aggregate_return=None):
    """Build a minimal fake DB collection supporting count_documents + aggregate."""
    aggregate_cursor = MagicMock()
    aggregate_cursor.to_list = AsyncMock(return_value=aggregate_return or [])

    collection = MagicMock()
    collection.count_documents = AsyncMock(return_value=count_return)
    collection.aggregate = MagicMock(return_value=aggregate_cursor)

    db = MagicMock()
    db.events = collection
    return db


def _login_event(status="failed", user_id="alice"):
    return {
        "event_type": "login_attempt",
        "source_ip": "10.0.0.1",
        "status": status,
        "user_id": user_id,
        "timestamp": datetime.now(timezone.utc),
    }


def _port_scan_event():
    return {
        "event_type": "port_scan",
        "source_ip": "10.0.0.2",
        "status": "unknown",
        "timestamp": datetime.now(timezone.utc),
    }


def _data_access_event():
    return {
        "event_type": "data_access",
        "source_ip": "10.0.0.3",
        "status": "success",
        "timestamp": datetime.now(timezone.utc),
    }


# ── BruteForceRule ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_brute_force_matches_failed_login():
    rule = BruteForceRule()
    assert rule.matches(_login_event("failed")) is True


@pytest.mark.asyncio
async def test_brute_force_no_match_success_login():
    rule = BruteForceRule()
    assert rule.matches(_login_event("success")) is False


@pytest.mark.asyncio
async def test_brute_force_no_match_other_event_type():
    rule = BruteForceRule()
    assert rule.matches(_port_scan_event()) is False


@pytest.mark.asyncio
async def test_brute_force_fires_above_threshold():
    rule = BruteForceRule()
    db = _make_db(count_return=rule.threshold)
    result = await rule.evaluate(_login_event(), db)
    assert result is not None
    assert result["alert_type"] == "brute_force_detected"
    assert result["severity"] == "high"
    assert result["source_ip"] == "10.0.0.1"


@pytest.mark.asyncio
async def test_brute_force_no_fire_below_threshold():
    rule = BruteForceRule()
    db = _make_db(count_return=rule.threshold - 1)
    result = await rule.evaluate(_login_event(), db)
    assert result is None


# ── PortScanRule ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_port_scan_matches_port_scan_event():
    rule = PortScanRule()
    assert rule.matches(_port_scan_event()) is True


@pytest.mark.asyncio
async def test_port_scan_no_match_login_event():
    rule = PortScanRule()
    assert rule.matches(_login_event()) is False


@pytest.mark.asyncio
async def test_port_scan_fires_above_threshold():
    rule = PortScanRule()
    db = _make_db(count_return=rule.threshold)
    result = await rule.evaluate(_port_scan_event(), db)
    assert result is not None
    assert result["alert_type"] == "port_scan_detected"
    assert result["severity"] == "high"


@pytest.mark.asyncio
async def test_port_scan_no_fire_below_threshold():
    rule = PortScanRule()
    db = _make_db(count_return=rule.threshold - 1)
    result = await rule.evaluate(_port_scan_event(), db)
    assert result is None


# ── CredentialStuffingRule ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_credential_stuffing_matches_failed_login():
    rule = CredentialStuffingRule()
    assert rule.matches(_login_event("failed")) is True


@pytest.mark.asyncio
async def test_credential_stuffing_fires_when_thresholds_met():
    rule = CredentialStuffingRule()
    # Simulate 12 failures across 6 distinct users
    agg_result = [{"count": 12, "distinct_users": ["u1", "u2", "u3", "u4", "u5", "u6"]}]
    db = _make_db(aggregate_return=agg_result)
    result = await rule.evaluate(_login_event(), db)
    assert result is not None
    assert result["alert_type"] == "credential_stuffing_detected"
    assert result["severity"] == "critical"
    assert result["distinct_users"] == 6


@pytest.mark.asyncio
async def test_credential_stuffing_no_fire_too_few_users():
    rule = CredentialStuffingRule()
    # Enough failures but only 2 distinct users — not stuffing
    agg_result = [{"count": 15, "distinct_users": ["u1", "u2"]}]
    db = _make_db(aggregate_return=agg_result)
    result = await rule.evaluate(_login_event(), db)
    assert result is None


@pytest.mark.asyncio
async def test_credential_stuffing_no_fire_too_few_failures():
    rule = CredentialStuffingRule()
    # Enough distinct users but too few total failures
    agg_result = [{"count": 3, "distinct_users": ["u1", "u2", "u3", "u4", "u5", "u6"]}]
    db = _make_db(aggregate_return=agg_result)
    result = await rule.evaluate(_login_event(), db)
    assert result is None


@pytest.mark.asyncio
async def test_credential_stuffing_no_fire_empty_aggregate():
    rule = CredentialStuffingRule()
    db = _make_db(aggregate_return=[])
    result = await rule.evaluate(_login_event(), db)
    assert result is None


# ── APIAbuseRule ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_api_abuse_matches_all_events():
    rule = APIAbuseRule()
    assert rule.matches(_login_event()) is True
    assert rule.matches(_port_scan_event()) is True
    assert rule.matches(_data_access_event()) is True


@pytest.mark.asyncio
async def test_api_abuse_fires_above_threshold():
    rule = APIAbuseRule()
    db = _make_db(count_return=rule.threshold)
    result = await rule.evaluate(_login_event(), db)
    assert result is not None
    assert result["alert_type"] == "api_abuse_detected"
    assert result["severity"] == "medium"


@pytest.mark.asyncio
async def test_api_abuse_no_fire_below_threshold():
    rule = APIAbuseRule()
    db = _make_db(count_return=rule.threshold - 1)
    result = await rule.evaluate(_login_event(), db)
    assert result is None


# ── DataExfiltrationRule ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_data_exfiltration_matches_data_access():
    rule = DataExfiltrationRule()
    assert rule.matches(_data_access_event()) is True


@pytest.mark.asyncio
async def test_data_exfiltration_no_match_login_event():
    rule = DataExfiltrationRule()
    assert rule.matches(_login_event()) is False


@pytest.mark.asyncio
async def test_data_exfiltration_fires_above_threshold():
    rule = DataExfiltrationRule()
    db = _make_db(count_return=rule.threshold)
    result = await rule.evaluate(_data_access_event(), db)
    assert result is not None
    assert result["alert_type"] == "data_exfiltration_detected"
    assert result["severity"] == "critical"


@pytest.mark.asyncio
async def test_data_exfiltration_no_fire_below_threshold():
    rule = DataExfiltrationRule()
    db = _make_db(count_return=rule.threshold - 1)
    result = await rule.evaluate(_data_access_event(), db)
    assert result is None


# ── evaluate() — top-level dispatcher ────────────────────────────────────────

@pytest.mark.asyncio
async def test_evaluate_returns_empty_when_no_rules_fire():
    db = _make_db(count_return=0)
    results = await evaluate(_login_event("failed"), db)
    assert results == []


@pytest.mark.asyncio
async def test_evaluate_returns_alert_when_brute_force_fires():
    rule = BruteForceRule()
    db = _make_db(count_return=rule.threshold)
    results = await evaluate(_login_event("failed"), db)
    alert_types = [r["alert_type"] for r in results]
    assert "brute_force_detected" in alert_types


@pytest.mark.asyncio
async def test_evaluate_rule_exception_is_non_fatal():
    """A rule that throws must not crash the evaluate() call."""
    db = MagicMock()
    # count_documents raises an exception
    db.events.count_documents = AsyncMock(side_effect=Exception("DB down"))
    db.events.aggregate = MagicMock(return_value=MagicMock(
        to_list=AsyncMock(return_value=[])
    ))
    # Should return an empty list, not raise
    results = await evaluate(_login_event("failed"), db)
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_evaluate_port_scan_not_triggered_for_login_event():
    """PortScanRule must not run against a login event."""
    db = _make_db(count_return=999)  # Would trigger if rule ran
    results = await evaluate(_login_event("failed"), db)
    alert_types = [r["alert_type"] for r in results]
    assert "port_scan_detected" not in alert_types


# ── Detection integrated via POST /events ────────────────────────────────────

@pytest.mark.asyncio
async def test_event_ingest_returns_alerts_triggered_count(client):
    """POST /events response must include alerts_triggered field."""
    resp = await client.post("/events", json={
        "event_type": "login_attempt",
        "source_ip": "192.168.1.1",
        "status": "failed",
    })
    assert resp.status_code == 202
    assert "alerts_triggered" in resp.json()


@pytest.mark.asyncio
async def test_event_ingest_zero_alerts_when_below_threshold(client, mock_mongo):
    """count_documents returns 0 → no detection alerts should fire."""
    mock_mongo.count_documents = AsyncMock(return_value=0)
    resp = await client.post("/events", json={
        "event_type": "login_attempt",
        "source_ip": "192.168.1.1",
        "status": "failed",
    })
    assert resp.status_code == 202
    assert resp.json()["alerts_triggered"] == 0
