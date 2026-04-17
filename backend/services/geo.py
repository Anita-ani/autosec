"""
Geo-enrichment service — looks up country, city, and ASN for an IP address.

Uses ip-api.com (free tier, no API key required, 45 req/min per IP).
Private/reserved IPs are returned immediately as "private" with no HTTP call.

All failures are non-fatal — the caller receives an empty dict and the event
is ingested normally. Geo data is best-effort enrichment, not a hard dependency.

Returned dict shape (when successful):
    {
        "country":      "United States",
        "country_code": "US",
        "region":       "California",
        "city":         "San Francisco",
        "isp":          "Cloudflare, Inc.",
        "asn":          "AS13335",
        "is_private":   False,
    }
"""
from __future__ import annotations

import ipaddress
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = float(os.environ.get("GEO_LOOKUP_TIMEOUT_S", "2"))
_API_URL = "http://ip-api.com/json/{ip}?fields=status,country,countryCode,regionName,city,isp,as"

# Private/loopback/link-local ranges — skip API call for these
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_private(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in net for net in _PRIVATE_NETWORKS)
    except ValueError:
        return False


async def lookup(ip: str) -> dict[str, Any]:
    """
    Return geo data for *ip*.  Never raises — returns {} on any failure.
    Private IPs return {"is_private": True} immediately without an HTTP call.
    """
    if _is_private(ip):
        return {"is_private": True}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(_API_URL.format(ip=ip))
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "success":
            logger.debug("ip-api returned non-success for %s: %s", ip, data.get("message"))
            return {}

        # Parse ASN number out of the "AS13335 Cloudflare..." string
        raw_as = data.get("as", "")
        asn = raw_as.split(" ")[0] if raw_as else None

        return {
            "country":      data.get("country"),
            "country_code": data.get("countryCode"),
            "region":       data.get("regionName"),
            "city":         data.get("city"),
            "isp":          data.get("isp"),
            "asn":          asn,
            "is_private":   False,
        }

    except Exception as exc:
        logger.warning("Geo lookup failed for %s (non-fatal): %s", ip, exc)
        return {}
