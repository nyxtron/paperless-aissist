"""Turns away changing requests that a browser sends on behalf of another website.

CORS only stops a foreign page from reading the answer. A POST without a body
needs no preflight, so while the login is off any website a user visits could
stop the scheduler or start a run. Same idea as Go's CrossOriginProtection.
"""

import logging
from typing import Iterable
from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def is_foreign(headers: Headers, allowed: frozenset[str]) -> bool:
    """Whether a browser sent this from a page outside the app and its allow-list."""
    origin = (headers.get("origin") or "").lower()
    if "*" in allowed or origin in allowed:
        return False
    fetch_site = (headers.get("sec-fetch-site") or "").lower()
    if fetch_site:
        return fetch_site not in ("same-origin", "none")
    # Browsers only send Sec-Fetch-Site on HTTPS and localhost, so a plain-HTTP
    # install on the LAN ends up here. Scripts send no Origin at all.
    if not origin:
        return False
    hosts = [headers.get("host") or ""]
    hosts += (headers.get("x-forwarded-host") or "").split(",")
    own = {h.strip().lower() for h in hosts if h.strip()}
    return urlsplit(origin).netloc not in own


class OriginGuard:
    """Pure ASGI, so the streaming log and MCP responses are not buffered."""

    def __init__(self, app, allowed: Iterable[str] = ()):
        self.app = app
        self.allowed = frozenset(o.lower() for o in allowed)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] not in SAFE_METHODS:
            headers = Headers(scope=scope)
            if is_foreign(headers, self.allowed):
                logger.warning(
                    "Rejected %s %s from origin %r (host %r). If this is your own "
                    "address, add it to CORS_ALLOW_ORIGINS.",
                    scope["method"], scope["path"], headers.get("origin"), headers.get("host"),
                )
                response = JSONResponse(
                    {"detail": "Request from another origin rejected. If it is yours, add it to CORS_ALLOW_ORIGINS."},
                    status_code=403,
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
