#!/usr/bin/env bash
# Quick health + connectivity check for all services
set -euo pipefail

BASE="${1:-http://localhost:8000}"
KEY="${2:-}"

echo "=== AutoSecOps Health Check ==="
echo ""

echo "→ Backend:"
curl -sf "$BASE/health" | python3 -m json.tool || echo "  UNREACHABLE"

echo ""
echo "→ n8n:"
N8N_PORT="${N8N_PORT:-5678}"
curl -sf "http://localhost:${N8N_PORT}/healthz" && echo " OK" || echo "  UNREACHABLE"

echo ""
echo "→ Events list (requires API key):"
if [ -n "$KEY" ]; then
  curl -sf -H "X-API-Key: $KEY" "$BASE/events?limit=5" | python3 -m json.tool
else
  echo "  Skipped — pass API key as second arg: $0 <base_url> <api_key>"
fi
