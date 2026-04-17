"""
JWT authentication service.

Users are loaded from the AUTOSEC_USERS environment variable — a JSON array
of objects with fields: username, password_hash (bcrypt), role.

Example:
    AUTOSEC_USERS='[{"username":"admin","password_hash":"$2b$12$...","role":"operator"}]'

Roles:
    operator  — full read/write access
    analyst   — read-only access (GET routes)

Generating a password hash (run once, store the output in AUTOSEC_USERS):
    python -c "from backend.services.auth import hash_password; print(hash_password('mypassword'))"
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any

from jose import jwt, JWTError  # noqa: F401 — re-exported for callers
from passlib.context import CryptContext

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
_DEFAULT_EXPIRE_MINUTES = 60


def _secret() -> str:
    return os.environ.get("JWT_SECRET", "change-me-in-production-please")


def _expire_minutes() -> int:
    return int(os.environ.get("JWT_EXPIRE_MINUTES", str(_DEFAULT_EXPIRE_MINUTES)))


_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── User store ────────────────────────────────────────────────────────────────

def _load_users() -> list[dict]:
    raw = os.environ.get("AUTOSEC_USERS", "").strip()
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("AUTOSEC_USERS is not valid JSON — no JWT users configured")
        return []


def get_user(username: str) -> dict | None:
    for user in _load_users():
        if user.get("username") == username:
            return user
    return None


# ── Password helpers ──────────────────────────────────────────────────────────

def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    """Utility — call this once to generate the hash to store in AUTOSEC_USERS."""
    return _pwd_context.hash(plain)


def authenticate_user(username: str, password: str) -> dict | None:
    """Return the user dict if credentials are valid, else None."""
    user = get_user(username)
    if not user:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return user


# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=_expire_minutes())
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, _secret(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """
    Decode and verify a JWT.
    Raises jose.JWTError on invalid / expired token.
    """
    return jwt.decode(token, _secret(), algorithms=[ALGORITHM])
