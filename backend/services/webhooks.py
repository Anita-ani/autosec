"""
Webhook delivery service — fires outbound HTTP POSTs to registered endpoints.

Each webhook subscription is stored in the `webhooks` MongoDB collection.
On alert creation or resolution, fire() is called with the event type and
payload. All registered, enabled webhooks subscribed to that event type
are notified concurrently.

Delivery is best-effort:
  - 3-second timeout per call
  - One retry on connection failure
  - Failures are logged but never propagate to the caller

Payload shape sent to the subscriber:
    {
        "event":     "alert.created",
        "timestamp": "2026-04-16T10:00:00+00:00",
        "data":      { ...alert fields... }
    }

If a secret is configured, it is sent as the X-Webhook-Secret header.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from backend.services import mongo

logger = logging.getLogger(__name__)

_TIMEOUT = 3.0
_MAX_RETRIES = 1


async def fire(event_type: str, payload: dict) -> None:
    """
    Deliver *payload* to all enabled webhooks subscribed to *event_type*.
    Non-blocking — all deliveries run concurrently via asyncio.gather.
    """
    db = mongo.get_db()
    cursor = db.webhooks.find({"enabled": True, "events": event_type})
    hooks = []
    async for doc in cursor:
        hooks.append(doc)

    if not hooks:
        return

    envelope = {
        "event": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": payload,
    }

    await asyncio.gather(
        *[_deliver(hook, envelope) for hook in hooks],
        return_exceptions=True,
    )


def _slack_payload(envelope: dict) -> dict:
    """Format an alert envelope as a Slack Block Kit message."""
    data = envelope.get("data", {})
    event = envelope.get("event", "alert.created")
    ts = envelope.get("timestamp", "")[:19].replace("T", " ")

    severity = data.get("severity", "unknown").upper()
    severity_prefix = {"CRITICAL": "[CRITICAL]", "HIGH": "[HIGH]",
                       "MEDIUM": "[MEDIUM]", "LOW": "[LOW]"}.get(severity, "[ALERT]")

    alert_type = data.get("alert_type", event)
    source_ip  = data.get("source_ip", "n/a")
    message    = data.get("message", "")

    summary = (
        f"*{severity_prefix} AutoSecOps — {alert_type}*\n"
        f"*Severity:* {severity}    *Source IP:* `{source_ip}`\n"
        f"*Message:* {message}\n"
        f"*Detected:* {ts} UTC"
    )

    return {
        "text": f"{severity_prefix} AutoSecOps: {alert_type} from {source_ip}",
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn", "text": summary}},
            {"type": "divider"},
        ],
    }


async def _deliver(hook: dict, envelope: dict) -> None:
    headers = {"Content-Type": "application/json"}
    if hook.get("secret"):
        headers["X-Webhook-Secret"] = hook["secret"]

    url = hook["url"]
    webhook_id = str(hook.get("_id", ""))
    payload = _slack_payload(envelope) if hook.get("type") == "slack" else envelope
    last_exc: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
            logger.info("Webhook delivered: url=%s event=%s status=%d",
                        url, envelope["event"], resp.status_code)
            await _log_delivery(webhook_id, url, envelope["event"], attempt + 1,
                                "success", resp.status_code, None)
            return
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                logger.debug("Webhook attempt %d failed for %s: %s — retrying", attempt + 1, url, exc)

    logger.warning("Webhook delivery failed after %d attempts for %s: %s",
                   _MAX_RETRIES + 1, url, last_exc)
    await _log_delivery(webhook_id, url, envelope["event"], _MAX_RETRIES + 1,
                        "failed", None, str(last_exc))


async def _log_delivery(
    webhook_id: str,
    url: str,
    event_type: str,
    attempts: int,
    outcome: str,
    status_code: int | None,
    error: str | None,
) -> None:
    try:
        db = mongo.get_db()
        doc: dict = {
            "webhook_id": webhook_id,
            "url": url,
            "event_type": event_type,
            "attempts": attempts,
            "outcome": outcome,
            "delivered_at": datetime.now(timezone.utc),
        }
        if status_code is not None:
            doc["status_code"] = status_code
        if error is not None:
            doc["error"] = error
        await db.webhook_delivery_log.insert_one(doc)
    except Exception as exc:
        logger.debug("Failed to write webhook delivery log: %s", exc)
