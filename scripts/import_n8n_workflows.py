#!/usr/bin/env python3
"""
Import and activate all AutoSecOps n8n workflows via the n8n REST API.

Usage:
    python scripts/import_n8n_workflows.py

Environment variables (or pass as args):
    N8N_URL      — n8n base URL, default http://localhost:5678
    N8N_USER     — basic auth username, default admin
    N8N_PASSWORD — basic auth password (required)

The script is idempotent: if a workflow with the same name already exists
it is updated in-place rather than duplicated.
"""
import json
import os
import sys
from pathlib import Path

try:
    import httpx
except ImportError:
    print("ERROR: httpx is not installed. Run: pip install httpx")
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────

N8N_URL = os.environ.get("N8N_URL", "http://localhost:5678").rstrip("/")
N8N_USER = os.environ.get("N8N_USER", "admin")
N8N_PASSWORD = os.environ.get("N8N_PASSWORD", "")

WORKFLOWS_DIR = Path(__file__).parent.parent / "n8n" / "workflows"


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_client() -> httpx.Client:
    if not N8N_PASSWORD:
        print("ERROR: N8N_PASSWORD environment variable is required.")
        sys.exit(1)
    return httpx.Client(
        base_url=N8N_URL,
        auth=(N8N_USER, N8N_PASSWORD),
        headers={"Content-Type": "application/json"},
        timeout=15.0,
    )


def get_existing_workflows(client: httpx.Client) -> dict[str, str]:
    """Return {workflow_name: workflow_id} for all existing workflows."""
    resp = client.get("/api/v1/workflows")
    resp.raise_for_status()
    return {wf["name"]: wf["id"] for wf in resp.json().get("data", [])}


def import_workflow(client: httpx.Client, workflow: dict, existing: dict[str, str]) -> str:
    """Create or update a workflow. Returns the workflow ID."""
    name = workflow.get("name", "unnamed")

    # Strip the 'id' field — n8n assigns its own IDs on create
    payload = {k: v for k, v in workflow.items() if k != "id"}

    if name in existing:
        wf_id = existing[name]
        resp = client.put(f"/api/v1/workflows/{wf_id}", content=json.dumps(payload))
        resp.raise_for_status()
        print(f"  Updated : {name} (id={wf_id})")
        return wf_id
    else:
        resp = client.post("/api/v1/workflows", content=json.dumps(payload))
        resp.raise_for_status()
        wf_id = resp.json()["id"]
        print(f"  Created : {name} (id={wf_id})")
        return wf_id


def activate_workflow(client: httpx.Client, wf_id: str, name: str) -> None:
    resp = client.patch(f"/api/v1/workflows/{wf_id}/activate")
    if resp.status_code == 200:
        print(f"  Activated: {name}")
    else:
        print(f"  WARNING: Could not activate {name} — {resp.status_code}: {resp.text}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    workflow_files = sorted(WORKFLOWS_DIR.glob("*.json"))
    if not workflow_files:
        print(f"No workflow files found in {WORKFLOWS_DIR}")
        sys.exit(1)

    print(f"Connecting to n8n at {N8N_URL} as '{N8N_USER}'...")
    with get_client() as client:
        # Verify connection
        try:
            client.get("/api/v1/workflows").raise_for_status()
        except Exception as exc:
            print(f"ERROR: Cannot reach n8n — {exc}")
            print("Make sure n8n is running and N8N_PASSWORD is correct.")
            sys.exit(1)

        existing = get_existing_workflows(client)
        print(f"Found {len(existing)} existing workflow(s) in n8n.\n")

        imported = []
        errors = []

        for path in workflow_files:
            print(f"Processing {path.name}...")
            try:
                workflow = json.loads(path.read_text(encoding="utf-8"))
                wf_id = import_workflow(client, workflow, existing)
                activate_workflow(client, wf_id, workflow.get("name", path.name))
                imported.append(path.name)
            except Exception as exc:
                print(f"  ERROR: {exc}")
                errors.append(path.name)
            print()

    print("─" * 50)
    print(f"Done. {len(imported)} imported/updated, {len(errors)} failed.")
    if errors:
        print(f"Failed: {', '.join(errors)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
