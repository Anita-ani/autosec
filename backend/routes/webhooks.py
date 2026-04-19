"""
Webhook management — CRUD for outbound webhook subscriptions.

POST   /webhooks          — register a new webhook
GET    /webhooks          — list all webhooks
DELETE /webhooks/{id}     — remove a webhook
PATCH  /webhooks/{id}     — enable / disable a webhook
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId
from datetime import datetime, timezone

from backend.dependencies import require_operator, require_any_role
from backend.models.schemas import WebhookConfig
from backend.services import mongo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


def _serialize(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    if isinstance(doc.get("created_at"), datetime):
        doc["created_at"] = doc["created_at"].isoformat()
    return doc


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_operator)])
async def create_webhook(body: WebhookConfig):
    """Register a new webhook subscription."""
    db = mongo.get_db()
    doc = body.model_dump()
    doc["created_at"] = datetime.now(timezone.utc)
    result = await db.webhooks.insert_one(doc)
    webhook_id = str(result.inserted_id)

    await db.audit_logs.insert_one({
        "action": "webhook_created",
        "webhook_id": webhook_id,
        "url": body.url,
        "events": body.events,
        "created_at": doc["created_at"],
    })

    return {
        "id": webhook_id,
        **body.model_dump(),
        "created_at": doc["created_at"].isoformat(),
    }


@router.get("", dependencies=[Depends(require_any_role)])
async def list_webhooks():
    """Return all registered webhooks (secrets are omitted from the response)."""
    db = mongo.get_db()
    cursor = db.webhooks.find({}, {"secret": 0})
    hooks = []
    async for doc in cursor:
        hooks.append(_serialize(doc))
    return {"webhooks": hooks, "count": len(hooks)}


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_operator)])
async def delete_webhook(webhook_id: str):
    """Remove a webhook by ID."""
    if not ObjectId.is_valid(webhook_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook ID")

    db = mongo.get_db()
    result = await db.webhooks.delete_one({"_id": ObjectId(webhook_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")

    await db.audit_logs.insert_one({
        "action": "webhook_deleted",
        "webhook_id": webhook_id,
        "created_at": datetime.now(timezone.utc),
    })


@router.patch("/{webhook_id}", dependencies=[Depends(require_operator)])
async def toggle_webhook(webhook_id: str, enabled: bool):
    """Enable or disable a webhook without deleting it."""
    if not ObjectId.is_valid(webhook_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook ID")

    db = mongo.get_db()
    result = await db.webhooks.update_one(
        {"_id": ObjectId(webhook_id)},
        {"$set": {"enabled": enabled}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")

    return {"id": webhook_id, "enabled": enabled}


@router.get("/{webhook_id}/deliveries", dependencies=[Depends(require_any_role)])
async def list_deliveries(webhook_id: str, limit: int = 50):
    """Return recent delivery attempts for a webhook (newest first)."""
    if not ObjectId.is_valid(webhook_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook ID")
    if limit > 200:
        limit = 200

    db = mongo.get_db()
    cursor = db.webhook_delivery_log.find(
        {"webhook_id": webhook_id},
        {"_id": 0},
    ).sort("delivered_at", -1).limit(limit)

    logs = []
    async for doc in cursor:
        if isinstance(doc.get("delivered_at"), datetime):
            doc["delivered_at"] = doc["delivered_at"].isoformat()
        logs.append(doc)

    return {"webhook_id": webhook_id, "deliveries": logs, "count": len(logs)}
