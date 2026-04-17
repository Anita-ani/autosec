from fastapi import APIRouter
from datetime import datetime, timezone

import backend.services.mongo as _mongo
import backend.middleware.rate_limit as rl_module

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health():
    """
    Liveness + readiness probe.

    Checks MongoDB and Redis (if configured). Used by ECS, docker-compose
    healthchecks, and the check_health.sh script.

    Status values:
      ok       — all configured services reachable
      degraded — one or more services unreachable
    """
    # ── MongoDB ───────────────────────────────────────────────────────────────
    mongo_ok = False
    try:
        await _mongo.get_client().admin.command("ping")
        mongo_ok = True
    except Exception:
        pass

    # ── Redis ────────────────────────────────────────────────────────────────
    redis_client = rl_module._redis_client
    if redis_client is None:
        # REDIS_URL not configured — in-memory fallback is active
        redis_status = "disabled"
        redis_ok = True  # not a failure — intentional config choice
    else:
        try:
            await redis_client.ping()
            redis_status = "connected"
            redis_ok = True
        except Exception:
            redis_status = "unreachable"
            redis_ok = False

    overall = "ok" if (mongo_ok and redis_ok) else "degraded"

    return {
        "status": overall,
        "mongo": "connected" if mongo_ok else "unreachable",
        "redis": redis_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
