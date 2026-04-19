"""
FastAPI dependency functions for JWT-based role guards.

Two auth paths are supported:
  - X-API-Key header      → validated by APIKeyMiddleware; treated as operator
  - Authorization: Bearer → JWT issued by POST /auth/token; role from token payload

Usage in routes:
    from backend.dependencies import require_operator, require_any_role

    @router.post("", dependencies=[Depends(require_operator)])
    async def create_thing(): ...

    @router.get("", dependencies=[Depends(require_any_role)])
    async def list_things(): ...
"""
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.services import auth as auth_svc
from jose import JWTError

_bearer_scheme = HTTPBearer(auto_error=False)


def _decode_bearer(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict | None:
    """
    Decode Bearer JWT if present.  Returns None when no Bearer header exists
    (allows the API-key path to take over).  Raises 401 on malformed/expired tokens.
    """
    if credentials is None:
        return None
    try:
        return auth_svc.decode_token(credentials.credentials)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_operator(
    request: Request,
    token_payload: dict | None = Depends(_decode_bearer),
) -> dict:
    """
    Allow access only to operator-role JWT users or API-key service accounts.
    Raises 403 for analyst-role JWT users.
    """
    if token_payload is not None:
        if token_payload.get("role") != "operator":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operator role required",
            )
        return token_payload

    # Fall through to API-key path — middleware already validated the key
    if request.headers.get("X-API-Key"):
        return {"role": "operator", "sub": "service-account"}

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_any_role(
    request: Request,
    token_payload: dict | None = Depends(_decode_bearer),
) -> dict:
    """
    Allow access to any authenticated user (operator or analyst JWT, or API-key).
    """
    if token_payload is not None:
        return token_payload

    if request.headers.get("X-API-Key"):
        return {"role": "operator", "sub": "service-account"}

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )
