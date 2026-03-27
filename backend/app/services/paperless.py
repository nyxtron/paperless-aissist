import httpx
import logging
import os
from typing import Optional, Any
from urllib.parse import urlparse, urlunparse
from ..models import Config
from ..database import get_session
from sqlmodel import select

logger = logging.getLogger(__name__)


class PaperlessClient:
    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None):
        self.base_url = base_url
        self.token = token
        self.client = httpx.AsyncClient(timeout=60.0)

    @classmethod
    async def from_config(cls) -> "PaperlessClient":
        base_url = await cls._get_config("paperless_url")
        token = await cls._get_config("paperless_token")
        if not base_url or not token:
            raise ValueError("Paperless URL and Token must be configured")
        return cls(base_url=base_url, token=token)

    @staticmethod
    async def _get_config(key: str) -> Optional[str]:
        # First try to get from database
        with get_session() as session:
            stmt = select(Config).where(Config.key == key)
            config = session.exec(stmt).first()
            if config and config.value:
                return config.value

        # Fallback to environment variable
        env_key = key.upper().replace("-", "_")
        return os.environ.get(env_key)

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Token {self.token}",
            "Content-Type": "application/json",
        }

    def _get_max_pages(self) -> int:
        with get_session() as session:
            stmt = select(Config).where(Config.key == "max_page_limit")
            config = session.exec(stmt).first()
            return int(config.value) if config else 100

    async def get_document(self, doc_id: int) -> dict[str, Any]:
        url = f"{self.base_url}/api/documents/{doc_id}/"
        logger.debug(f"GET {url}")
        response = await self.client.get(url, headers=self._get_headers())
        response.raise_for_status()
        return response.json()

    async def get_document_file(self, doc_id: int) -> bytes:
        url = f"{self.base_url}/api/documents/{doc_id}/download/"
        logger.debug(f"GET {url}")
        response = await self.client.get(url, headers=self._get_headers())
        response.raise_for_status()
        return response.content

    async def list_documents(
        self,
        tags: Optional[list[int]] = None,
        search: Optional[str] = None,
        max_page_limit: int = 100,
    ) -> list[dict]:
        params: dict[str, Any] = {"page_size": 100}
        if tags:
            params["tags__id__all"] = ",".join(map(str, tags))
        if search:
            params["search"] = search
        url = f"{self.base_url}/api/documents/?" + "&".join(
            f"{k}={v}" for k, v in params.items()
        )
        return await self._get_all_pages(url, max_page_limit)

    async def _get_all_pages(
        self, url: str, max_page_limit: int = 100
    ) -> list[dict[str, Any]]:
        results = []
        next_url: Optional[str] = url
        base = urlparse(self.base_url)
        page = 0
        while next_url and page < max_page_limit:
            logger.debug(f"GET {next_url}")
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

    async def get_correspondents(self) -> list[dict[str, Any]]:
        return await self._get_all_pages(
            f"{self.base_url}/api/correspondents/", self._get_max_pages()
        )

    async def get_tags(self) -> list[dict[str, Any]]:
        return await self._get_all_pages(
            f"{self.base_url}/api/tags/", self._get_max_pages()
        )

    async def get_document_types(self) -> list[dict[str, Any]]:
        return await self._get_all_pages(
            f"{self.base_url}/api/document_types/", self._get_max_pages()
        )

    async def get_custom_fields(self) -> list[dict[str, Any]]:
        return await self._get_all_pages(
            f"{self.base_url}/api/custom_fields/", self._get_max_pages()
        )

    async def update_document(
        self,
        doc_id: int,
        title: Optional[str] = None,
        correspondent: Optional[int] = None,
        document_type: Optional[int] = None,
        tags: Optional[list[int]] = None,
        custom_fields: Optional[dict] = None,
        content: Optional[str] = None,
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

        logger.debug(f"PATCH {url} payload_keys={list(payload.keys())}")
        response = await self.client.patch(
            url, headers=self._get_headers(), json=payload
        )
        logger.debug(f"PATCH {url} → {response.status_code}")
        response.raise_for_status()
        return response.json()

    async def close(self):
        await self.client.aclose()
