# AutoSecOps — Implementation Runbook

A step-by-step guide for DevOps engineers to stand up the full AutoSecOps platform, wire n8n automation workflows, and verify end-to-end threat detection and response.

---

## Table of Contents

1. [What This Platform Does](#1-what-this-platform-does)
2. [Prerequisites](#2-prerequisites)
3. [Repository Layout](#3-repository-layout)
4. [Environment Setup](#4-environment-setup)
5. [Start the Stack](#5-start-the-stack)
6. [Import n8n Workflows](#6-import-n8n-workflows)
7. [Configure n8n Environment Variables](#7-configure-n8n-environment-variables)
8. [Workflow Reference](#8-workflow-reference)
9. [Verify End-to-End Automation](#9-verify-end-to-end-automation)
10. [API Quick Reference](#10-api-quick-reference)
11. [Dashboard](#11-dashboard)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. What This Platform Does

AutoSecOps is a security automation platform that:

- **Ingests** security events (login attempts, port scans, API abuse, etc.) via a FastAPI backend
- **Detects** threats in real time using an inline detection engine (5 rules: BruteForce, PortScan, CredentialStuffing, APIAbuse, DataExfiltration)
- **Automates responses** through n8n workflows — blocking IPs, creating alerts, and sending Slack notifications
- **Visualises** live security posture through a React dashboard

```
Your App / SIEM
      │  POST /events  (security event stream)
      ▼
┌─────────────┐     forwards      ┌─────────────┐
│  FastAPI    │ ──────────────▶  │     n8n      │
│  Backend   │                   │  Workflows  │
│  :8000     │ ◀── block/alert ── │  :5678      │
└─────────────┘                   └─────────────┘
      │  read/write
      ▼
┌─────────────┐   ┌─────────────┐
│  MongoDB    │   │    Redis     │
│  :27017     │   │  rate limit │
└─────────────┘   └─────────────┘
```

---

## 2. Prerequisites

| Tool | Minimum Version | Notes |
|------|----------------|-------|
| Docker | 24.x | Required for the full stack |
| Docker Compose | v2 (plugin) | Use `docker compose`, not `docker-compose` |
| Python | 3.12+ | Only needed to run helper scripts |
| curl | any | For smoke tests |

> **No local MongoDB, Redis, or Python runtime is needed to run the platform** — everything runs in Docker. Python is only used for the import and seed scripts.

---

## 3. Repository Layout

```
autosec/
├── backend/
│   ├── main.py               # FastAPI app entry point
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── models/schemas.py     # Pydantic schemas
│   ├── middleware/           # Rate limiting, request logging, RBAC
│   ├── routes/               # events, alerts, block-ip, health, stats,
│   │                         # replay, webhooks, auth
│   └── services/             # MongoDB client, n8n forwarder,
│                             # detection engine, geo, triage, webhooks
├── n8n/workflows/            # 6 workflow JSON files (01–06)
├── frontend/                 # React + Vite dashboard
├── docker-compose.yml        # Run from project root
├── .env.example              # Copy to .env before starting
├── tests/                    # pytest suite (zero infrastructure required)
├── scripts/
│   ├── seed_events.py        # Sends test events to exercise workflows
│   ├── import_n8n_workflows.py  # Auto-imports all workflows into n8n
│   └── check_health.sh       # Quick health check
└── docs/
    ├── runbook.md            # This file
    ├── api.md                # Full API reference
    ├── architecture.md       # System architecture details
    └── workflows.md          # n8n workflow deep-dives
```

---

## 4. Environment Setup

### 4.1 Create your `.env` file

```bash
cp .env.example .env
```

Open `.env` and fill in the three required secrets:

```dotenv
# ── Required ──────────────────────────────────────────────────────────────────
MONGO_PASSWORD=choose-a-strong-password
API_KEY=generate-a-32-char-random-string
N8N_PASSWORD=your-n8n-dashboard-password

# ── Optional ──────────────────────────────────────────────────────────────────
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...   # Slack alerts
ALERT_EMAIL=security@yourcompany.com

# ── Defaults (safe to leave as-is for local dev) ──────────────────────────────
MONGO_USER=autosec
N8N_USER=admin
BACKEND_PORT=8000
N8N_PORT=5678
RATE_LIMIT_REQUESTS=60
RATE_LIMIT_WINDOW_SECONDS=60
```

**Generating a secure `API_KEY`:**

```bash
# Linux / macOS
openssl rand -hex 32

# Windows PowerShell
[System.Web.Security.Membership]::GeneratePassword(32, 0)
```

> The stack will **refuse to start** if `MONGO_PASSWORD`, `API_KEY`, or `N8N_PASSWORD` are missing.

---

## 5. Start the Stack

Run all commands from the **project root** (the directory containing `docker-compose.yml`).

### 5.1 Start all services

```bash
docker compose up -d
```

This starts four containers:

| Container | Service | Port |
|-----------|---------|------|
| `autosec-mongo` | MongoDB 7.0 | internal only |
| `autosec-redis` | Redis 7 (Alpine) | internal only |
| `autosec-backend` | FastAPI backend | `localhost:8000` |
| `autosec-n8n` | n8n | `localhost:5678` |

### 5.2 Wait for health checks to pass

```bash
docker compose ps
```

All containers should show `healthy` or `running` within ~60 seconds. If backend is still starting, wait for MongoDB and Redis health checks to pass first — backend has `depends_on` with health conditions.

### 5.3 Verify the backend is up

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "ok",
  "mongo": "connected",
  "redis": "connected",
  "timestamp": "2026-04-17T10:00:00+00:00"
}
```

If `status` is `degraded`, check `docker compose logs mongo` or `docker compose logs redis`.

---

## 6. Import n8n Workflows

n8n does **not** auto-load workflow files from disk. You must import them explicitly — either via the script or the UI.

### Option A — Automated (recommended)

```bash
pip install httpx   # one-time install if not already present

N8N_PASSWORD=your-n8n-password python scripts/import_n8n_workflows.py
```

This imports all 6 workflow files from `n8n/workflows/` in one shot. You'll see a confirmation line for each workflow.

### Option B — Manual via UI

1. Open **http://localhost:5678** in your browser
2. Log in with username `admin` (or `N8N_USER`) and your `N8N_PASSWORD`
3. Click the **+** (new workflow) button → **Import from file**
4. Upload each file from `n8n/workflows/` one at a time:
   - `01_failed_login_detection.json`
   - `02_suspicious_ip_detection.json`
   - `03_alert_aggregation.json`
   - `04_block_ip_handler.json`
   - `05_port_scan_detection.json`
   - `06_credential_stuffing_detection.json`
5. After importing each workflow, click **Activate** (toggle in the top-right)

> All 6 workflows must be **active** for the automation to work.

---

## 7. Configure n8n Environment Variables

The workflows read two environment variables that n8n resolves at runtime:

| Variable | Value | Where it's set |
|----------|-------|---------------|
| `AUTOSEC_BACKEND_URL` | `http://backend:8000` | `docker-compose.yml` (auto-set) |
| `AUTOSEC_API_KEY` | your `API_KEY` value | `docker-compose.yml` (auto-set from `.env`) |
| `SLACK_WEBHOOK_URL` | your Slack webhook URL | `docker-compose.yml` (optional) |

These are already wired in `docker-compose.yml` under the `n8n` service — **no manual action required** as long as your `.env` is populated correctly.

To verify n8n can see them:
1. In n8n, open any workflow
2. Click on an HTTP Request node that calls the backend
3. The URL field should show `={{ $env.AUTOSEC_BACKEND_URL }}/...` and resolve correctly when you test the node

---

## 8. Workflow Reference

### Workflow 01 — Failed Login Detection

**Trigger:** Webhook — every `POST /events` forwarded from the backend  
**Purpose:** Detect brute-force login attacks from a single IP

**Logic:**
1. Receives all security events via webhook
2. Filters for `event_type=login_attempt` AND `status=failed`
3. Counts failures per source IP using a 60-second sliding window (in-memory via n8n static data)
4. If failures **≥ 5 in 60 seconds**:
   - Calls `POST /block-ip` on the backend to block the IP
   - Sends a Slack notification (if `SLACK_WEBHOOK_URL` is set)

**Thresholds:**
- Window: 60 seconds
- Trigger: 5 failed logins

---

### Workflow 02 — Suspicious IP Detection

**Trigger:** Webhook — every `POST /events` forwarded from the backend  
**Purpose:** Detect high-frequency activity from any single IP regardless of event type

**Logic:**
1. Receives all security events
2. Tracks total event count per IP in a 5-minute sliding window
3. If count **≥ 20 events in 5 minutes**:
   - Calls `POST /block-ip` on the backend

**Thresholds:**
- Window: 5 minutes
- Trigger: 20 events of any type

---

### Workflow 03 — Alert Aggregation (Scheduled)

**Trigger:** Schedule — runs every 5 minutes  
**Purpose:** Summarise open alerts and notify on critical activity

**Logic:**
1. Calls `GET /alerts?resolved=false&limit=200` on the backend
2. Aggregates counts by severity (critical / high / medium / low) and alert type
3. If any **critical** alerts are open:
   - Sends a summary Slack message listing totals by severity

**Use case:** Ensures critical threats don't go unnoticed even if real-time notifications were missed.

---

### Workflow 04 — Block IP Handler & Notification

**Trigger:** Webhook — `POST /webhook/block-ip` (called by the backend's `n8n.forward_block()`)  
**Purpose:** Receives block events from the backend and sends formatted notifications

**Logic:**
1. Receives the block payload from the backend
2. Formats a human-readable Slack message with IP, reason, and trigger source
3. If `SLACK_WEBHOOK_URL` is configured, sends the notification
4. Responds to the webhook with confirmation

**Note:** This workflow receives calls from the backend — it does not call the backend itself.

---

### Workflow 05 — Port Scan Detection

**Trigger:** Webhook — every `POST /events` forwarded from the backend  
**Purpose:** Detect reconnaissance port scanning activity

**Logic:**
1. Filters for `event_type=port_scan` events only
2. Counts port scan events per IP in a 30-second window
3. If count **≥ 20 in 30 seconds**:
   - Calls `POST /alerts` to create a `high` severity alert
   - Calls `POST /block-ip` to block the IP immediately
   - Sends a Slack warning notification

**Thresholds:**
- Window: 30 seconds
- Trigger: 20 port scan events

---

### Workflow 06 — Credential Stuffing Detection

**Trigger:** Webhook — every `POST /events` forwarded from the backend  
**Purpose:** Detect automated credential stuffing attacks targeting multiple accounts

**Logic:**
1. Filters for `event_type=login_attempt` AND `status=failed`
2. Tracks failures per IP — counting both total failures **and** distinct `user_id` values in a 5-minute window
3. If **≥ 10 failures** across **≥ 5 distinct accounts** in 5 minutes:
   - Calls `POST /alerts` to create a `critical` severity alert
   - Calls `POST /block-ip` to block the IP
   - Sends a critical Slack notification

**Why two thresholds?** Brute-force against one account is workflow 01. Credential stuffing is characterised by trying many accounts — requiring both high failure count _and_ high account diversity prevents false positives.

**Thresholds:**
- Window: 5 minutes (300 seconds)
- Trigger: ≥ 10 failures AND ≥ 5 distinct user_ids

---

## 9. Verify End-to-End Automation

### 9.1 Seed with test events (recommended)

The seed script sends a batch of pre-defined events that will trigger workflows:

```bash
python scripts/seed_events.py \
  --url http://localhost:8000 \
  --key YOUR_API_KEY
```

Output:
```
✓ [202] login_attempt from 10.0.0.5
✓ [202] login_attempt from 10.0.0.5
...
Done. Check n8n for triggered workflows.
```

### 9.2 Send events manually with curl

Replace `YOUR_API_KEY` with the value from your `.env`.

**Trigger brute-force detection (workflow 01)** — send 6 failed logins from the same IP:

```bash
for i in {1..6}; do
  curl -s -X POST http://localhost:8000/events \
    -H "X-API-Key: YOUR_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"event_type":"login_attempt","source_ip":"198.51.100.1","status":"failed","user_id":"alice"}' \
    | jq .
done
```

**Trigger port scan detection (workflow 05):**

```bash
for i in {1..25}; do
  curl -s -X POST http://localhost:8000/events \
    -H "X-API-Key: YOUR_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"event_type":"port_scan","source_ip":"198.51.100.2","status":"blocked"}' \
    | jq .
done
```

**Trigger credential stuffing (workflow 06)** — failures across multiple user accounts:

```bash
for user in alice bob charlie dave eve frank george henry iris james; do
  curl -s -X POST http://localhost:8000/events \
    -H "X-API-Key: YOUR_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"event_type\":\"login_attempt\",\"source_ip\":\"198.51.100.3\",\"status\":\"failed\",\"user_id\":\"$user\"}" \
    | jq .
done
```

### 9.3 Check results

**View blocked IPs:**
```bash
curl -s http://localhost:8000/block-ip \
  -H "X-API-Key: YOUR_API_KEY" | jq .
```

**View generated alerts:**
```bash
curl -s "http://localhost:8000/alerts?resolved=false" \
  -H "X-API-Key: YOUR_API_KEY" | jq .
```

**View platform stats:**
```bash
curl -s http://localhost:8000/stats \
  -H "X-API-Key: YOUR_API_KEY" | jq .
```

**Check n8n workflow execution history:**
1. Open http://localhost:5678
2. Click on a workflow → **Executions** tab
3. You should see successful runs timestamped around when you sent events

---

## 10. API Quick Reference

All endpoints (except `/health`) require the `X-API-Key` header.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | None | Liveness + readiness check |
| `POST` | `/events` | Operator | Ingest a security event |
| `GET` | `/events` | Analyst | List recent events |
| `POST` | `/alerts` | Operator | Create an alert manually |
| `GET` | `/alerts` | Analyst | List alerts (filter by `?resolved=true/false`) |
| `PATCH` | `/alerts/{id}/resolve` | Operator | Resolve an alert |
| `GET` | `/alerts/{id}/triage` | Analyst | AI-assisted triage report (requires `ANTHROPIC_API_KEY`) |
| `POST` | `/block-ip` | Operator | Block an IP address |
| `GET` | `/block-ip` | Analyst | List blocked IPs |
| `DELETE` | `/block-ip/{ip}` | Operator | Unblock an IP |
| `GET` | `/stats` | Analyst | Aggregated platform stats |
| `POST` | `/replay` | Operator | Re-run detection over a historical time window |
| `POST` | `/webhooks` | Operator | Register an outbound webhook |
| `GET` | `/webhooks` | Analyst | List registered webhooks |
| `DELETE` | `/webhooks/{id}` | Operator | Delete a webhook |
| `PATCH` | `/webhooks/{id}` | Operator | Enable / disable a webhook |

**Minimal event payload:**
```json
{
  "event_type": "login_attempt",
  "source_ip": "203.0.113.1",
  "status": "failed",
  "user_id": "alice"
}
```

**Supported `status` values:** `success`, `failed`, `blocked`, `unknown`

**Supported `event_type` patterns** (detection engine watches these specifically):
- `login_attempt` — brute force, credential stuffing
- `port_scan` — port scan detection
- `api_call` — API abuse detection
- `data_export` — data exfiltration detection
- Any other string is accepted and stored but won't trigger detection rules

---

## 11. Dashboard

The React dashboard provides a live view of platform activity.

### Running locally (dev mode)

```bash
cd frontend
npm install     # first time only
npm run dev
```

Open **http://localhost:5173** — the dashboard polls `GET /stats` and `GET /alerts` every 30 seconds.

### What's on the dashboard

| Panel | Data source |
|-------|------------|
| Stat cards (events, alerts, blocked IPs) | `GET /stats` |
| Alerts by severity (pie chart) | `GET /stats` |
| Open alerts by type (bar chart) | `GET /stats` |
| Event types in last 24h (bar chart) | `GET /stats` |
| Recent alerts table | `GET /alerts?limit=20` |
| Top source countries | `GET /stats` (geo-enriched events) |
| Recently blocked IPs | `GET /stats` |

> **Geo data note:** Country information appears only for events where the source IP was successfully geo-enriched via ip-api.com. Private IPs (10.x, 192.168.x, etc.) are skipped automatically.

---

## 12. Troubleshooting

### Backend fails to start

```bash
docker compose logs backend
```

Common causes:
- `MONGO_PASSWORD` not set in `.env` → set it and re-run `docker compose up -d`
- MongoDB not healthy yet → wait 30s and retry; MongoDB takes longer than Redis to initialise

### n8n workflows not triggering

1. Confirm all 6 workflows are **active** (green toggle in n8n UI)
2. Confirm the backend is forwarding events — check `docker compose logs backend` for lines like `forwarding event to n8n`
3. In n8n, open the workflow → **Executions** tab → check for failed runs with error details
4. Confirm `AUTOSEC_BACKEND_URL` resolves — from inside the n8n container, `http://backend:8000` must be reachable (the Docker network handles this automatically)

### IP not being blocked after sending events

- The in-memory sliding window counters in workflows 01, 02, 05, 06 **reset when n8n restarts** — if you restarted n8n between test runs, the counters are zero again
- The backend's inline detection engine (separate from n8n) maintains its own counters per process — also resets on restart
- Wait and re-send the events within the threshold window without restarting services

### `jq` not available

Replace `| jq .` with `| python -m json.tool` or remove it to see raw JSON.

### Redis shows as `unreachable` in `/health`

The backend falls back to in-memory rate limiting automatically — this is a degraded but functional state. Check `docker compose logs redis` for startup errors.

### Re-importing workflows after changes

The import script is idempotent — running it again updates existing workflows:

```bash
N8N_PASSWORD=your-n8n-password python scripts/import_n8n_workflows.py
```

### Full reset (wipe all data)

```bash
docker compose down -v   # removes all volumes (MongoDB data, n8n data, Redis data)
docker compose up -d
```

> This deletes all events, alerts, and blocked IPs. Re-import workflows after.
