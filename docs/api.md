# AutoSecOps API Reference

Base URL: `http://localhost:8000`

All endpoints except `/health` require: `X-API-Key: <your_key>`

---

## Health

### `GET /health`
No auth required.

**Response**
```json
{ "status": "ok", "mongo": "connected", "timestamp": "2026-04-15T10:00:00Z" }
```

---

## Events

### `POST /events`
Ingest a security event. Runs all detection rules inline and creates alerts for any that fire.

**Body**
```json
{
  "event_type": "login_attempt",
  "source_ip": "192.168.1.1",
  "status": "failed",
  "user_id": "alice",
  "timestamp": "2026-04-15T12:00:00Z",
  "metadata": {}
}
```

| Field | Required | Notes |
|-------|----------|-------|
| `event_type` | Yes | Alphanumerics, underscores, hyphens only |
| `source_ip` | Yes | Valid IPv4 or IPv6 |
| `status` | Yes | `success` \| `failed` \| `blocked` \| `unknown` |
| `user_id` | No | Max 128 chars |
| `timestamp` | No | ISO 8601; defaults to server time if omitted |
| `metadata` | No | Arbitrary JSON object |

**Response** `202 Accepted`
```json
{
  "status": "accepted",
  "event_id": "64f1a2b3c4d5e6f7a8b9c0d1",
  "alerts_triggered": 0
}
```

`alerts_triggered` is the number of detection rules that fired synchronously during ingestion.

### `GET /events?limit=50&skip=0`
List recent events (max 200).

---

## Alerts

### `POST /alerts`
Create an alert directly. Used by n8n workflows and the detection engine.

**Body**
```json
{
  "alert_type": "brute_force_detected",
  "source_ip": "10.0.0.1",
  "severity": "high",
  "message": "5 failed logins from 10.0.0.1 in 60s",
  "triggered_by": "n8n:failed-login-detection",
  "metadata": {}
}
```

| Field | Required | Notes |
|-------|----------|-------|
| `alert_type` | Yes | Alphanumerics, underscores, hyphens only |
| `source_ip` | Yes | Valid IPv4 or IPv6 |
| `severity` | Yes | `low` \| `medium` \| `high` \| `critical` |
| `message` | Yes | Max 1000 chars |
| `triggered_by` | No | Defaults to `"external"` |
| `metadata` | No | Arbitrary JSON object |

**Response** `201 Created`
```json
{ "status": "created", "alert_id": "64f1a2b3c4d5e6f7a8b9c0d1" }
```

### `GET /alerts?limit=50&skip=0&resolved=false`
List alerts. Filter by `resolved` boolean.

### `PATCH /alerts/{alert_id}/resolve`
Mark an alert as resolved.

**Response** `200 OK`
```json
{ "status": "resolved", "alert_id": "64f1a2b3c4d5e6f7a8b9c0d1" }
```

---

## Block IP

### `POST /block-ip`
Add an IP to the blocklist. Idempotent — re-blocking an existing IP updates the reason.

**Body**
```json
{
  "ip": "10.0.0.1",
  "reason": "Brute force detected",
  "triggered_by": "n8n:failed-login-detection"
}
```

**Response** `201 Created`
```json
{ "status": "blocked", "ip": "10.0.0.1" }
```

### `GET /block-ip?limit=50&skip=0`
List all blocked IPs.

### `DELETE /block-ip/{ip}`
Remove an IP from the blocklist.

---

## Stats

### `GET /stats`
Platform-wide summary for dashboards and monitoring.

**Response** `200 OK`
```json
{
  "totals": {
    "events": 14823,
    "events_24h": 312,
    "alerts": 47,
    "open_alerts": 12,
    "blocked_ips": 9
  },
  "alerts_by_severity": {
    "critical": 3,
    "high": 7,
    "medium": 2
  },
  "open_alerts_by_type": {
    "brute_force_detected": 6,
    "port_scan_detected": 4,
    "credential_stuffing_detected": 2
  },
  "events_by_type_24h": {
    "login_attempt": 280,
    "port_scan": 18,
    "data_access": 14
  },
  "top_blocked_ips": [
    {
      "ip": "10.0.0.1",
      "reason": "5 failed logins in 60s",
      "triggered_by": "detection_engine",
      "blocked_at": "2026-04-15T11:22:00Z"
    }
  ]
}
```

---

## Detection Rules

The following rules run synchronously on every `POST /events`. When a rule fires, an alert is created automatically and `alerts_triggered` in the response increments.

| Rule | Trigger | Severity |
|------|---------|----------|
| `brute_force_detected` | 5+ failed `login_attempt` from same IP in 60s | high |
| `port_scan_detected` | 20+ `port_scan` events from same IP in 30s | high |
| `credential_stuffing_detected` | 10+ failed logins across 5+ distinct user IDs from same IP in 300s | critical |
| `api_abuse_detected` | 100+ events of any type from same IP in 60s | medium |
| `data_exfiltration_detected` | 5+ `data_access` events from same IP in 60s | critical |

---

## Error Responses

| Code | Meaning |
|------|---------|
| 401 | Missing or invalid API key |
| 422 | Validation error (see `detail` array) |
| 429 | Rate limit exceeded |
| 404 | Resource not found |
| 500 | Server error |
