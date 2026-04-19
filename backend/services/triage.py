"""
AI-assisted alert triage — generates a human-readable summary and remediation
steps for an alert by sending context to Gemini.

Requires:
    GEMINI_API_KEY environment variable
    openai Python package (already in most requirements.txt; used for the
    OpenAI-compatible Gemini endpoint)

The triage call is intentionally async — the openai async client is used so
we don't block the event loop.

Context sent to the model:
  - The alert document (type, severity, source IP, message, timestamps)
  - Up to 20 related events from the same source IP in the last hour
  - Current open alert count for this IP

Response shape:
    {
        "alert_id": str,
        "summary": str,          # 2-3 sentence narrative
        "severity_assessment": str,
        "remediation_steps": [str, ...],
        "related_events_count": int,
        "model": str,
    }
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger(__name__)

_MODEL = "gemini-2.0-flash"
_MAX_EVENTS = 20
_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


async def run(alert: dict, db) -> dict[str, Any]:
    """
    Generate a triage report for the given alert dict.
    Raises RuntimeError if GEMINI_API_KEY is not set.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    source_ip = alert.get("source_ip", "unknown")
    since = datetime.now(timezone.utc) - timedelta(hours=1)

    # Gather context from MongoDB
    related_cursor = db.events.find(
        {"source_ip": source_ip, "timestamp": {"$gte": since}},
        {"_id": 0, "event_type": 1, "status": 1, "timestamp": 1},
    ).sort("timestamp", -1).limit(_MAX_EVENTS)

    related_events: list[dict] = []
    async for doc in related_cursor:
        if isinstance(doc.get("timestamp"), datetime):
            doc["timestamp"] = doc["timestamp"].isoformat()
        related_events.append(doc)

    open_count = await db.alerts.count_documents(
        {"source_ip": source_ip, "resolved": False}
    )

    prompt = _build_prompt(alert, related_events, open_count)

    from openai import AsyncOpenAI
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=_GEMINI_BASE_URL,
    )

    response = await client.chat.completions.create(
        model=_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.choices[0].message.content
    parsed = _parse_response(raw)

    return {
        "alert_id": str(alert.get("_id", alert.get("id", ""))),
        "related_events_count": len(related_events),
        "model": _MODEL,
        **parsed,
    }


def _build_prompt(alert: dict, related_events: list[dict], open_count: int) -> str:
    created_at = alert.get("created_at")
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()

    return f"""You are a security analyst assistant. Analyse the following security alert and provide a concise triage report.

## Alert
- Type: {alert.get("alert_type")}
- Severity: {alert.get("severity")}
- Source IP: {alert.get("source_ip")}
- Message: {alert.get("message")}
- Detected at: {created_at}
- Rule: {alert.get("rule", "n/a")}

## Context
- Open alerts for this IP: {open_count}
- Related events in last 1h (most recent first, up to {_MAX_EVENTS}):
{_format_events(related_events)}

## Instructions
Respond with EXACTLY this structure (no markdown headers, plain text sections separated by the labels below):

SUMMARY:
<2-3 sentence narrative explaining what is happening, who is affected, and why it matters>

SEVERITY_ASSESSMENT:
<One sentence assessing whether the severity is appropriate given the context>

REMEDIATION_STEPS:
1. <First step>
2. <Second step>
3. <Third step>
(add more steps if needed, numbered list only)
"""


def _format_events(events: list[dict]) -> str:
    if not events:
        return "  (none)"
    lines = []
    for e in events:
        lines.append(f"  - {e.get('timestamp', 'n/a')} | {e.get('event_type')} | {e.get('status')}")
    return "\n".join(lines)


def _parse_response(text: str) -> dict[str, Any]:
    """
    Parse the structured response from Gemini into a dict.
    Falls back gracefully if the format doesn't match.
    """
    summary = ""
    severity_assessment = ""
    remediation_steps: list[str] = []

    section = None
    step_lines: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("SUMMARY:"):
            section = "summary"
            rest = stripped[len("SUMMARY:"):].strip()
            if rest:
                summary += rest + " "
        elif stripped.startswith("SEVERITY_ASSESSMENT:"):
            section = "severity"
            rest = stripped[len("SEVERITY_ASSESSMENT:"):].strip()
            if rest:
                severity_assessment += rest + " "
        elif stripped.startswith("REMEDIATION_STEPS:"):
            section = "remediation"
        elif section == "summary" and stripped:
            summary += stripped + " "
        elif section == "severity" and stripped:
            severity_assessment += stripped + " "
        elif section == "remediation" and stripped:
            import re
            cleaned = re.sub(r"^\d+\.\s*", "", stripped)
            if cleaned:
                step_lines.append(cleaned)

    remediation_steps = step_lines

    # Fallback: if parsing failed entirely, return the raw text as summary
    if not summary and not remediation_steps:
        summary = text.strip()

    return {
        "summary": summary.strip(),
        "severity_assessment": severity_assessment.strip(),
        "remediation_steps": remediation_steps,
    }