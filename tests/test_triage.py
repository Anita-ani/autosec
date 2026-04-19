"""
Tests for GET /alerts/{id}/triage and the triage service.
All Gemini API calls are mocked — no real API key required.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

import backend.services.triage as triage_svc
from backend.services.triage import _parse_response

ALERT_ID = "64f1a2b3c4d5e6f7a8b9c0d1"

SAMPLE_ALERT = {
    "_id": ALERT_ID,
    "alert_type": "brute_force_detected",
    "source_ip": "10.0.0.5",
    "severity": "high",
    "message": "5 failed login attempts from 10.0.0.5 in 60s",
    "rule": "brute_force",
    "created_at": datetime(2026, 4, 16, 10, 0, tzinfo=timezone.utc),
    "resolved": False,
}

CLAUDE_RESPONSE = """\
SUMMARY:
The source IP 10.0.0.5 has been attempting brute-force attacks against user accounts. \
Multiple failed login attempts were detected within a short window, suggesting automated credential testing.

SEVERITY_ASSESSMENT:
High severity is appropriate given the volume and speed of failed attempts.

REMEDIATION_STEPS:
1. Block the source IP 10.0.0.5 at the firewall
2. Reset passwords for any accounts targeted
3. Enable multi-factor authentication for all user accounts
4. Review logs for any successful logins from this IP
"""


# ── _parse_response ───────────────────────────────────────────────────────────

def test_parse_response_extracts_summary():
    result = _parse_response(CLAUDE_RESPONSE)
    assert "brute-force" in result["summary"]


def test_parse_response_extracts_severity_assessment():
    result = _parse_response(CLAUDE_RESPONSE)
    assert "High severity" in result["severity_assessment"]


def test_parse_response_extracts_remediation_steps():
    result = _parse_response(CLAUDE_RESPONSE)
    steps = result["remediation_steps"]
    assert len(steps) >= 3
    assert any("firewall" in s.lower() for s in steps)


def test_parse_response_fallback_on_unstructured_text():
    result = _parse_response("This is unstructured text without labels.")
    assert result["summary"] == "This is unstructured text without labels."
    assert result["remediation_steps"] == []


def test_parse_response_strips_leading_numbers():
    result = _parse_response(CLAUDE_RESPONSE)
    for step in result["remediation_steps"]:
        # Steps should not start with "1.", "2.", etc.
        assert not step[0].isdigit()


# ── Service (mocked AI client) ───────────────────────────────────────────────

def _make_db(alert_exists=True):
    from tests.conftest import _async_cursor
    fake_col = MagicMock()
    fake_col.find_one = AsyncMock(return_value={**SAMPLE_ALERT} if alert_exists else None)
    fake_col.find = MagicMock(return_value=_async_cursor([]))
    fake_col.count_documents = AsyncMock(return_value=2)
    fake_db = MagicMock()
    fake_db.alerts = fake_col
    fake_db.events = fake_col
    return fake_db


def _mock_gemini(response_text: str):
    mock_message = MagicMock()
    mock_message.content = response_text
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    return mock_client


@pytest.mark.asyncio
async def test_service_returns_triage_report():
    db = _make_db()
    mock_client = _mock_gemini(CLAUDE_RESPONSE)

    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}), \
         patch("openai.AsyncOpenAI", return_value=mock_client):
        result = await triage_svc.run(SAMPLE_ALERT, db)

    assert result["alert_id"] == ALERT_ID
    assert "summary" in result
    assert "remediation_steps" in result
    assert result["model"] == "gemini-2.0-flash"


@pytest.mark.asyncio
async def test_service_raises_without_api_key():
    db = _make_db()

    import os
    with patch.dict("os.environ", {}, clear=False):
        os.environ.pop("GEMINI_API_KEY", None)
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
            await triage_svc.run(SAMPLE_ALERT, db)


@pytest.mark.asyncio
async def test_service_includes_related_events_count():
    from tests.conftest import _async_cursor
    fake_col = MagicMock()
    fake_col.find = MagicMock(return_value=_async_cursor([
        {"event_type": "login_attempt", "status": "failed",
         "timestamp": datetime(2026, 4, 16, 9, 55, tzinfo=timezone.utc)},
        {"event_type": "login_attempt", "status": "failed",
         "timestamp": datetime(2026, 4, 16, 9, 56, tzinfo=timezone.utc)},
    ]))
    fake_col.count_documents = AsyncMock(return_value=1)
    fake_db = MagicMock()
    fake_db.events = fake_col
    fake_db.alerts = fake_col

    mock_client = _mock_gemini(CLAUDE_RESPONSE)

    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}), \
         patch("openai.AsyncOpenAI", return_value=mock_client):
        result = await triage_svc.run(SAMPLE_ALERT, fake_db)

    assert result["related_events_count"] == 2


# ── Route (GET /alerts/{id}/triage) ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_triage_route_returns_200(client, mock_mongo):
    mock_mongo.alerts.find_one = AsyncMock(return_value={**SAMPLE_ALERT})
    mock_client = _mock_gemini(CLAUDE_RESPONSE)

    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}), \
         patch("openai.AsyncOpenAI", return_value=mock_client):
        resp = await client.get(f"/alerts/{ALERT_ID}/triage")

    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data
    assert "remediation_steps" in data


@pytest.mark.asyncio
async def test_triage_route_404_for_missing_alert(client, mock_mongo):
    mock_mongo.alerts.find_one = AsyncMock(return_value=None)

    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
        resp = await client.get(f"/alerts/{ALERT_ID}/triage")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_triage_route_503_when_no_api_key(client, mock_mongo):
    mock_mongo.alerts.find_one = AsyncMock(return_value={**SAMPLE_ALERT})

    import os
    with patch.dict("os.environ", {}, clear=False):
        os.environ.pop("GEMINI_API_KEY", None)
        resp = await client.get(f"/alerts/{ALERT_ID}/triage")

    assert resp.status_code == 503
    assert "GEMINI_API_KEY" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_triage_route_400_invalid_id(client):
    resp = await client.get("/alerts/not-a-valid-id/triage")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_triage_requires_auth():
    from httpx import AsyncClient, ASGITransport
    from backend.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/alerts/{ALERT_ID}/triage")
    assert resp.status_code == 401
