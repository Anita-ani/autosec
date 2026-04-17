"""
MongoDB service — single Motor async client shared across the app.
Collections: events, alerts, blocked_ips, audit_logs
"""
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING
import os
import logging

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        uri = os.environ["MONGO_URI"]
        _client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    return _client


def get_db():
    return get_client()[os.environ.get("MONGO_DB", "autosecops")]


async def init_indexes():
    """Create indexes on startup — idempotent."""
    db = get_db()
    await db.events.create_index([("source_ip", ASCENDING), ("timestamp", DESCENDING)])
    await db.events.create_index([("event_type", ASCENDING)])
    await db.alerts.create_index([("source_ip", ASCENDING), ("created_at", DESCENDING)])
    await db.alerts.create_index([("resolved", ASCENDING)])
    await db.blocked_ips.create_index([("ip", ASCENDING)], unique=True)
    await db.audit_logs.create_index([("created_at", DESCENDING)])
    logger.info("MongoDB indexes initialized")


async def close_client():
    global _client
    if _client:
        _client.close()
        _client = None
