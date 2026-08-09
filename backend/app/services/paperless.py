"""HTTP client for the Paperless-ngx REST API.

Supports document CRUD, listing with pagination, and metadata entity fetching.
All requests include bearer token authentication.
"""

import asyncio
import httpx
import logging
import re
import time
from typing import Optional, Any
from urllib.parse import urlparse, urlunparse
from ..constants import (
    PAPERLESS_TIMEOUT,
    DEFAULT_PAGE_SIZE,
    DEFAULT_FETCH_SIZE,
    PAPERLESS_METADATA_CACHE_TTL,
)

logger = logging.getLogger(__name__)


def normalize_name(name: str) -> str:
    """Normalize a metadata name for duplicate detection.

    Casefolds and collapses internal whitespace so that names differing only in
    case or spacing (e.g. "Deutsche  Telekom" vs "deutsche telekom") compare
    equal. Shared by the client and the correspondent step so both sides of a
    get-or-create decision agree on what counts as the same entry.
    """
    return re.sub(r"\s+", " ", name or "").strip().casefold()


class PaperlessClient:
    """Async HTTP client for the Paperless-ngx API.

    Attributes:
        base_url: Base URL of the Paperless instance.
        token: Bearer token for authentication.
    """

    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None):
        """Initialize with optional base URL and token; defaults are read from config."""
        self.base_url = base_url
        self.token = token
        self.client = httpx.AsyncClient(timeout=PAPERLESS_TIMEOUT)
        self._metadata_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        # Bumped whenever a metadata write invalidates the cache. A GET that was
        # already in flight when the bump happened refuses to store its (now
        # stale) snapshot, so a freshly created entry cannot be masked until the
        # TTL expires.
        self._metadata_generation = 0
        # Serializes refresh+match+create in get_or_create_correspondent so two
        # documents proposing the same new correspondent cannot both create it.
        self._correspondent_write_lock = asyncio.Lock()
        self._request_count = 0
        self._paged_request_count = 0

    @classmethod
    async def from_config(cls) -> "PaperlessClient":
        """Factory: construct a client from the application config (paperless_url/token)."""
        base_url = await cls._get_config("paperless_url")
        token = await cls._get_config("paperless_token")
        if not base_url or not token:
            raise ValueError("Paperless URL and Token must be configured")
        return cls(base_url=base_url, token=token)

    @staticmethod
    async def _get_config(key: str) -> Optional[str]:
        """Read a config key from ConfigCache."""
        from .config_cache import ConfigCache

        cache = await ConfigCache.get_instance()
        return await cache.get(key)

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Token {self.token}",
            "Content-Type": "application/json",
        }

    async def _get_max_pages(self) -> int:
        from .config_cache import ConfigCache

        cache = await ConfigCache.get_instance()
        val = await cache.get("max_page_limit", str(DEFAULT_PAGE_SIZE))
        try:
            return int(val)
        except (ValueError, TypeError):
            return DEFAULT_PAGE_SIZE

    async def _get_fetch_size(self) -> int:
        from .config_cache import ConfigCache

        cache = await ConfigCache.get_instance()
        val = await cache.get("paperless_fetch_size", str(DEFAULT_FETCH_SIZE))
        try:
            size = int(val)
            return min(max(size, 50), 1000)
        except (ValueError, TypeError):
            return DEFAULT_FETCH_SIZE

    async def get_document(self, doc_id: int) -> dict[str, Any]:
        url = f"{self.base_url}/api/documents/{doc_id}/"
        logger.debug(f"GET {url}")
        self._request_count += 1
        response = await self.client.get(url, headers=self._get_headers())
        response.raise_for_status()
        return response.json()

    async def get_document_file(self, doc_id: int, original: bool = False) -> bytes:
        """Fetch a document file from Paperless.

        By default this keeps Paperless' normal download behavior. Set
        original=True for callers that explicitly need the uploaded source file.
        """
        url = f"{self.base_url}/api/documents/{doc_id}/download/"
        if original:
            url += "?original=true"
        logger.debug(f"GET {url}")
        self._request_count += 1
        response = await self.client.get(url, headers=self._get_headers())
        response.raise_for_status()
        return response.content

    async def list_documents(
        self,
        tags: Optional[list[int]] = None,
        tags_any: Optional[list[int]] = None,
        search: Optional[str] = None,
        max_page_limit: Optional[int] = None,
    ) -> list[dict]:
        fetch_size = await self._get_fetch_size()
        params: dict[str, Any] = {"page_size": fetch_size}
        if tags:
            params["tags__id__all"] = ",".join(map(str, tags))
        if tags_any:
            params["tags__id__in"] = ",".join(map(str, tags_any))
        if search:
            params["search"] = search
        url = f"{self.base_url}/api/documents/?" + "&".join(
            f"{k}={v}" for k, v in params.items()
        )
        page_limit = max_page_limit if max_page_limit is not None else await self._get_max_pages()
        return await self._get_all_pages(url, page_limit)

    async def _get_all_pages(
        self, url: str, max_page_limit: int = 100
    ) -> list[dict[str, Any]]:
        results = []
        next_url: Optional[str] = url
        base = urlparse(self.base_url)
        page = 0
        while next_url and page < max_page_limit:
            logger.debug(f"GET {next_url}")
            self._request_count += 1
            self._paged_request_count += 1
            response = await self.client.get(next_url, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()
            results.extend(data.get("results", []))
            page += 1
            raw_next = data.get("next")
            if raw_next:
                parsed = urlparse(raw_next)
                next_url = urlunparse(
                    parsed._replace(scheme=base.scheme, netloc=base.netloc)
                )
            else:
                next_url = None
        return results

    async def get_correspondents(
        self, force_refresh: bool = False
    ) -> list[dict[str, Any]]:
        return await self._get_cached_collection(
            "correspondents",
            f"{self.base_url}/api/correspondents/",
            force_refresh=force_refresh,
        )

    async def get_tags(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        return await self._get_cached_collection(
            "tags", f"{self.base_url}/api/tags/", force_refresh=force_refresh
        )

    async def get_document_types(
        self, force_refresh: bool = False
    ) -> list[dict[str, Any]]:
        return await self._get_cached_collection(
            "document_types",
            f"{self.base_url}/api/document_types/",
            force_refresh=force_refresh,
        )

    async def get_custom_fields(
        self, force_refresh: bool = False
    ) -> list[dict[str, Any]]:
        return await self._get_cached_collection(
            "custom_fields",
            f"{self.base_url}/api/custom_fields/",
            force_refresh=force_refresh,
        )

    async def _get_cached_collection(
        self, cache_key: str, url: str, force_refresh: bool = False
    ) -> list[dict[str, Any]]:
        now = time.monotonic()
        cached = self._metadata_cache.get(cache_key)
        if (
            not force_refresh
            and cached
            and (now - cached[0]) < PAPERLESS_METADATA_CACHE_TTL
        ):
            return cached[1]

        generation_at_start = self._metadata_generation
        fetch_size = await self._get_fetch_size()
        separator = "&" if "?" in url else "?"
        paged_url = f"{url}{separator}page_size={fetch_size}"
        data = await self._get_all_pages(paged_url, await self._get_max_pages())
        # Skip storing if a write invalidated the cache while this GET was in
        # flight: our snapshot predates the write and would hide the new entry.
        if self._metadata_generation == generation_at_start:
            self._metadata_cache[cache_key] = (now, data)
        return data

    async def update_document(
        self,
        doc_id: int,
        title: Optional[str] = None,
        correspondent: Optional[int] = None,
        document_type: Optional[int] = None,
        tags: Optional[list[int]] = None,
        custom_fields: Optional[dict] = None,
        content: Optional[str] = None,
        created_date: Optional[str] = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/api/documents/{doc_id}/"
        payload = {}
        if title is not None:
            payload["title"] = title
        if correspondent is not None:
            payload["correspondent"] = correspondent
        if document_type is not None:
            payload["document_type"] = document_type
        if tags is not None:
            payload["tags"] = tags
        if custom_fields is not None:
            payload["custom_fields"] = custom_fields
        if content is not None:
            payload["content"] = content
        if created_date is not None:
            payload["created"] = created_date

        logger.debug(f"PATCH {url} payload_keys={list(payload.keys())}")
        self._request_count += 1
        response = await self.client.patch(
            url, headers=self._get_headers(), json=payload
        )
        logger.debug(f"PATCH {url} → {response.status_code}")
        response.raise_for_status()
        return response.json()

    async def _create_correspondent(self, name: str) -> dict[str, Any]:
        """POST a new correspondent and return the created entity.

        Invalidates the cached correspondents collection (and bumps the metadata
        generation) so the new entry is visible to subsequent lookups. Prefer
        get_or_create_correspondent(); this is the raw write it builds on.
        """
        url = f"{self.base_url}/api/correspondents/"
        logger.debug(f"POST {url} name={name!r}")
        self._request_count += 1
        response = await self.client.post(
            url, headers=self._get_headers(), json={"name": name}
        )
        logger.debug(f"POST {url} → {response.status_code}")
        response.raise_for_status()
        self._metadata_cache.pop("correspondents", None)
        self._metadata_generation += 1
        return response.json()

    async def get_or_create_correspondent(
        self, name: str
    ) -> tuple[dict[str, Any], bool]:
        """Return ``(correspondent, created)`` for ``name``.

        Reuses an existing correspondent whenever one matches
        case/whitespace-insensitively; otherwise creates it. Refresh + match +
        POST run under a lock so that concurrent documents (Paperless-aissist
        processes several at once) proposing the same new name cannot each
        create a duplicate — Paperless only rejects exact-string collisions. The
        lock is held only around the metadata read and the write, never across
        the LLM call, which has already completed before this is invoked.

        If the POST fails (a concurrent writer, or a server-side uniqueness
        rule), the list is re-read under the lock and the now-present entry is
        reused; the error propagates only when nothing matches afterwards.
        """
        target = normalize_name(name)
        async with self._correspondent_write_lock:
            correspondents = await self.get_correspondents(force_refresh=True)
            match = next(
                (c for c in correspondents if normalize_name(c["name"]) == target),
                None,
            )
            if match:
                return match, False

            try:
                created = await self._create_correspondent(name)
                return created, True
            except Exception:
                correspondents = await self.get_correspondents(force_refresh=True)
                match = next(
                    (c for c in correspondents if normalize_name(c["name"]) == target),
                    None,
                )
                if match:
                    return match, False
                raise

    @property
    def is_closed(self) -> bool:
        return self.client.is_closed

    def get_metrics(self) -> dict[str, int]:
        return {
            "requests": self._request_count,
            "paged_requests": self._paged_request_count,
        }

    def reset_metrics(self) -> None:
        self._request_count = 0
        self._paged_request_count = 0

    async def close(self):
        await self.client.aclose()
