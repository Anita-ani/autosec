"""
Stats endpoint — aggregated summary for dashboards and monitoring.
All queries hit MongoDB directly; results are not cached (use a caching layer in Phase 3).
"""
from fastapi import APIRouter, Depends
from datetime import datetime, timezone, timedelta

from backend.dependencies import require_any_role
from backend.services import mongo

router = APIRouter(prefix="/stats", tags=["Stats"])


@router.get("", dependencies=[Depends(require_any_role)])
async def get_stats():
    """
    Return platform-wide summary statistics:
    - Total counts (events, alerts, open alerts, blocked IPs)
    - Alerts broken down by severity
    - Top 10 event types in the last 24 hours
    - 5 most recently blocked IPs
    """
    db = mongo.get_db()
    since_24h = datetime.now(timezone.utc) - timedelta(hours=24)

    # ─ Totals (parallel count queries)
    total_events = await db.events.count_documents({})
    total_alerts = await db.alerts.count_documents({})
    open_alerts = await db.alerts.count_documents({"resolved": False})
    total_blocked = await db.blocked_ips.count_documents({})
    events_24h = await db.events.count_documents({"timestamp": {"$gte": since_24h}})

    # ─ Alerts by severity
    severity_pipeline = [
        {"$group": {"_id": "$severity", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    severity_results = await db.alerts.aggregate(severity_pipeline).to_list(10)
    alerts_by_severity = {r["_id"]: r["count"] for r in severity_results if r["_id"]}

    # ─ Alerts by type (top 10) 
    alert_type_pipeline = [
        {"$match": {"resolved": False}},
        {"$group": {"_id": "$alert_type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    alert_type_results = await db.alerts.aggregate(alert_type_pipeline).to_list(10)
    open_alerts_by_type = {r["_id"]: r["count"] for r in alert_type_results if r["_id"]}

    # ─ Events by type — last 24h 
    type_pipeline = [
        {"$match": {"timestamp": {"$gte": since_24h}}},
        {"$group": {"_id": "$event_type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    type_results = await db.events.aggregate(type_pipeline).to_list(10)
    events_by_type_24h = {r["_id"]: r["count"] for r in type_results if r["_id"]}

    # ─ Top source countries (last 24h, enriched events only)
    country_pipeline = [
        {"$match": {"timestamp": {"$gte": since_24h}, "geo.country_code": {"$exists": True}}},
        {"$group": {"_id": {"code": "$geo.country_code", "name": "$geo.country"}, "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    country_results = await db.events.aggregate(country_pipeline).to_list(10)
    top_source_countries = [
        {"country": r["_id"]["name"], "country_code": r["_id"]["code"], "count": r["count"]}
        for r in country_results if r["_id"]["code"]
    ]

    # ─ Top 5 recently blocked IPs
    top_blocked_pipeline = [
        {"$sort": {"blocked_at": -1}},
        {"$limit": 5},
        {"$project": {"_id": 0, "ip": 1, "reason": 1, "triggered_by": 1, "blocked_at": 1}},
    ]
    top_blocked = await db.blocked_ips.aggregate(top_blocked_pipeline).to_list(5)
    # Convert datetime fields to ISO strings for JSON serialisation
    for entry in top_blocked:
        if isinstance(entry.get("blocked_at"), datetime):
            entry["blocked_at"] = entry["blocked_at"].isoformat()

    return {
        "totals": {
            "events": total_events,
            "events_24h": events_24h,
            "alerts": total_alerts,
            "open_alerts": open_alerts,
            "blocked_ips": total_blocked,
        },
        "alerts_by_severity": alerts_by_severity,
        "open_alerts_by_type": open_alerts_by_type,
        "events_by_type_24h": events_by_type_24h,
        "top_source_countries": top_source_countries,
        "top_blocked_ips": top_blocked,
    }
