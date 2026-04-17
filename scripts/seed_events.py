#!/usr/bin/env python3
"""
Seed the API with test events to exercise n8n workflows.
Usage:
    python scripts/seed_events.py --url http://localhost:8000 --key YOUR_API_KEY
"""
import argparse
import httpx
import time
import random

EVENTS = [
    {"event_type": "login_attempt", "source_ip": "10.0.0.5", "status": "failed", "user_id": "alice"},
    {"event_type": "login_attempt", "source_ip": "10.0.0.5", "status": "failed", "user_id": "alice"},
    {"event_type": "login_attempt", "source_ip": "10.0.0.5", "status": "failed", "user_id": "alice"},
    {"event_type": "login_attempt", "source_ip": "10.0.0.5", "status": "failed", "user_id": "alice"},
    {"event_type": "login_attempt", "source_ip": "10.0.0.5", "status": "failed", "user_id": "alice"},
    {"event_type": "login_attempt", "source_ip": "10.0.0.5", "status": "failed", "user_id": "alice"},
    {"event_type": "login_attempt", "source_ip": "192.168.1.1", "status": "success", "user_id": "bob"},
    {"event_type": "file_access", "source_ip": "172.16.0.22", "status": "blocked"},
    {"event_type": "api_call", "source_ip": "203.0.113.55", "status": "failed"},
]


def main():
    parser = argparse.ArgumentParser(description="Seed AutoSecOps with test events")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--key", required=True, help="X-API-Key value")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds between requests")
    args = parser.parse_args()

    headers = {"X-API-Key": args.key}
    with httpx.Client(base_url=args.url, headers=headers, timeout=10) as client:
        for event in EVENTS:
            resp = client.post("/events", json=event)
            status = "✓" if resp.status_code == 202 else "✗"
            print(f"{status} [{resp.status_code}] {event['event_type']} from {event['source_ip']}")
            time.sleep(args.delay)

    print("\nDone. Check n8n for triggered workflows.")


if __name__ == "__main__":
    main()
