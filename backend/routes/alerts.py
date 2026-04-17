from fastapi import APIRouter, HTTPException, status
from datetime import datetime, timezone

from backend.models.schemas import AlertCreate
from backend.services import mongo, triage as triage_svc

router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_alert(payload: AlertCreate):
    """
    Create an alert directly.
    Used by n8n workflows and the internal detection engine.
    """
    db = mongo.get_db()
    now = datetime.now(timezone.utc)

    doc = payload.model_dump()
    doc["created_at"] = now
    doc["resolved"] = False

    result = await db.alerts.insert_one(doc)
    alert_id = str(result.inserted_id)

    await db.audit_logs.insert_one({
        "action": "alert_created",
        "alert_id": alert_id,
        "alert_type": payload.alert_type,
        "source_ip": payload.source_ip,
        "severity": payload.severity,
        "triggered_by": payload.triggered_by,
        "created_at": now,
    })

    return {"status": "created", "alert_id": alert_id}


@router.get("")
async def list_alerts(limit: int = 50, skip: int = 0, resolved: bool | None = None):
    """List alerts, optionally filtered by resolved status."""
    if limit > 200:
        limit = 200
    db = mongo.get_db()
    query: dict = {}
    if resolved is not None:
        query["resolved"] = resolved

    cursor = db.alerts.find(query).sort("created_at", -1).skip(skip).limit(limit)
    alerts = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        alerts.append(doc)
    return {"alerts": alerts, "count": len(alerts)}


@router.patch("/{alert_id}/resolve")
async def resolve_alert(alert_id: str):
    """Mark an alert as resolved."""
    from bson import ObjectId
    from bson.errors import InvalidId
    db = mongo.get_db()
    try:
        oid = ObjectId(alert_id)
    except InvalidId:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid alert ID")

    result = await db.alerts.update_one(
        {"_id": oid},
        {"$set": {"resolved": True, "resolved_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

    await mongo.get_db().audit_logs.insert_one({
        "action": "alert_resolved",
        "alert_id": alert_id,
        "created_at": datetime.now(timezone.utc),
    })
    return {"status": "resolved", "alert_id": alert_id}


@router.get("/{alert_id}/triage")
async def triage_alert(alert_id: str):
    """
    Generate an AI-assisted triage report for an alert.

    Calls Claude (claude-sonnet-4-6) with the alert context and recent related
    events from the same source IP. Requires ANTHROPIC_API_KEY to be set.

    Returns a summary, severity assessment, and remediation steps.
    """
    from bson import ObjectId
    from bson.errors import InvalidId

    db = mongo.get_db()
    try:
        oid = ObjectId(alert_id)
    except InvalidId:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid alert ID")

    alert = await db.alerts.find_one({"_id": oid})
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

    alert["_id"] = str(alert["_id"])

    try:
        report = await triage_svc.run(alert, db)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    return report
