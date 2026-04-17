"""
Structured JSON request logger with request-ID correlation.

Every inbound request gets a UUID assigned as X-Request-ID (or the value
passed in by the caller is echoed back). The ID is stored in a ContextVar
so it automatically appears on every log line emitted during that request,
including lines from routes and services.
"""
import json
import logging
import time
import uuid
from contextvars import ContextVar

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("autosecops.access")

# Shared ContextVar — populated per-request so every log line includes the ID
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    """Injects the active request_id into every log record."""
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get("-")
        return True


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Honour caller-supplied ID; generate one if absent
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_var.set(req_id)

        start = time.monotonic()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)

        duration_ms = round((time.monotonic() - start) * 1000, 2)
        response.headers["X-Request-ID"] = req_id

        logger.info(json.dumps({
            "request_id": req_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "client_ip": _client_ip(request),
            "user_agent": request.headers.get("User-Agent", ""),
        }))
        return response
