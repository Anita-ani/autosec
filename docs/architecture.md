# AutoSecOps — Architecture

## Overview

```
  External Systems / Agents
          │
          ▼  POST /events
  ┌───────────────────────┐
  │      FastAPI API      │  ← API key auth, rate limiting, input validation
  └──────────┬────────────┘
             │
     ┌───────┴────────┐
     │                │
     ▼                ▼
  MongoDB          Detection Engine          n8n (Webhook)
  (store)      (5 inline rules)             (evaluate workflows)
                     │                            │
                     │ alert fired          ┌─────┴──────────┐
                     ▼                      │                │
              POST /alerts ◄────────── Workflow 01–06   POST /block-ip
              (db.alerts)               (per rule)      (db.blocked_ips)
                                             │
                                        Slack / Email
                                        notification
```

---

## Components

| Component | Role | Port |
|-----------|------|------|
| FastAPI backend | Event ingestion, REST API, audit trail, inline detection | 8000 |
| MongoDB | Persistent storage (events, alerts, blocked_ips, audit_logs) | 27017 |
| Redis | Rate-limiter state (sliding window sorted sets); auto-expires via TTL | 6379 |
| n8n | Workflow automation engine — secondary detection and notification | 5678 |

---

## Data Flow

### Event Ingestion (`POST /events`)

1. Client sends a `POST /events` payload
2. FastAPI validates with Pydantic (IP via `ipaddress` stdlib, event_type regex-sanitized)
3. Event is stored in `events` collection; audit log entry written
4. **Detection engine runs synchronously** — all 5 rules evaluated inline:
   - Each rule calls `count_documents` (or `aggregate`) on the `events` collection
   - If threshold exceeded, an alert document is inserted into `alerts` collection and an audit log entry written
5. Event forwarded to n8n via webhook (non-blocking — failure never fails the ingest request)
6. n8n evaluates its own workflows in parallel:
   - **Workflow 01**: failed login detection (>5 per IP / 60s → block)
   - **Workflow 02**: high-frequency IP detection (>20 events / 5min → block)
   - **Workflow 03**: alert aggregation (scheduled every 5 min)
   - **Workflow 04**: block-IP notification handler
   - **Workflow 05**: port scan detection (>20 probes / 30s → alert + block)
   - **Workflow 06**: credential stuffing detection (10+ failures / 5+ accounts / 300s → critical alert + block)
7. When n8n triggers a block: `POST /block-ip` → upsert to `blocked_ips`, audit log, re-notify n8n
8. When n8n creates an alert: `POST /alerts` → insert to `alerts`, audit log

### Alert Creation

Alerts can be created by three paths:
- **Detection engine** (synchronous, inline on every ingest) — `triggered_by: "detection_engine"`
- **n8n workflows** (async, via `POST /alerts`) — `triggered_by: "n8n:<workflow-name>"`
- **External callers** (direct API) — `triggered_by: "external"` or custom

### Stats (`GET /stats`)

Aggregates across all four collections using MongoDB pipelines:
- Total counts (events, events 24h, alerts, open alerts, blocked IPs)
- Alerts grouped by severity
- Open alerts grouped by type
- Top 10 event types in the last 24h
- 5 most recently blocked IPs

---

## Detection Rules

All rules are stateless and query MongoDB directly — they work correctly across multiple Uvicorn workers.

| Rule | Event type | Condition | Severity |
|------|-----------|-----------|----------|
| `BruteForceRule` | `login_attempt` + `status=failed` | ≥ 5 from same IP in 60s | high |
| `PortScanRule` | `port_scan` | ≥ 20 from same IP in 30s | high |
| `CredentialStuffingRule` | `login_attempt` + `status=failed` | ≥ 10 failures across ≥ 5 distinct user_ids from same IP in 300s | critical |
| `APIAbuseRule` | any | ≥ 100 from same IP in 60s | medium |
| `DataExfiltrationRule` | `data_access` | ≥ 5 from same IP in 60s | critical |

Rule failures are caught and logged — a broken rule never crashes the ingest request.

---

## Security Controls

| Control | Implementation |
|---------|---------------|
| API key authentication | Constant-time `hmac.compare_digest`; fail-closed; returns `JSONResponse` (not `raise HTTPException`) |
| Rate limiting | Redis sliding-window (sorted sets) per client IP; in-memory fallback when `REDIS_URL` unset; fail-open on Redis error |
| Input validation | Pydantic v2 strict schemas; IP via `ipaddress.ip_address()`; event_type regex-sanitized |
| Alert deduplication | Before inserting a detection alert, `count_documents` checks for an unresolved alert of the same type + IP; skips if duplicate |
| Structured logging | `python-json-logger` on every log line; X-Request-ID UUID propagated via `ContextVar` across all log records in a request |
| CORS | Driven by `CORS_ORIGINS` env var (comma-separated); defaults to `*` in dev — always set in production |
| Docker hardening | `read_only: true`, `tmpfs: [/tmp]`, `cap_drop: ALL`, `no-new-privileges:true`, `mem_limit: 512m`, `cpus: 1.0` |
| Non-root container | Backend runs as `appuser` |
| No hardcoded secrets | All credentials via environment variables / `.env` |
| Audit log | Every action (ingest, block, alert create/resolve) written to `audit_logs` collection |

---

## File Layout

```
autosecops/
├── backend/
│   ├── main.py                     # FastAPI app, lifespan, middleware registration
│   ├── Dockerfile                  # Build context = project root
│   ├── requirements.txt
│   ├── models/
│   │   └── schemas.py              # EventPayload, BlockIPRequest, AlertCreate, AlertOut
│   ├── middleware/
│   │   ├── auth.py                 # APIKeyMiddleware
│   │   ├── rate_limit.py           # RateLimitMiddleware + cleanup_stale_ips()
│   │   └── request_logger.py       # Structured access log
│   ├── routes/
│   │   ├── events.py               # POST /events, GET /events
│   │   ├── alerts.py               # POST /alerts, GET /alerts, PATCH /alerts/:id/resolve
│   │   ├── block_ip.py             # POST /block-ip, GET /block-ip, DELETE /block-ip/:ip
│   │   ├── health.py               # GET /health
│   │   └── stats.py                # GET /stats
│   └── services/
│       ├── mongo.py                # Motor client, get_db(), init_indexes()
│       ├── n8n.py                  # forward_event(), forward_block()
│       └── detection.py            # 5 detection rules + evaluate()
├── n8n/workflows/                  # 01–06 workflow JSON files
├── docker-compose.yml              # Project root — run: docker compose up -d
├── docker/
│   └── Dockerfile                  # Referenced by docker-compose.yml
├── tests/
│   ├── conftest.py                 # Fixtures: client, mock_mongo, mock_n8n
│   ├── test_events.py              # Includes alert deduplication tests
│   ├── test_alerts.py
│   ├── test_block_ip.py
│   ├── test_health.py
│   ├── test_detection.py
│   ├── test_stats.py
│   └── test_rate_limit.py          # In-memory path, Redis path, fail-open
└── scripts/
    ├── seed_events.py
    ├── import_n8n_workflows.py     # Auto-import all 6 workflows into n8n
    └── check_health.sh
```
