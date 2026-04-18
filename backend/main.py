"""
AutoSecOps — FastAPI entry point.

Start (dev):
    uvicorn backend.main:app --reload --port 8000

Environment variables required:
    MONGO_URI        — e.g. mongodb://mongo:27017
    JWT_SECRET       — secret key for signing JWTs (use a long random string in production)
    AUTOSEC_USERS    — JSON array of users, e.g.:
                       '[{"username":"admin","password_hash":"<bcrypt>","role":"operator"}]'

Optional:
    JWT_EXPIRE_MINUTES — token lifetime in minutes (default: 60)
    N8N_WEBHOOK_BASE   — e.g. http://n8n:5678/webhook
    REDIS_URL          — e.g. redis://redis:6379/0  (enables Redis-backed rate limiter)
    CORS_ORIGINS       — comma-separated allowed origins, e.g. https://app.example.com
                         defaults to * when unset (dev only — always set in production)
"""
import asyncio
import logging
import logging.config
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.middleware.auth import APIKeyMiddleware
from backend.middleware.rate_limit import RateLimitMiddleware, cleanup_stale_ips, init_redis, close_redis
from backend.middleware.request_logger import RequestLoggerMiddleware, RequestIdFilter
from backend.routes import events, alerts, auth, block_ip, health, stats, replay, webhooks
from backend.services.mongo import init_indexes, close_client


# ── Logging ───────────────────────────────────────────────────────────────────

logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(request_id)s %(message)s",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        }
    },
    "root": {"level": "INFO", "handlers": ["console"]},
})

# Inject request_id into every log record via a filter on the root handler
_request_id_filter = RequestIdFilter()
for _handler in logging.root.handlers:
    _handler.addFilter(_request_id_filter)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_indexes()
    await init_redis()
    cleanup_task = asyncio.create_task(cleanup_stale_ips())
    yield
    cleanup_task.cancel()
    await close_redis()
    await close_client()


# ── CORS origins ──────────────────────────────────────────────────────────────

_cors_env = os.environ.get("CORS_ORIGINS", "").strip()
_cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()] if _cors_env else ["*"]


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AutoSecOps API",
    description="Intelligent Security Automation Platform — event ingestion, alerting, and IP blocking.",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Order matters: logger → rate limiter → API key auth → CORS
app.add_middleware(RequestLoggerMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(APIKeyMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(events.router)
app.include_router(alerts.router)
app.include_router(block_ip.router)
app.include_router(stats.router)
app.include_router(replay.router)
app.include_router(webhooks.router)
