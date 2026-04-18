import logging
from fastapi import APIRouter, Request, HTTPException, status
from datetime import datetime, timezone
from bson import ObjectId

from backend.models.schemas import EventPayload
from backend.services import mongo, n8n, detection, geo, webhooks

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/events", tags=["Events"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def ingest_event(payload: EventPayload, request: Request):
    """
    Ingest a security event.
    Stores to MongoDB and forwards to n8n for workflow evaluation.
    """
    db = mongo.get_db()

    doc = payload.model_dump()
    doc["received_at"] = datetime.now(timezone.utc)
    doc["client_ip"] = request.client.host if request.client else "unknown"

    # Geo-enrich — non-blocking; failure never fails ingestion
    geo_data = await geo.lookup(payload.source_ip)
    if geo_data:
        doc["geo"] = geo_data

    result = await db.events.insert_one(doc)
    event_id = str(result.inserted_id)

    # Audit log
    await db.audit_logs.insert_one({
        "action": "event_ingested",
        "event_id": event_id,
        "event_type": payload.event_type,
        "source_ip": payload.source_ip,
        "created_at": datetime.now(timezone.utc),
    })

    # Forward to n8n (non-blocking — failure won't fail the request)
    forwarded = {**doc, "event_id": event_id, "timestamp": doc["timestamp"].isoformat()}
    await n8n.forward_event(forwarded)

    # Run detection rules inline — create alerts for any that fire
    triggered = await detection.evaluate(doc, db)
    alerts_created = 0
    for alert in triggered:
        # Deduplication: skip if an open alert of the same type + IP already exists
        duplicate = await db.alerts.count_documents({
            "alert_type": alert["alert_type"],
            "source_ip": alert["source_ip"],
            "resolved": False,
        })
        if duplicate:
            logger.debug(
                "Dedup: skipping duplicate alert type=%s ip=%s",
                alert["alert_type"], alert["source_ip"],
            )
            continue

        now = datetime.now(timezone.utc)
        alert_doc = {
            **alert,
            "triggered_by": "detection_engine",
            "created_at": now,
            "resolved": False,
        }
        alert_result = await db.alerts.insert_one(alert_doc)
        await db.audit_logs.insert_one({
            "action": "alert_created",
            "alert_id": str(alert_result.inserted_id),
            "alert_type": alert["alert_type"],
            "source_ip": alert["source_ip"],
            "severity": alert["severity"],
            "triggered_by": "detection_engine",
            "created_at": now,
        })
        logger.info(
            "Detection alert created: rule=%s severity=%s ip=%s",
            alert.get("rule"), alert["severity"], alert["source_ip"],
        )
        alerts_created += 1

        # Fire webhooks — non-blocking, failure never fails the request
        await webhooks.fire("alert.created", {
            **alert_doc,
            "id": str(alert_result.inserted_id),
            "created_at": alert_doc["created_at"].isoformat(),
        })

    return {"status": "accepted", "event_id": event_id, "alerts_triggered": alerts_created}


@router.get("")
async def list_events(limit: int = 50, skip: int = 0):
    """Return the most recent events (max 200)."""
    if limit > 200:
        limit = 200
    db = mongo.get_db()
    cursor = db.events.find({}, {"_id": 1, "event_type": 1, "source_ip": 1, "status": 1, "timestamp": 1}) \
                      .sort("timestamp", -1).skip(skip).limit(limit)
    events = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        events.append(doc)
    return {"events": events, "count": len(events)}
