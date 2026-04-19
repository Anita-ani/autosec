#!/usr/bin/env python3
"""
Simulate realistic security event traffic to populate the AutoSecOps dashboard.

Generates events that trigger all 5 detection rules:
  - BruteForce           (6+ failed logins from same IP)
  - PortScan             (port_scan events)
  - CredentialStuffing   (failed logins across many user accounts)
  - APIAbuse             (burst of api_call events)
  - DataExfiltration     (burst of data_access events)

Usage:
    python scripts/simulate_logs.py
    python scripts/simulate_logs.py --url http://localhost:8000 --key YOUR_KEY --rounds 3
"""
import argparse
import httpx
import time
import random

API_KEY  = "local-dev-api-key-autosec123"
BASE_URL = "http://localhost:8000"

# Real-ish public IPs spread across several countries
ATTACKER_IPS = [
    "185.220.101.34",   # DE  – Tor exit node
    "45.142.212.100",   # NL  – known scanner
    "194.165.16.77",    # RU
    "103.251.167.20",   # CN
    "41.223.57.14",     # NG
    "81.161.229.3",     # UA
    "5.188.86.172",     # RU
    "162.247.74.201",   # US  – Tor
]

INTERNAL_IPS = ["10.0.1.5", "10.0.2.8", "192.168.10.3"]

USERS = [f"user_{i:03d}" for i in range(1, 40)]
ADMINS = ["admin", "root", "administrator", "sa", "sysadmin"]


def post(client: httpx.Client, event: dict) -> str:
    try:
        r = client.post("/events", json=event, timeout=8)
        mark = "OK" if r.status_code == 202 else f"FAIL {r.status_code}"
        alerts = r.json().get("alerts_triggered", 0) if r.status_code == 202 else 0
        alert_str = f"  >> {alerts} alert(s)" if alerts else ""
        return f"  {mark}  {event['event_type']:<28} {event['source_ip']:<18}{alert_str}"
    except Exception as e:
        return f"  ✗  ERROR: {e}"


def section(title: str):
    print(f"\n{'-'*60}")
    print(f"  {title}")
    print(f"{'-'*60}")


def simulate(client: httpx.Client, delay: float):

    # ── 1. Brute-force attacks ─────────────────────────────────────────────────
    section("BruteForce — 8 failed logins from same IP")
    brute_ip = random.choice(ATTACKER_IPS)
    for _ in range(8):
        print(post(client, {
            "event_type": "login_attempt",
            "source_ip": brute_ip,
            "status": "failed",
            "user_id": "admin",
        }))
        time.sleep(delay)

    # ── 2. Credential stuffing ─────────────────────────────────────────────────
    section("CredentialStuffing — failed logins across 12 accounts")
    stuff_ip = random.choice([ip for ip in ATTACKER_IPS if ip != brute_ip])
    for user in random.sample(USERS + ADMINS, 12):
        print(post(client, {
            "event_type": "login_attempt",
            "source_ip": stuff_ip,
            "status": "failed",
            "user_id": user,
        }))
        time.sleep(delay)

    # ── 3. Port scan ───────────────────────────────────────────────────────────
    section("PortScan — rapid probe burst")
    scan_ip = random.choice(ATTACKER_IPS)
    for _ in range(6):
        print(post(client, {
            "event_type": "port_scan",
            "source_ip": scan_ip,
            "status": "unknown",
            "metadata": {"ports_probed": random.randint(50, 500)},
        }))
        time.sleep(delay)

    # ── 4. API abuse ───────────────────────────────────────────────────────────
    section("APIAbuse — burst of API calls")
    abuse_ip = random.choice(ATTACKER_IPS)
    for _ in range(10):
        print(post(client, {
            "event_type": "api_call",
            "source_ip": abuse_ip,
            "status": random.choice(["failed", "failed", "success"]),
            "metadata": {"endpoint": random.choice(["/api/users", "/api/transfer", "/api/keys"])},
        }))
        time.sleep(delay)

    # ── 5. Data exfiltration ───────────────────────────────────────────────────
    section("DataExfiltration — high-volume data access")
    exfil_ip = random.choice(ATTACKER_IPS)
    for _ in range(8):
        print(post(client, {
            "event_type": "data_access",
            "source_ip": exfil_ip,
            "status": "success",
            "metadata": {
                "bytes_transferred": random.randint(500_000, 5_000_000),
                "table": random.choice(["users", "transactions", "wallets", "api_keys"]),
            },
        }))
        time.sleep(delay)

    # ── 6. Normal background traffic ──────────────────────────────────────────
    section("Normal traffic — mixed legit events")
    for _ in range(12):
        ip = random.choice(INTERNAL_IPS + ATTACKER_IPS[:2])
        event_type = random.choice([
            "login_attempt", "login_attempt", "login_attempt",
            "file_access", "api_call", "data_access",
        ])
        status = random.choices(
            ["success", "failed", "blocked"],
            weights=[70, 20, 10],
        )[0]
        print(post(client, {
            "event_type": event_type,
            "source_ip": ip,
            "status": status,
            "user_id": random.choice(USERS) if event_type == "login_attempt" else None,
        }))
        time.sleep(delay)

    # ── 7. Manual block a known bad actor ─────────────────────────────────────
    section("Block IP — flagging top attacker")
    try:
        r = client.post("/block-ip", json={
            "ip": brute_ip,
            "reason": "Automated block: brute-force attack detected",
            "triggered_by": "simulate_logs",
        }, timeout=8)
        mark = "OK" if r.status_code == 201 else f"FAIL {r.status_code}"
        print(f"  {mark}  Blocked {brute_ip}")
    except Exception as e:
        print(f"  ✗  Block failed: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url",    default=BASE_URL)
    parser.add_argument("--key",    default=API_KEY)
    parser.add_argument("--rounds", type=int, default=1, help="Repeat full simulation N times")
    parser.add_argument("--delay",  type=float, default=0.15, help="Seconds between requests")
    args = parser.parse_args()

    headers = {"X-API-Key": args.key, "Content-Type": "application/json"}

    print(f"\nAutoSecOps -- Log Simulator")
    print(f"   Target : {args.url}")
    print(f"   Rounds : {args.rounds}")
    print(f"   Delay  : {args.delay}s per request")

    with httpx.Client(base_url=args.url, headers=headers) as client:
        # Quick health check
        try:
            h = client.get("/health", timeout=5)
            print(f"   Health : {h.json().get('status', '?')}\n")
        except Exception as e:
            print(f"   Health : UNREACHABLE ({e})\n")
            return

        for i in range(args.rounds):
            if args.rounds > 1:
                print(f"\n{'='*60}  Round {i+1}/{args.rounds}")
            simulate(client, args.delay)

    print(f"\nDone -- refresh the dashboard at http://localhost:5173\n")


if __name__ == "__main__":
    main()
