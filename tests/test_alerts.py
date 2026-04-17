import pytest
from unittest.mock import AsyncMock, MagicMock

VALID_ALERT = {
    "alert_type": "brute_force_detected",
    "source_ip": "10.0.0.1",
    "severity": "high",
    "message": "5 failed logins from 10.0.0.1 in 60s",
    "triggered_by": "n8n:failed-login-detection",
}


@pytest.mark.asyncio
async def test_list_alerts(client):
    resp = await client.get("/alerts")
    assert resp.status_code == 200
    data = resp.json()
    assert "alerts" in data
    assert "count" in data


@pytest.mark.asyncio
async def test_list_alerts_resolved_filter(client):
    resp = await client.get("/alerts?resolved=false")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_resolve_alert_invalid_id(client):
    resp = await client.patch("/alerts/not-a-valid-objectid/resolve")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_resolve_alert_not_found(client, mock_mongo):
    mock_mongo.alerts.update_one = AsyncMock(return_value=MagicMock(matched_count=0))
    resp = await client.patch("/alerts/64f1a2b3c4d5e6f7a8b9c0d1/resolve")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_resolve_alert_success(client, mock_mongo):
    mock_mongo.alerts.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    resp = await client.patch("/alerts/64f1a2b3c4d5e6f7a8b9c0d1/resolve")
    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"


# ── POST /alerts ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_alert_success(client):
    resp = await client.post("/alerts", json=VALID_ALERT)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "created"
    assert "alert_id" in data


@pytest.mark.asyncio
async def test_create_alert_invalid_ip(client):
    bad = {**VALID_ALERT, "source_ip": "not-an-ip"}
    resp = await client.post("/alerts", json=bad)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_alert_invalid_severity(client):
    bad = {**VALID_ALERT, "severity": "extreme"}
    resp = await client.post("/alerts", json=bad)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_alert_invalid_alert_type_injection(client):
    bad = {**VALID_ALERT, "alert_type": "alert'; DROP TABLE alerts; --"}
    resp = await client.post("/alerts", json=bad)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_alert_defaults_triggered_by(client):
    payload = {k: v for k, v in VALID_ALERT.items() if k != "triggered_by"}
    resp = await client.post("/alerts", json=payload)
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_create_alert_missing_required_fields(client):
    resp = await client.post("/alerts", json={"alert_type": "brute_force_detected"})
    assert resp.status_code == 422
