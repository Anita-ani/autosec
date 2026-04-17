# n8n Workflow Reference

Import the JSON files from `n8n/workflows/` into your n8n instance via:
**Settings → Import workflow → Upload file**

---

## 01 — Failed Login Detection

**Trigger:** Webhook `POST /webhook/ingest-event`

**Logic:**
- Filters for `event_type=login_attempt` AND `status=failed`
- Uses workflow static data to count failures per IP in a 60-second sliding window
- If count ≥ 5: calls `POST /block-ip` on the backend, sends Slack alert

**Env vars used:** `AUTOSEC_BACKEND_URL`, `AUTOSEC_API_KEY`, `SLACK_WEBHOOK_URL`

---

## 02 — Suspicious IP Detection

**Trigger:** Same webhook `POST /webhook/ingest-event` (runs in parallel with Workflow 01)

**Logic:**
- Counts ALL event types per IP in a 5-minute window
- If count ≥ 20: blocks the IP as high-frequency/suspicious

**Env vars used:** `AUTOSEC_BACKEND_URL`, `AUTOSEC_API_KEY`

---

## 03 — Alert Aggregation

**Trigger:** Schedule — every 5 minutes

**Logic:**
- Fetches all unresolved alerts from `GET /alerts?resolved=false`
- Aggregates by severity and type
- Sends a Slack summary if any critical alerts exist

**Env vars used:** `AUTOSEC_BACKEND_URL`, `AUTOSEC_API_KEY`, `SLACK_WEBHOOK_URL`

---

## 04 — Block IP Handler & Notification

**Trigger:** Webhook `POST /webhook/block-ip`

**Logic:**
- Receives block events forwarded by the FastAPI backend
- Formats a human-readable Slack message
- Sends notification if `SLACK_WEBHOOK_URL` is set
- Responds to the webhook with confirmation

**Env vars used:** `SLACK_WEBHOOK_URL`

---

## Setting n8n Environment Variables

In docker-compose, these are injected automatically from your `.env` file.
When running n8n standalone, set them under **Settings → Variables**.
