"""Authentication endpoints: login, logout, and auth status."""

import httpx
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from starlette.requests import Request
from ..limiter import limiter
from ..auth import (
    _is_auth_enabled,
    _get_paperless_url,
    _verify_token_against_paperless,
    _bearer_scheme,
    _token_cache,
    require_auth,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str
    code: Optional[str] = None


@router.get("/status")
async def auth_status():
    """Return whether authentication is enabled."""
    return {"auth_enabled": _is_auth_enabled()}


@router.post("/login")
@limiter.limit("5/minute")
async def login(request: Request, body: LoginRequest):
    """Authenticate with Paperless and return a bearer token."""
    paperless_url = await _get_paperless_url()
    if not paperless_url:
        raise HTTPException(status_code=503, detail="Paperless not configured")
    try:
        payload: dict = {"username": body.username, "password": body.password}
        if body.code:
            payload["code"] = body.code
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{paperless_url}/api/token/",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
        if response.status_code == 400:
            try:
                errors = response.json().get("non_field_errors", [])
            except Exception:
                errors = []
            if any("MFA" in e or "mfa" in e.lower() for e in errors):
                raise HTTPException(status_code=400, detail="mfa_required")
            raise HTTPException(status_code=401, detail="Invalid username or password")
        if response.status_code in (401, 403):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        response.raise_for_status()
        data = response.json()
        token = data.get("token")
        if not token:
            raise HTTPException(
                status_code=500, detail="No token in Paperless response"
            )
        return {"token": token, "username": body.username}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Login error: {exc}")
        raise HTTPException(status_code=503, detail="Could not reach Paperless")


@router.get("/me")
async def me(user: dict = Depends(require_auth)):
    return user


@router.post("/logout")
async def logout(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
):
    """Invalidate the current bearer token from the cache."""
    if credentials and credentials.scheme.lower() == "bearer":
        _token_cache.pop(credentials.credentials, None)
    return {"success": True}
