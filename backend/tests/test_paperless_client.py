from unittest.mock import AsyncMock, MagicMock

import pytest

from app.constants import PAPERLESS_METADATA_CACHE_TTL
from app.services.paperless import PaperlessClient


BASE_URL = "http://paperless.test"


def make_response(results, next_url=None):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "count": len(results),
        "next": next_url,
        "previous": None,
        "results": results,
    }
    return response


def make_binary_response(content=b"pdf bytes"):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.content = content
    return response


@pytest.mark.parametrize(
    ("method_name", "path"),
    [
        ("get_tags", "tags"),
        ("get_correspondents", "correspondents"),
        ("get_document_types", "document_types"),
        ("get_custom_fields", "custom_fields"),
    ],
)
@pytest.mark.asyncio
async def test_metadata_collections_request_configured_fetch_size(method_name, path):
    client = PaperlessClient(base_url=BASE_URL, token="token")
    client.client.get = AsyncMock(return_value=make_response([]))

    await getattr(client, method_name)()

    requested_url = client.client.get.call_args.args[0]
    assert requested_url == f"{BASE_URL}/api/{path}/?page_size=1000"

    await client.close()


@pytest.mark.asyncio
async def test_metadata_collections_are_cached_between_calls():
    client = PaperlessClient(base_url=BASE_URL, token="token")
    client.client.get = AsyncMock(
        return_value=make_response([{"id": 1, "name": "ai-process"}])
    )

    first = await client.get_tags()
    second = await client.get_tags()

    assert first == second
    assert client.client.get.call_count == 1

    await client.close()


@pytest.mark.asyncio
async def test_metadata_collection_force_refresh_fetches_and_replaces_cache():
    client = PaperlessClient(base_url=BASE_URL, token="token")
    client.client.get = AsyncMock(
        side_effect=[
            make_response([{"id": 1, "name": "old"}]),
            make_response([{"id": 2, "name": "new"}]),
        ]
    )

    first = await client.get_tags()
    second = await client.get_tags(force_refresh=True)
    third = await client.get_tags()

    assert first == [{"id": 1, "name": "old"}]
    assert second == [{"id": 2, "name": "new"}]
    assert third == second
    assert client.client.get.call_count == 2

    await client.close()


@pytest.mark.asyncio
async def test_get_document_file_uses_paperless_default_download_by_default():
    client = PaperlessClient(base_url=BASE_URL, token="token")
    client.client.get = AsyncMock(return_value=make_binary_response(b"archive pdf"))

    content = await client.get_document_file(42)

    assert content == b"archive pdf"
    requested_url = client.client.get.call_args.args[0]
    assert requested_url == f"{BASE_URL}/api/documents/42/download/"

    await client.close()


@pytest.mark.asyncio
async def test_get_document_file_can_request_original_document():
    client = PaperlessClient(base_url=BASE_URL, token="token")
    client.client.get = AsyncMock(return_value=make_binary_response(b"original pdf"))

    content = await client.get_document_file(42, original=True)

    assert content == b"original pdf"
    requested_url = client.client.get.call_args.args[0]
    assert requested_url == f"{BASE_URL}/api/documents/42/download/?original=true"

    await client.close()


def test_metadata_cache_ttl_is_one_hour():
    assert PAPERLESS_METADATA_CACHE_TTL == 3600


@pytest.mark.asyncio
async def test_update_document_maps_created_date_to_paperless_created_field():
    client = PaperlessClient(base_url=BASE_URL, token="token")
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"id": 1051, "created": "2026-04-28"}
    client.client.patch = AsyncMock(return_value=response)

    await client.update_document(1051, created_date="2026-04-28")

    assert client.client.patch.await_args.kwargs["json"] == {"created": "2026-04-28"}

    await client.close()


@pytest.mark.asyncio
async def test_get_tags_follows_pagination_across_pages():
    client = PaperlessClient(base_url=BASE_URL, token="token")
    page1 = [{"id": i, "name": f"tag-{i}"} for i in range(1, 21)]
    page2 = [{"id": i, "name": f"tag-{i}"} for i in range(21, 41)]
    page3 = [{"id": i, "name": f"tag-{i}"} for i in range(41, 61)]
    client.client.get = AsyncMock(
        side_effect=[
            make_response(page1, next_url=f"{BASE_URL}/api/tags/?page=2"),
            make_response(page2, next_url=f"{BASE_URL}/api/tags/?page=3"),
            make_response(page3, next_url=None),
        ]
    )

    tags = await client.get_tags()

    assert len(tags) == 60
    assert client.client.get.call_count == 3

    await client.close()


@pytest.mark.asyncio
async def test_get_document_types_single_page_is_not_truncated():
    client = PaperlessClient(base_url=BASE_URL, token="token")
    items = [{"id": i, "name": f"type-{i}"} for i in range(1, 11)]
    client.client.get = AsyncMock(return_value=make_response(items, next_url=None))

    result = await client.get_document_types()

    assert len(result) == 10
    assert client.client.get.call_count == 1

    await client.close()
