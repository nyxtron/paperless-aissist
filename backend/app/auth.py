"""Authentication middleware and token verification.

Handles bearer token validation against Paperless, with an in-memory cache
to reduce load. Auth can be enabled/disabled via config or AUTH_ENABLED env var.
"""

import os
import time
import logging
import httpx
from typing import Optional
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .database import get_async_session, get_session
from .models import Config
from sqlmodel import select

logger = logging.getLogger(__name__)

_MAX_CACHE_SIZE = 1000
_CACHE_TTL_SECONDS = 30

_token_cache: dict[str, tuple[float, dict]] = {}

_bearer_scheme = HTTPBearer(auto_error=False)


def _is_auth_enabled() -> bool:
    """Check whether authentication is enabled (env var or config flag)."""
    env_val = os.environ.get("AUTH_ENABLED")
    if env_val is not None:
        return env_val.lower() not in ("false", "0", "no")
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
