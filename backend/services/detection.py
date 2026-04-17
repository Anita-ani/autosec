"""
Detection engine — evaluates security rules on every ingested event.

Rules query MongoDB directly for historical context, so they work correctly
across multiple workers and don't rely on in-memory state.

Each rule:
  - matches(event)   — quick pre-filter; skip expensive DB query if irrelevant
  - evaluate(event, db) — async; returns an alert dict if threshold exceeded, else None

Failures in individual rules are logged but never crash the ingest request.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)


# ── Base class ────────────────────────────────────────────────────────────────

class DetectionRule:
    name: str
    severity: str
    alert_type: str

    def matches(self, event: dict) -> bool:
        raise NotImplementedError

    async def evaluate(self, event: dict, db) -> Optional[dict]:
        raise NotImplementedError


# ── Rules ─────────────────────────────────────────────────────────────────────

class BruteForceRule(DetectionRule):
    """5+ failed login_attempts from the same IP within 60 seconds → high."""
    name = "brute_force"
    severity = "high"
    alert_type = "brute_force_detected"
    threshold = 5
    window_seconds = 60

    def matches(self, event: dict) -> bool:
        return event.get("event_type") == "login_attempt" and event.get("status") == "failed"

    async def evaluate(self, event: dict, db) -> Optional[dict]:
        since = datetime.now(timezone.utc) - timedelta(seconds=self.window_seconds)
        count = await db.events.count_documents({
            "source_ip": event["source_ip"],
            "event_type": "login_attempt",
            "status": "failed",
            "timestamp": {"$gte": since},
        })
        if count >= self.threshold:
            return {
                "alert_type": self.alert_type,
                "source_ip": event["source_ip"],
                "severity": self.severity,
                "message": (
                    f"{count} failed login attempts from {event['source_ip']} "
                    f"in {self.window_seconds}s"
                ),
                "rule": self.name,
                "event_count": count,
            }
        return None


class PortScanRule(DetectionRule):
    """20+ port_scan events from the same IP within 30 seconds → high."""
    name = "port_scan"
    severity = "high"
    alert_type = "port_scan_detected"
    threshold = 20
    window_seconds = 30

    def matches(self, event: dict) -> bool:
        return event.get("event_type") == "port_scan"

    async def evaluate(self, event: dict, db) -> Optional[dict]:
        since = datetime.now(timezone.utc) - timedelta(seconds=self.window_seconds)
        count = await db.events.count_documents({
            "source_ip": event["source_ip"],
            "event_type": "port_scan",
            "timestamp": {"$gte": since},
        })
        if count >= self.threshold:
            return {
                "alert_type": self.alert_type,
                "source_ip": event["source_ip"],
                "severity": self.severity,
                "message": (
                    f"Port scan detected: {count} probes from {event['source_ip']} "
                    f"in {self.window_seconds}s"
                ),
                "rule": self.name,
                "event_count": count,
            }
        return None


class CredentialStuffingRule(DetectionRule):
    """10+ failed logins from one IP across 5+ distinct user_ids in 300s → critical."""
    name = "credential_stuffing"
    severity = "critical"
    alert_type = "credential_stuffing_detected"
    threshold = 10
    distinct_user_threshold = 5
    window_seconds = 300

    def matches(self, event: dict) -> bool:
        return event.get("event_type") == "login_attempt" and event.get("status") == "failed"

    async def evaluate(self, event: dict, db) -> Optional[dict]:
        since = datetime.now(timezone.utc) - timedelta(seconds=self.window_seconds)
        pipeline = [
            {"$match": {
                "source_ip": event["source_ip"],
                "event_type": "login_attempt",
                "status": "failed",
                "timestamp": {"$gte": since},
            }},
            {"$group": {
                "_id": None,
                "count": {"$sum": 1},
                "distinct_users": {"$addToSet": "$user_id"},
            }},
        ]
        results = await db.events.aggregate(pipeline).to_list(1)
        if not results:
            return None
        r = results[0]
        count = r.get("count", 0)
        distinct = len([u for u in r.get("distinct_users", []) if u is not None])
        if count >= self.threshold and distinct >= self.distinct_user_threshold:
            return {
                "alert_type": self.alert_type,
                "source_ip": event["source_ip"],
                "severity": self.severity,
                "message": (
                    f"Credential stuffing detected: {count} failed logins across "
                    f"{distinct} accounts from {event['source_ip']} in {self.window_seconds}s"
                ),
                "rule": self.name,
                "event_count": count,
                "distinct_users": distinct,
            }
        return None


class APIAbuseRule(DetectionRule):
    """100+ events of any type from the same IP within 60 seconds → medium."""
    name = "api_abuse"
    severity = "medium"
    alert_type = "api_abuse_detected"
    threshold = 100
    window_seconds = 60

    def matches(self, event: dict) -> bool:
        return True  # Applies to all event types

    async def evaluate(self, event: dict, db) -> Optional[dict]:
        since = datetime.now(timezone.utc) - timedelta(seconds=self.window_seconds)
        count = await db.events.count_documents({
            "source_ip": event["source_ip"],
            "timestamp": {"$gte": since},
        })
        if count >= self.threshold:
            return {
                "alert_type": self.alert_type,
                "source_ip": event["source_ip"],
                "severity": self.severity,
                "message": (
                    f"API abuse detected: {count} requests from {event['source_ip']} "
                    f"in {self.window_seconds}s"
                ),
                "rule": self.name,
                "event_count": count,
            }
        return None


class DataExfiltrationRule(DetectionRule):
    """5+ data_access events from the same IP within 60 seconds → critical."""
    name = "data_exfiltration"
    severity = "critical"
    alert_type = "data_exfiltration_detected"
    threshold = 5
    window_seconds = 60

    def matches(self, event: dict) -> bool:
        return event.get("event_type") == "data_access"

    async def evaluate(self, event: dict, db) -> Optional[dict]:
        since = datetime.now(timezone.utc) - timedelta(seconds=self.window_seconds)
        count = await db.events.count_documents({
            "source_ip": event["source_ip"],
            "event_type": "data_access",
            "timestamp": {"$gte": since},
        })
        if count >= self.threshold:
            return {
                "alert_type": self.alert_type,
                "source_ip": event["source_ip"],
                "severity": self.severity,
                "message": (
                    f"Possible data exfiltration: {count} data_access events from "
                    f"{event['source_ip']} in {self.window_seconds}s"
                ),
                "rule": self.name,
                "event_count": count,
            }
        return None


# ── Rule registry ─────────────────────────────────────────────────────────────

RULES: list[DetectionRule] = [
    BruteForceRule(),
    PortScanRule(),
    CredentialStuffingRule(),
    APIAbuseRule(),
    DataExfiltrationRule(),
]


# ── Public API ────────────────────────────────────────────────────────────────

async def evaluate(event: dict, db) -> list[dict]:
    """
    Run all matching detection rules against the given event.
    Returns a list of alert dicts for every rule that fired.
    Failures in individual rules are caught and logged — never crash the caller.
    """
    triggered = []
    for rule in RULES:
        if not rule.matches(event):
            continue
        try:
            result = await rule.evaluate(event, db)
            if result:
                triggered.append(result)
        except Exception as exc:
            logger.warning("Detection rule %s failed (non-fatal): %s", rule.name, exc)
    return triggered
