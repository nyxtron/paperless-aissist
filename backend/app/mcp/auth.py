"""MCP bearer-token verifier reusing the hashed paia_ automation token."""

import hmac

from fastmcp.server.auth import TokenVerifier, AccessToken

from ..auth import AUTOMATION_API_TOKEN_HASH_KEY, hash_automation_token
from ..services.config_cache import get_config_value


def _get_automation_token_hash() -> str:
    """Read the stored automation token hash (sync; reuses config lookup)."""
    return get_config_value(AUTOMATION_API_TOKEN_HASH_KEY, "") or ""


class AissistTokenVerifier(TokenVerifier):
    """Validate an incoming bearer token against the stored paia_ token hash."""

    async def verify_token(self, token: str) -> AccessToken | None:
        stored_hash = _get_automation_token_hash()
        if not stored_hash:
            return None
        provided_hash = hash_automation_token(token)
        if not hmac.compare_digest(provided_hash, stored_hash):
            return None
        return AccessToken(token=token, client_id="automation", scopes=[])
