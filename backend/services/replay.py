"""
Replay engine — re-evaluates detection rules over a historical time window.

Useful for:
  - Testing a newly added rule against existing data without re-ingesting events
  - Auditing gaps in historical detection
  - Reproducing past incidents in a staging environment

The replay does NOT re-insert raw events (they already exist).  It fetches
events from the given window, runs each through the detection engine, and
returns a summary of which rules fired and how many new alerts would be
created (dry_run=True, the default) or actually creates them (dry_run=False).

Deduplication is respected in both modes: an alert is only counted/created if
no unresolved alert of the same type + IP already exists.
"""
import logging
from datetime import datetime, timezone

from backend.services import mongo
from backend.services import detection

logger = logging.getLogger(__name__)


async def run(
    since: datetime,
    until: datetime,
    dry_run: bool = True,
    batch_size: int = 500,
) -> dict:
    """
    Replay detection rules over events in [since, until].

    Returns:
        {
            "window": {"since": ..., "until": ...},
            "dry_run": bool,
            "events_scanned": int,
            "rules_fired": {"rule_name": count, ...},
            "alerts_created": int,   # 0 when dry_run=True
            "alerts_skipped_dedup": int,
        }
    """
    if since >= until:
        raise ValueError("since must be before until")

    db = mongo.get_db()
    query = {"timestamp": {"$gte": since, "$lt": until}}

    events_scanned = 0
    rules_fired: dict[str, int] = {}
    alerts_created = 0
    alerts_skipped = 0

    # Stream events in batches to avoid loading the full collection into memory
    cursor = db.events.find(query).sort("timestamp", 1)
    batch: list[dict] = []

    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        batch.append(doc)
        if len(batch) >= batch_size:
            created, skipped, fired = await _process_batch(batch, db, dry_run)
            alerts_created += created
            alerts_skipped += skipped
            for rule, count in fired.items():
                rules_fired[rule] = rules_fired.get(rule, 0) + count
            events_scanned += len(batch)
            batch = []

    # Remainder
    if batch:
        created, skipped, fired = await _process_batch(batch, db, dry_run)
        alerts_created += created
        alerts_skipped += skipped
        for rule, count in fired.items():
            rules_fired[rule] = rules_fired.get(rule, 0) + count
        events_scanned += len(batch)

    logger.info(
        "Replay complete: window=%s/%s dry_run=%s scanned=%d fired=%s created=%d skipped=%d",
        since.isoformat(), until.isoformat(), dry_run,
        events_scanned, rules_fired, alerts_created, alerts_skipped,
    )

    return {
        "window": {
            "since": since.isoformat(),
            "until": until.isoformat(),
        },
        "dry_run": dry_run,
        "events_scanned": events_scanned,
        "rules_fired": rules_fired,
        "alerts_created": alerts_created,
        "alerts_skipped_dedup": alerts_skipped,
    }


async def _process_batch(
    events: list[dict],
    db,
    dry_run: bool,
) -> tuple[int, int, dict[str, int]]:
    """Process a batch of events through the detection engine."""
    created = 0
    skipped = 0
    fired: dict[str, int] = {}

    for event in events:
        triggered = await detection.evaluate(event, db)
        for alert in triggered:
            rule = alert.get("rule", "unknown")
            fired[rule] = fired.get(rule, 0) + 1

            # Dedup check
            duplicate = await db.alerts.count_documents({
                "alert_type": alert["alert_type"],
                "source_ip": alert["source_ip"],
                "resolved": False,
            })
            if duplicate:
                skipped += 1
                continue

            if not dry_run:
                now = datetime.now(timezone.utc)
                await db.alerts.insert_one({
                    **alert,
                    "triggered_by": "replay_engine",
                    "created_at": now,
                    "resolved": False,
                })
                await db.audit_logs.insert_one({
                    "action": "alert_created",
                    "alert_type": alert["alert_type"],
                    "source_ip": alert["source_ip"],
                    "severity": alert["severity"],
                    "triggered_by": "replay_engine",
                    "created_at": now,
                })
            created += 1

    return created, skipped, fired
