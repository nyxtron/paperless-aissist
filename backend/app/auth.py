"""Authentication middleware and token verification.

Handles bearer token validation against Paperless, with an in-memory cache
to reduce load. Auth can be enabled/disabled via config or AUTH_ENABLED env var.
"""

import hashlib
import hmac
import os
import secrets
import time
import logging
import httpx
from typing import Optional
from fastapi import HTTPException, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .database import get_async_session, get_session
from .models import Config
from sqlmodel import select

logger = logging.getLogger(__name__)

_MAX_CACHE_SIZE = 1000
_CACHE_TTL_SECONDS = 30
AUTOMATION_API_TOKEN_HASH_KEY = "automation_api_token_hash"

_token_cache: dict[str, tuple[float, dict]] = {}

_bearer_scheme = HTTPBearer(auto_error=False)


def generate_automation_token() -> str:
    """Create a high-entropy token for external automation clients."""
    return f"paia_{secrets.token_urlsafe(32)}"


def hash_automation_token(token: str) -> str:
    """Hash an automation token before it is stored in config."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _is_auth_enabled() -> bool:
    """Check whether authentication is enabled.

    The setting in the web UI decides. AUTH_ENABLED=true is the one exception:
    it keeps auth switched on regardless, so an operator who enforces it cannot
    lose that protection through the UI. Any other value only acts as the
    default until the UI setting exists.
    """
    env_val = os.environ.get("AUTH_ENABLED")
    env_enabled = (
        env_val is not None and env_val.lower() not in ("false", "0", "no")
    )
    if env_enabled:
        return True
    with get_session() as session:
        stmt = select(Config).where(Config.key == "auth_enabled")
        cfg = session.exec(stmt).first()
        if cfg:
            return cfg.value.lower() not in ("false", "0", "no")
    return False


async def _get_paperless_url() -> str:
    """Retrieve the configured Paperless URL (async session version)."""
    async with get_async_session() as session:
        stmt = select(Config).where(Config.key == "paperless_url")
        cfg = await session.exec(stmt)
        cfg = cfg.first()
        if cfg and cfg.value:
            return cfg.value
    return os.environ.get("PAPERLESS_URL", "")


async def _get_automation_token_hash() -> str:
    """Retrieve the stored automation API token hash."""
    async with get_async_session() as session:
        stmt = select(Config).where(Config.key == AUTOMATION_API_TOKEN_HASH_KEY)
        cfg = await session.exec(stmt)
        cfg = cfg.first()
        if cfg and cfg.value:
            return cfg.value
    return ""


def _evict_stale_entries():
    """Remove token cache entries older than _CACHE_TTL_SECONDS."""
    now = time.time()
    stale = [
        k for k, (ts, _) in _token_cache.items() if (now - ts) > _CACHE_TTL_SECONDS
    ]
    for k in stale:
        del _token_cache[k]


async def _verify_token_against_paperless(token: str) -> dict:
    """Verify bearer token against Paperless API, with caching.

    Returns:
        A dict with token info on success.

    Raises:
        HTTPException: 401 if token invalid, 503 if Paperless unreachable.
    """
    now = time.time()
    cached = _token_cache.get(token)
    if cached and (now - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]

    paperless_url = await _get_paperless_url()
    if not paperless_url:
        if cached:
            logger.warning("Paperless URL not configured; serving stale auth cache")
            return cached[1]
        raise HTTPException(status_code=503, detail="Paperless not configured")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{paperless_url}/api/tags/?page_size=1",
                headers={"Authorization": f"Token {token}"},
            )
        if response.status_code in (401, 403):
            _token_cache.pop(token, None)
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        response.raise_for_status()
        user_info = {"token": token}

        _evict_stale_entries()
        if len(_token_cache) >= _MAX_CACHE_SIZE:
            oldest = min(_token_cache, key=lambda k: _token_cache[k][0])
            del _token_cache[oldest]
        _token_cache[token] = (now, user_info)
        return user_info
    except HTTPException:
        raise
    except (httpx.ConnectError, httpx.TimeoutException, Exception) as exc:
        if cached:
            logger.warning(f"Paperless unreachable ({exc}); serving stale auth cache")
            return cached[1]
        raise HTTPException(
            status_code=503,
            detail="Paperless is unreachable and no cached session exists",
        )


async def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> dict:
    """FastAPI dependency that enforces authentication.

    Returns:
        Empty dict if auth is disabled; otherwise the verified user info.
    """
    if not _is_auth_enabled():
        return {}
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authentication required")
    return await _verify_token_against_paperless(credentials.credentials)


async def require_auth_or_query(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    token: Optional[str] = Query(None, alias="token"),
) -> dict:
    """FastAPI dependency that enforces authentication via header or query param.

    Query-param tokens may appear in server logs and browser history.
    Use header-based auth (Bearer token) when possible.
    Query-param auth is intended as a fallback for clients that cannot
    send custom headers (e.g., native EventSource).
    """
    if not _is_auth_enabled():
        return {}
    auth_token = None
    if credentials and credentials.scheme.lower() == "bearer":
        auth_token = credentials.credentials
    elif token:
        auth_token = token
    if not auth_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    return await _verify_token_against_paperless(auth_token)


async def require_automation_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> dict:
    """Require the dedicated Paperless-AIssist automation API token.

    This is intentionally independent from UI auth and remains required even
    when the web UI login is disabled.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Automation API token required")

    stored_hash = await _get_automation_token_hash()
    if not stored_hash:
        raise HTTPException(status_code=401, detail="Automation API token not configured")

    provided_hash = hash_automation_token(credentials.credentials)
    if not hmac.compare_digest(provided_hash, stored_hash):
        raise HTTPException(status_code=401, detail="Invalid automation API token")

    return {"automation": True}
