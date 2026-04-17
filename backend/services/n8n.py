"""
n8n forwarder — sends event payloads to n8n webhook endpoints.
Non-blocking: failures are logged but never crash the main request.
"""
import httpx
import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

N8N_BASE = os.environ.get("N8N_WEBHOOK_BASE", "http://n8n:5678/webhook")


async def forward_event(event: dict) -> None:
    url = f"{N8N_BASE}/ingest-event"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=event)
            resp.raise_for_status()
            logger.info("Event forwarded to n8n: %s", resp.status_code)
    except Exception as exc:
        logger.warning("n8n forward failed (non-fatal): %s", exc)


async def forward_block(ip: str, reason: str, triggered_by: str) -> None:
    url = f"{N8N_BASE}/block-ip"
    payload = {
        "ip": ip,
        "reason": reason,
        "triggered_by": triggered_by,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            logger.info("Block-IP forwarded to n8n for %s", ip)
    except Exception as exc:
        logger.warning("n8n block forward failed (non-fatal): %s", exc)
