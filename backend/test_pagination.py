import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock
from app.services.paperless import PaperlessClient

BASE = "http://fake-paperless"

def make_response(results, next_url=None):
    """Build a mock httpx response object."""
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {"count": 60, "next": next_url, "previous": None, "results": results}
    return mock

async def test_pagination():
    client = PaperlessClient(base_url=BASE, token="test-token")

    # Simulate 3 pages of 20 tags each (60 total)
    page1 = [{"id": i, "name": f"tag-{i}"} for i in range(1, 21)]
    page2 = [{"id": i, "name": f"tag-{i}"} for i in range(21, 41)]
    page3 = [{"id": i, "name": f"tag-{i}"} for i in range(41, 61)]

    client.client.get = AsyncMock(side_effect=[
        make_response(page1, next_url=f"{BASE}/api/tags/?page=2"),
        make_response(page2, next_url=f"{BASE}/api/tags/?page=3"),
        make_response(page3, next_url=None),
    ])

    tags = await client.get_tags()

    assert len(tags) == 60, f"Expected 60 tags, got {len(tags)}"
    assert client.client.get.call_count == 3, f"Expected 3 GET calls, got {client.client.get.call_count}"
    print(f"  PASS  get_tags() returned {len(tags)} items across {client.client.get.call_count} pages")

    await client.close()

async def test_single_page_not_truncated():
    """Verify single-page results (no 'next') still work correctly."""
    client = PaperlessClient(base_url=BASE, token="test-token")

    items = [{"id": i, "name": f"type-{i}"} for i in range(1, 11)]
    client.client.get = AsyncMock(return_value=make_response(items, next_url=None))

    result = await client.get_document_types()

    assert len(result) == 10, f"Expected 10, got {len(result)}"
    assert client.client.get.call_count == 1
    print(f"  PASS  get_document_types() returned {len(result)} items in 1 page")

    await client.close()

async def main():
    print("Testing pagination fix for PaperlessClient...")
    passed = 0
    failed = 0
    for test in [test_pagination, test_single_page_not_truncated]:
        try:
            await test()
            passed += 1
        except Exception as e:
            print(f"  FAIL  {test.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    asyncio.run(main())
