"""
Tests for the geo-enrichment service and its integration into POST /events.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from backend.services.geo import lookup, _is_private


# ── _is_private helper ────────────────────────────────────────────────────────

def test_private_rfc1918_addresses():
    assert _is_private("10.0.0.1") is True
    assert _is_private("172.16.5.5") is True
    assert _is_private("192.168.1.100") is True


def test_loopback_is_private():
    assert _is_private("127.0.0.1") is True
    assert _is_private("::1") is True


def test_link_local_is_private():
    assert _is_private("169.254.0.1") is True
    assert _is_private("fe80::1") is True


def test_public_ip_is_not_private():
    assert _is_private("8.8.8.8") is False
    assert _is_private("1.1.1.1") is False


# ── lookup() ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_lookup_private_ip_returns_is_private():
    result = await lookup("192.168.1.1")
    assert result == {"is_private": True}


@pytest.mark.asyncio
async def test_lookup_returns_geo_data_on_success():
    api_response = {
        "status": "success",
        "country": "United States",
        "countryCode": "US",
        "regionName": "California",
        "city": "San Francisco",
        "isp": "Cloudflare, Inc.",
        "as": "AS13335 Cloudflare, Inc.",
    }
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=api_response)

    with patch("backend.services.geo.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await lookup("1.1.1.1")

    assert result["country"] == "United States"
    assert result["country_code"] == "US"
    assert result["city"] == "San Francisco"
    assert result["asn"] == "AS13335"
    assert result["is_private"] is False


@pytest.mark.asyncio
async def test_lookup_returns_empty_on_api_failure():
    api_response = {"status": "fail", "message": "private range"}
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=api_response)

    with patch("backend.services.geo.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await lookup("1.1.1.1")

    assert result == {}


@pytest.mark.asyncio
async def test_lookup_returns_empty_on_network_error():
    with patch("backend.services.geo.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("timeout"))
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await lookup("8.8.8.8")

    assert result == {}


@pytest.mark.asyncio
async def test_lookup_returns_empty_on_http_error():
    with patch("backend.services.geo.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock(side_effect=httpx.HTTPStatusError(
            "429", request=MagicMock(), response=MagicMock()
        ))
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await lookup("8.8.8.8")

    assert result == {}


# ── Integration: geo enrichment in POST /events ───────────────────────────────

VALID_EVENT = {
    "event_type": "login_attempt",
    "source_ip": "8.8.8.8",
    "status": "failed",
    "timestamp": "2026-04-16T10:00:00Z",
}


@pytest.mark.asyncio
async def test_ingest_event_includes_geo_when_lookup_succeeds(client):
    geo_data = {
        "country": "United States", "country_code": "US",
        "region": "California", "city": "Mountain View",
        "isp": "Google LLC", "asn": "AS15169", "is_private": False,
    }
    with patch("backend.routes.events.geo.lookup", new_callable=AsyncMock, return_value=geo_data):
        resp = await client.post("/events", json=VALID_EVENT)

    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_ingest_event_succeeds_when_geo_lookup_fails(client):
    """Geo failure must never fail event ingestion."""
    with patch("backend.routes.events.geo.lookup", new_callable=AsyncMock, return_value={}):
        resp = await client.post("/events", json=VALID_EVENT)

    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_ingest_private_ip_skips_api_call(client):
    private_event = {**VALID_EVENT, "source_ip": "10.0.0.5"}
    with patch("backend.routes.events.geo.lookup", new_callable=AsyncMock,
               return_value={"is_private": True}) as mock_lookup:
        resp = await client.post("/events", json=private_event)

    assert resp.status_code == 202
    mock_lookup.assert_called_once_with("10.0.0.5")
