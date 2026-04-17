from fastapi import APIRouter, HTTPException, status
from datetime import datetime, timezone

from backend.models.schemas import BlockIPRequest
from backend.services import mongo, n8n

router = APIRouter(prefix="/block-ip", tags=["Block IP"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def block_ip(payload: BlockIPRequest):
    """
    Add an IP to the blocklist.
    Idempotent — re-blocking an already-blocked IP updates the reason.
    """
    db = mongo.get_db()
    now = datetime.now(timezone.utc)

    await db.blocked_ips.update_one(
        {"ip": payload.ip},
        {"$set": {
            "ip": payload.ip,
            "reason": payload.reason,
            "triggered_by": payload.triggered_by,
            "updated_at": now,
        }, "$setOnInsert": {"blocked_at": now}},
        upsert=True,
    )

    await db.audit_logs.insert_one({
        "action": "ip_blocked",
        "ip": payload.ip,
        "reason": payload.reason,
        "triggered_by": payload.triggered_by,
        "created_at": now,
    })

    await n8n.forward_block(payload.ip, payload.reason, payload.triggered_by)

    return {"status": "blocked", "ip": payload.ip}


@router.get("")
async def list_blocked_ips(limit: int = 50, skip: int = 0):
    """Return the blocked IP list."""
    if limit > 200:
        limit = 200
    db = mongo.get_db()
    cursor = db.blocked_ips.find({}).sort("blocked_at", -1).skip(skip).limit(limit)
    ips = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        ips.append(doc)
    return {"blocked_ips": ips, "count": len(ips)}


@router.delete("/{ip}")
async def unblock_ip(ip: str):
    """Remove an IP from the blocklist."""
    db = mongo.get_db()
    result = await db.blocked_ips.delete_one({"ip": ip})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="IP not in blocklist")

    await db.audit_logs.insert_one({
        "action": "ip_unblocked",
        "ip": ip,
        "created_at": datetime.now(timezone.utc),
    })
    return {"status": "unblocked", "ip": ip}
