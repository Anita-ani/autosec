# AutoSecOps — Intelligent Security Automation Platform

A production-grade DevSecOps platform that ingests security events, detects threats in real time, and automates responses through n8n workflows.

## Quick Start

### 1. Create your .env file

> **This step is required.** Docker Compose will refuse to start without it.

```bash
cp .env.example .env
```

Then open `.env` and set the three required secrets:

| Variable | Required | Description |
|----------|----------|-------------|
| `MONGO_PASSWORD` | **Yes** | MongoDB root password — choose something strong |
| `API_KEY` | **Yes** | Shared secret for `X-API-Key` header — use a random 32-char string |
| `N8N_PASSWORD` | **Yes** | n8n dashboard password |
| `SLACK_WEBHOOK_URL` | No | Incoming webhook URL for Slack alerts |
| `ALERT_EMAIL` | No | Email address for alert notifications |

Everything else in `.env.example` has safe defaults and does not need to change for local development.

### 2. Start all services

Run from the **project root** (where `docker-compose.yml` lives):

```bash
docker compose up -d
```

| Service | URL |
|---------|-----|
| FastAPI backend | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |
| n8n dashboard | http://localhost:5678 |

### 3. Import n8n workflows

With the stack running, import all 6 workflows in one step:

```bash
N8N_PASSWORD=your_n8n_password python scripts/import_n8n_workflows.py
```

Or log into the n8n dashboard → **Settings → Import workflow** → upload each file from `n8n/workflows/` manually.

### 4. Send a test event

```bash
curl -X POST http://localhost:8000/events \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"event_type":"login_attempt","source_ip":"10.0.0.5","status":"failed","user_id":"alice"}'
```

### 5. Seed bulk test data

```bash
python scripts/seed_events.py --url http://localhost:8000 --key YOUR_API_KEY
```

---

## Project Structure

```
autosecops/
├── backend/
│   ├── main.py               # FastAPI app entry point
│   ├── Dockerfile            # Build context is project root: docker build -f backend/Dockerfile .
│   ├── requirements.txt
│   ├── models/schemas.py     # Pydantic input/output schemas
│   ├── middleware/           # auth, rate limiting, request logging
│   ├── routes/               # events, alerts, block-ip, health, stats
│   └── services/             # mongo client, n8n forwarder, detection engine
├── n8n/workflows/            # Workflow JSON files (01–06)
├── docker-compose.yml        # Run from project root: docker compose up -d
├── tests/                    # pytest suite (no infra required)
├── scripts/
│   ├── seed_events.py        # Bulk test data generator
│   ├── import_n8n_workflows.py  # Auto-import workflows into n8n
│   └── check_health.sh       # Service health check
└── docs/                     # architecture.md, api.md, workflows.md
```

> **Docker note:** `docker-compose.yml` lives at the project root. The `backend/Dockerfile` uses build context `.` (project root) so it can copy `backend/` correctly. Always run `docker compose` from the project root — not from inside `docker/`.

---

## Running Tests

```bash
pip install -r backend/requirements.txt -r tests/requirements-test.txt
pytest
```

---

## Phase Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| 1 — MVP | **Done** | FastAPI + MongoDB + n8n + Docker |
| 2 — Automation | **Done** | Detection engine (5 rules), POST /alerts, GET /stats, n8n workflows 05–06 |
| 3 — DevSecOps | **Done** | Redis rate limiting, structured JSON logging + request-ID, CORS lockdown, alert dedup, Docker hardening |
| 4 — Deployment | **Done** | ECS/Fargate Terraform, GitHub Actions CI/CD (lint→test→build→ECR→ECS), Secrets Manager, CloudWatch alarms |
| 5 — Advanced | Next | Replay engine, analytics dashboard, AI-assisted triage, geo-enrichment, RBAC |
