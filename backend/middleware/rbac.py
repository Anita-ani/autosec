"""
RBAC dependency injection for FastAPI routes.

Usage:
    from fastapi import Depends
    from backend.middleware.rbac import require_analyst, require_operator

    @router.get("/data")
    async def read_data(user: dict = Depends(require_analyst)):
        ...

    @router.post("/data")
    async def write_data(user: dict = Depends(require_operator)):
        ...

Roles:
    analyst   — read-only (GET routes)
    operator  — full access (all routes)

Authentication: Authorization: Bearer <JWT>
"""
from __future__ import annotations

import logging

from fastapi import Request, HTTPException, status
from jose import JWTError

from backend.services import auth as auth_svc

logger = logging.getLogger(__name__)

_BEARER_PREFIX = "Bearer "


def _extract_user(request: Request) -> dict:
    """
    Extract and verify the Bearer JWT from the Authorization header.
    Returns {"username": ..., "role": ...} on success.
    Raises HTTPException 401 on missing/invalid token.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith(_BEARER_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing or not Bearer",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header[len(_BEARER_PREFIX):]
    try:
        payload = auth_svc.decode_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = payload.get("sub", "")
    role = payload.get("role", "")
    if not username or not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload missing sub or role",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {"username": username, "role": role}


def require_analyst(request: Request) -> dict:
    """Allow analyst or operator role."""
    user = _extract_user(request)
    if user["role"] not in ("analyst", "operator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return user


def require_operator(request: Request) -> dict:
    """Allow operator role only."""
    user = _extract_user(request)
    if user["role"] != "operator":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator role required",
        )
    return user
