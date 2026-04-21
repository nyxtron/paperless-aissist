"""Singleton wrapper for the PaperlessClient.

Ensures a single shared client instance across the application lifecycle.
"""

from typing import Optional
import asyncio
from .paperless import PaperlessClient


class PaperlessClientManager:
    """Singleton manager for the shared PaperlessClient instance."""

    _client: Optional[PaperlessClient] = None
    _lock: asyncio.Lock = asyncio.Lock()

    @classmethod
    async def get_client(cls) -> PaperlessClient:
        """Return the cached client, creating one from config if needed."""
        if cls._client is not None and not cls._client.is_closed:
            return cls._client
        async with cls._lock:
            if cls._client is not None and not cls._client.is_closed:
                return cls._client
            client = await PaperlessClient.from_config()
            old = cls._client
            cls._client = client
            if old is not None:
                try:
                    await old.close()
                except Exception:
                    pass
            return cls._client

    @classmethod
    async def close(cls):
        """Close the shared client and clear the reference."""
        async with cls._lock:
            if cls._client is not None:
                try:
                    await cls._client.close()
                except Exception:
                    pass
                cls._client = None

    @classmethod
    async def reset(cls):
        """Close the client and clear the reference (for config changes)."""
        async with cls._lock:
            old = cls._client
            cls._client = None
        if old is not None:
            try:
                await old.close()
            except Exception:
                pass
