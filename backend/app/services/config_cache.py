"""In-memory configuration cache backed by SQLite.

Provides both a simple blocking getter (for sync contexts) and an async
singleton ConfigCache with TTL-based invalidation.
"""

import asyncio
import os
import time
from typing import Optional
from ..constants import CONFIG_CACHE_TTL


def get_config_value(key: str, default: Optional[str] = None) -> Optional[str]:
    """Fetch a config value from DB, falling back to environment variables.

    Args:
        key: Configuration key.
        default: Default value if not found.

    Returns:
        The configuration value or default.
    """
    from ..database import get_session
    from ..models import Config
    from sqlmodel import select

    with get_session() as session:
        stmt = select(Config).where(Config.key == key)
        config = session.exec(stmt).first()
        if config and config.value:
            return config.value

    env_key = key.upper().replace("-", "_")
    return os.environ.get(env_key, default)


class ConfigCache:
    """Async singleton cache for all config key-value pairs with TTL invalidation."""

    _instance: Optional["ConfigCache"] = None
    _lock: Optional[asyncio.Lock] = None

    def __init__(self):
        """Initialize empty cache with default TTL from constants."""
        self._cache: dict[str, str] = {}
        self._loaded_at: float = 0
        self._ttl_seconds: float = CONFIG_CACHE_TTL

    @classmethod
    async def _get_lock(cls) -> asyncio.Lock:
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        return cls._lock

    @classmethod
    async def get_instance(cls) -> "ConfigCache":
        """Return the singleton ConfigCache, loading from DB on first call."""
        if cls._instance is None:
            async with await cls._get_lock():
                if cls._instance is None:
                    cls._instance = cls()
                    await cls._instance._load()
        return cls._instance

    async def get(self, key: str, default: str = "") -> str:
        """Return a cached value, reloading if expired.

        Args:
            key: Configuration key.
            default: Default value if not found.

        Returns:
            The cached value or default.
        """
        if self._is_expired():
            async with await self._get_lock():
                if self._is_expired():
                    await self._load()
        return self._cache.get(key, default)

    async def get_all(self) -> dict[str, str]:
        """Return a copy of the entire cache, reloading if expired."""
        if self._is_expired():
            async with await self._get_lock():
                if self._is_expired():
                    await self._load()
        return dict(self._cache)

    async def invalidate(self):
        async with await self._get_lock():
            self._loaded_at = 0
            self._cache.clear()

    def _is_expired(self) -> bool:
        if self._loaded_at == 0:
            return True
        return (time.monotonic() - self._loaded_at) > self._ttl_seconds

    async def _load(self):
        """Load all config entries from the database into the cache."""
        from ..database import get_async_session
        from ..models import Config
        from sqlmodel import select

        async with get_async_session() as session:
            result = await session.exec(select(Config))
            configs = result.all()
            self._cache = {c.key: c.value for c in configs}
        self._loaded_at = time.monotonic()
