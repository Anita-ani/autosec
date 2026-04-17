"""
API key authentication middleware.
The API key is stored in the API_KEY environment variable.
Requests must include:  X-API-Key: <key>
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import os
import hmac

# Paths that do NOT require authentication
PUBLIC_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        api_key = request.headers.get("X-API-Key", "")
        expected = os.environ.get("API_KEY", "")

        if not expected:
            # Fail closed: if no key configured, deny everything
            return JSONResponse(
                status_code=500,
                content={"detail": "API key not configured on server"},
            )

        # Constant-time comparison to prevent timing attacks
        if not hmac.compare_digest(api_key.encode(), expected.encode()):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key"},
                headers={"WWW-Authenticate": "ApiKey"},
            )

        return await call_next(request)
