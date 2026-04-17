"""
Authentication — issue JWT access tokens.

POST /auth/token
  Body:    { "username": "...", "password": "..." }
  Returns: { "access_token": "...", "token_type": "bearer", "role": "operator|analyst" }

This endpoint is public — no Authorization header required.
"""
import logging
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from backend.services import auth as auth_svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])


class TokenRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


@router.post("/token", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def login(body: TokenRequest):
    """
    Exchange username + password for a JWT access token.

    Include the returned token in subsequent requests as:
        Authorization: Bearer <access_token>
    """
    user = auth_svc.authenticate_user(body.username, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_svc.create_access_token(
        {"sub": user["username"], "role": user["role"]}
    )
    logger.info("Token issued: username=%s role=%s", user["username"], user["role"])
    return TokenResponse(access_token=token, token_type="bearer", role=user["role"])
