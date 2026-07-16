"""Recovery from stale metadata cache references (issue #36).

When a correspondent or document type was deleted in Paperless after our
metadata cache picked it up, the final update fails with a 400 "Invalid pk ...
object does not exist". The processor should refresh the cache, drop the stale
references, and retry with what is still valid instead of failing the document.
"""

import httpx
import pytest

from app.services.processor import DocumentProcessor


def _invalid_pk_error(field: str, pk: int) -> httpx.HTTPStatusError:
    request = httpx.Request("PATCH", "http://paperless:8000/api/documents/26/")
    response = httpx.Response(
        400,
        request=request,
        text=f'{{"{field}":["Invalid pk \\"{pk}\\" - object does not exist."]}}',
    )
    return httpx.HTTPStatusError(
        "Client error '400 Bad Request'", request=request, response=response
    )


class StubPaperless:
    def __init__(self, fail_times: int = 1, error: httpx.HTTPStatusError | None = None):
        self.update_calls: list[dict] = []
        self.refresh_calls: list[str] = []
        self._fail_times = fail_times
        self._error = error or _invalid_pk_error("document_type", 10)

    async def update_document(self, doc_id: int, **kwargs):
        self.update_calls.append(kwargs)
        if self._fail_times > 0:
            self._fail_times -= 1
            raise self._error

    async def get_correspondents(self, force_refresh: bool = False):
        self.refresh_calls.append("correspondents")
        return [{"id": 5, "name": "Emons"}]

    async def get_document_types(self, force_refresh: bool = False):
        self.refresh_calls.append("document_types")
        return [{"id": 7, "name": "Invoice"}]


@pytest.mark.asyncio
async def test_stale_document_type_is_dropped_and_update_retried():
    paperless = StubPaperless()
    processor = DocumentProcessor(paperless)

    await processor._apply_metadata_update(26, "New title", 5, 10)

    assert len(paperless.update_calls) == 2
    retry = paperless.update_calls[1]
    assert retry["title"] == "New title"
    assert retry["correspondent"] == 5  # still valid — kept
    assert retry["document_type"] is None  # stale — dropped
    assert "document_types" in paperless.refresh_calls


@pytest.mark.asyncio
async def test_stale_correspondent_is_dropped_too():
    paperless = StubPaperless(error=_invalid_pk_error("correspondent", 99))
    processor = DocumentProcessor(paperless)

    await processor._apply_metadata_update(26, None, 99, 7)

    retry = paperless.update_calls[1]
    assert retry["correspondent"] is None
    assert retry["document_type"] == 7


@pytest.mark.asyncio
async def test_no_retry_when_nothing_valid_remains():
    # Everything stale and no title: nothing left worth updating — no retry, no raise.
    paperless = StubPaperless(error=_invalid_pk_error("document_type", 10))
    processor = DocumentProcessor(paperless)

    await processor._apply_metadata_update(26, None, 99, 10)

    assert len(paperless.update_calls) == 1


@pytest.mark.asyncio
async def test_unrelated_400_is_reraised():
    request = httpx.Request("PATCH", "http://paperless:8000/api/documents/26/")
    response = httpx.Response(400, request=request, text='{"title":["Too long."]}')
    error = httpx.HTTPStatusError("Client error '400 Bad Request'", request=request, response=response)
    paperless = StubPaperless(error=error)
    processor = DocumentProcessor(paperless)

    with pytest.raises(httpx.HTTPStatusError):
        await processor._apply_metadata_update(26, "x", None, 10)
    assert len(paperless.update_calls) == 1


@pytest.mark.asyncio
async def test_reraises_when_refresh_does_not_explain_the_error():
    # 400 says "does not exist" but the fresh cache still contains both IDs:
    # dropping nothing means retrying would fail identically — re-raise.
    paperless = StubPaperless()
    processor = DocumentProcessor(paperless)

    with pytest.raises(httpx.HTTPStatusError):
        await processor._apply_metadata_update(26, "x", 5, 7)
    assert len(paperless.update_calls) == 1
