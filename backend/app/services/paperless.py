import httpx
import os
from typing import Optional, Any
from ..models import Config
from ..database import get_session
from sqlmodel import select


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
    
    async def get_document(self, doc_id: int) -> dict[str, Any]:
        url = f"{self.base_url}/api/documents/{doc_id}/"
        response = await self.client.get(url, headers=self._get_headers())
        response.raise_for_status()
        return response.json()
    
    async def get_document_file(self, doc_id: int) -> bytes:
        url = f"{self.base_url}/api/documents/{doc_id}/download/"
        response = await self.client.get(url, headers=self._get_headers())
        response.raise_for_status()
        return response.content
    
    async def list_documents(self, tags: Optional[list[int]] = None, limit: int = 50) -> list[dict]:
        url = f"{self.base_url}/api/documents/"
        params = {"limit": limit}
        if tags:
            params["tags__id"] = ",".join(map(str, tags))
        
        response = await self.client.get(url, headers=self._get_headers(), params=params)
        response.raise_for_status()
        data = response.json()
        return data.get("results", [])
    
    async def get_correspondents(self) -> list[dict[str, Any]]:
        url = f"{self.base_url}/api/correspondents/"
        response = await self.client.get(url, headers=self._get_headers())
        response.raise_for_status()
        data = response.json()
        return data.get("results", [])
    
    async def get_tags(self) -> list[dict[str, Any]]:
        url = f"{self.base_url}/api/tags/"
        response = await self.client.get(url, headers=self._get_headers())
        response.raise_for_status()
        data = response.json()
        return data.get("results", [])
    
    async def get_document_types(self) -> list[dict[str, Any]]:
        url = f"{self.base_url}/api/document_types/"
        response = await self.client.get(url, headers=self._get_headers())
        response.raise_for_status()
        data = response.json()
        return data.get("results", [])
    
    async def get_custom_fields(self) -> list[dict[str, Any]]:
        url = f"{self.base_url}/api/custom_fields/"
        response = await self.client.get(url, headers=self._get_headers())
        response.raise_for_status()
        data = response.json()
        return data.get("results", [])
    
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
        
        response = await self.client.patch(url, headers=self._get_headers(), json=payload)
        response.raise_for_status()
        return response.json()
    
    async def close(self):
        await self.client.aclose()
