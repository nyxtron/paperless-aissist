from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_config_crud(client):
    """Test full CRUD cycle for config values."""
    response = client.post(
        "/api/config",
        json={"key": "test_integration_key", "value": "test_value"},
    )
    assert response.status_code == 200
    assert response.json()["key"] == "test_integration_key"
    assert response.json()["value"] == "test_value"

    response = client.get("/api/config/test_integration_key")
    assert response.status_code == 200
    assert response.json()["value"] == "test_value"

    response = client.post(
        "/api/config",
        json={"key": "test_integration_key", "value": "updated_value"},
    )
    assert response.status_code == 200
    assert response.json()["value"] == "updated_value"

    response = client.delete("/api/config/test_integration_key")
    assert response.status_code == 200

    response = client.get("/api/config/test_integration_key")
    assert response.status_code == 404


def test_config_list_masks_secrets(client):
    """Sensitive keys are excluded from GET /api/config and listed in secrets_set."""
    client.post(
        "/api/config", json={"key": "llm_api_key", "value": "sk-super-secret-key-12345"}
    )
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert "llm_api_key" not in data["data"]
    assert "secrets_set" in data
    assert "llm_api_key" in data["secrets_set"]


def test_config_sensitive_key_not_accessible(client):
    """GET /api/config/{key} returns 404 for sensitive keys."""
    for key in ["paperless_token", "llm_api_key", "llm_api_key_vision"]:
        response = client.get(f"/api/config/{key}")
        assert response.status_code == 404, (
            f"Expected 404 for {key}, got {response.status_code}"
        )


def test_paperless_url_trailing_slash_is_stripped(client):
    """paperless_url is normalized: surrounding whitespace and trailing slashes removed."""
    response = client.post(
        "/api/config",
        json={"key": "paperless_url", "value": "  http://paperless.local///  "},
    )
    assert response.status_code == 200
    assert response.json()["value"] == "http://paperless.local"

    response = client.get("/api/config/paperless_url")
    assert response.status_code == 200
    assert response.json()["value"] == "http://paperless.local"


def test_paperless_url_without_scheme_is_rejected(client):
    """paperless_url without http(s):// scheme returns a clear 400."""
    response = client.post(
        "/api/config",
        json={"key": "paperless_url", "value": "paperless.local"},
    )
    assert response.status_code == 400
    assert "http://" in response.json()["detail"]


def test_paperless_url_empty_value_is_allowed(client):
    """Clearing paperless_url (empty string) is allowed and stays empty."""
    response = client.post(
        "/api/config",
        json={"key": "paperless_url", "value": ""},
    )
    assert response.status_code == 200
    assert response.json()["value"] == ""


def test_other_config_keys_are_not_normalized(client):
    """Normalization only applies to paperless_url — other keys keep trailing slashes."""
    response = client.post(
        "/api/config",
        json={"key": "llm_api_base", "value": "http://localhost:11434/"},
    )
    assert response.status_code == 200
    assert response.json()["value"] == "http://localhost:11434/"


def test_stats_endpoints(client):
    """Stats endpoints return valid data."""
    response = client.get("/api/stats")
    assert response.status_code == 200
    assert "total_processed" in response.json()

    response = client.get("/api/stats/daily?days=7")
    assert response.status_code == 200

    response = client.get("/api/stats/recent?limit=10")
    assert response.status_code == 200


def test_stats_bounds(client):
    """Stats endpoints enforce parameter bounds."""
    response = client.get("/api/stats/daily?days=500")
    assert response.status_code == 200

    response = client.get("/api/stats/recent?limit=5000")
    assert response.status_code == 200


def test_auth_status_endpoint(client):
    """Auth status returns auth_enabled flag."""
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    assert "auth_enabled" in response.json()


def test_app_info_endpoint(client):
    """App info endpoint exposes the runtime version string."""
    response = client.get("/api/app-info")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert isinstance(data["version"], str)
    assert data["version"]


def test_prompts_list(client):
    """Prompts endpoint returns a list."""
    response = client.get("/api/prompts")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_scheduler_status_endpoint(client):
    """Scheduler status endpoint returns JSON."""
    response = client.get("/api/scheduler")
    assert response.status_code == 200
    data = response.json()
    assert "enabled" in data or "is_processing" in data
    assert "interval_minutes" in data or "interval" in data


def test_stats_log_stream_asyncio_imported(client):
    """Verify asyncio is imported in stats.py so event_gen does not NameError."""
    import ast
    import inspect
    from app.routers.stats import stream_logs

    source = inspect.getsource(stream_logs)
    tree = ast.parse(source)
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert "asyncio" in names


def test_tagged_documents_uses_combined_tag_filter_and_deduplicates(client):
    client.post("/api/config", json={"key": "process_tag", "value": "ai-process"})
    client.post(
        "/api/config", json={"key": "paperless_url", "value": "http://paperless.local/"}
    )
    paperless = MagicMock()
    paperless.base_url = "http://paperless.local/"
    paperless.reset_metrics = MagicMock()
    paperless.get_metrics = MagicMock(return_value={"requests": 2, "paged_requests": 1})
    paperless.get_tags = AsyncMock(
        return_value=[
            {"id": 5, "name": "ai-process"},
            {"id": 7, "name": "ai-title"},
        ]
    )
    paperless.list_documents = AsyncMock(
        return_value=[
            {"id": 1, "title": "Legacy", "created": "2026-01-01", "tags": [5]},
            {"id": 2, "title": "Both", "created": "2026-01-02", "tags": [5, 7]},
            {"id": 2, "title": "Both", "created": "2026-01-02", "tags": [5, 7]},
            {"id": 3, "title": "Title", "created": "2026-01-03", "tags": [7]},
        ]
    )

    with (
        patch(
            "app.routers.documents.PaperlessClientManager.get_client",
            AsyncMock(return_value=paperless),
        ),
        patch(
            "app.routers.documents.DocumentProcessor._get_modular_tag_map",
            AsyncMock(return_value={"title": "ai-title"}),
        ),
    ):
        response = client.get("/api/documents/tagged")

    assert response.status_code == 200
    data = response.json()
    assert [doc["id"] for doc in data["documents"]] == [1, 2, 3]
    assert data["process_tag_id"] == 5
    assert data["paperless_url"] == "http://paperless.local/"
    paperless.list_documents.assert_awaited_once_with(tags_any=[5, 7])


def test_tagged_documents_no_trigger_tags_does_not_scan_documents(client):
    client.post("/api/config", json={"key": "process_tag", "value": "missing-process"})
    paperless = MagicMock()
    paperless.reset_metrics = MagicMock()
    paperless.get_tags = AsyncMock(return_value=[{"id": 10, "name": "unrelated"}])
    paperless.list_documents = AsyncMock(return_value=[])

    with (
        patch(
            "app.routers.documents.PaperlessClientManager.get_client",
            AsyncMock(return_value=paperless),
        ),
        patch(
            "app.routers.documents.DocumentProcessor._get_modular_tag_map",
            AsyncMock(return_value={"title": "missing-title"}),
        ),
    ):
        response = client.get("/api/documents/tagged")

    assert response.status_code == 200
    assert response.json()["documents"] == []
    paperless.list_documents.assert_not_called()


def test_paperless_client_list_documents_supports_all_and_any_tag_filters(monkeypatch):
    from app.services.paperless import PaperlessClient

    client_instance = PaperlessClient(base_url="http://paperless.local", token="token")
    captured_urls = []

    async def fake_fetch_size():
        return 100

    async def fake_max_pages():
        return 10

    async def fake_get_all_pages(url, max_page_limit):
        captured_urls.append((url, max_page_limit))
        return []

    monkeypatch.setattr(client_instance, "_get_fetch_size", fake_fetch_size)
    monkeypatch.setattr(client_instance, "_get_max_pages", fake_max_pages)
    monkeypatch.setattr(client_instance, "_get_all_pages", fake_get_all_pages)

    import asyncio

    asyncio.run(client_instance.list_documents(tags=[1, 2], tags_any=[3, 4]))

    url, page_limit = captured_urls[0]
    assert page_limit == 10
    assert "tags__id__all=1,2" in url
    assert "tags__id__in=3,4" in url


@pytest.mark.asyncio
async def test_modular_scheduler_scan_uses_combined_tag_filter():
    from app.services import scheduler as scheduler_service

    paperless = MagicMock()
    paperless.reset_metrics = MagicMock()
    paperless.get_metrics = MagicMock(return_value={"requests": 2, "paged_requests": 1})
    paperless.get_tags = AsyncMock(
        return_value=[
            {"id": 7, "name": "ai-title"},
            {"id": 8, "name": "ai-tags"},
        ]
    )
    paperless.list_documents = AsyncMock(
        return_value=[
            {"id": 3, "title": "Title", "tags": [7]},
            {"id": 4, "title": "Tags", "tags": [8]},
        ]
    )

    processor = MagicMock()
    processor._get_config = AsyncMock(return_value="ai-process")
    processor._get_modular_tag_map = AsyncMock(
        return_value={"title": "ai-title", "tags": "ai-tags"}
    )
    processor.process_document = AsyncMock(
        side_effect=[
            {"success": True, "document_id": 3},
            {"success": True, "document_id": 4},
        ]
    )

    with (
        patch(
            "app.services.paperless_manager.PaperlessClientManager.get_client",
            AsyncMock(return_value=paperless),
        ),
        patch("app.services.processor.DocumentProcessor", return_value=processor),
    ):
        result = await scheduler_service.process_modular_tagged_documents()

    assert result["processed"] == 2
    paperless.list_documents.assert_awaited_once_with(tags_any=[7, 8])
    assert processor.process_document.await_count == 2


@pytest.mark.asyncio
async def test_modular_scheduler_excludes_process_tag_and_counts_failures():
    from app.services import scheduler as scheduler_service

    paperless = MagicMock()
    paperless.reset_metrics = MagicMock()
    paperless.get_metrics = MagicMock(return_value={"requests": 2, "paged_requests": 1})
    paperless.get_tags = AsyncMock(
        return_value=[
            {"id": 5, "name": "ai-process"},
            {"id": 7, "name": "ai-title"},
        ]
    )
    paperless.list_documents = AsyncMock(
        return_value=[
            {"id": 3, "title": "Title", "tags": [7]},
            {"id": 4, "title": "Failed", "tags": [7]},
        ]
    )

    processor = MagicMock()
    processor._get_config = AsyncMock(return_value="ai-process")
    processor._get_modular_tag_map = AsyncMock(
        return_value={"process": "ai-process", "title": "ai-title"}
    )
    processor.process_document = AsyncMock(
        side_effect=[
            {"success": True, "document_id": 3},
            {"success": False, "document_id": 4, "error": "timeout"},
        ]
    )

    with (
        patch(
            "app.services.paperless_manager.PaperlessClientManager.get_client",
            AsyncMock(return_value=paperless),
        ),
        patch("app.services.processor.DocumentProcessor", return_value=processor),
    ):
        result = await scheduler_service.process_modular_tagged_documents()

    assert result["success"] is False
    assert result["processed"] == 1
    assert result["failed"] == 1
    paperless.list_documents.assert_awaited_once_with(tags_any=[7])


def test_trigger_processing_reports_failed_results(client):
    with (
        patch("app.routers.documents.try_trigger_processing", return_value=(True, "")),
        patch(
            "app.routers.documents.process_tagged_with_state",
            AsyncMock(
                return_value={
                    "success": False,
                    "processed": 1,
                    "failed": 1,
                    "results": [
                        {"success": True, "document_id": 1},
                        {"success": False, "document_id": 2, "error": "timeout"},
                    ],
                }
            ),
        ),
        patch(
            "app.routers.documents.process_modular_with_state",
            AsyncMock(return_value={"success": True, "processed": 0, "failed": 0, "results": []}),
        ),
        patch("app.routers.documents._clear_processing"),
    ):
        response = client.post("/api/documents/trigger")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["processed"] == 1
    assert data["failed"] == 1


def test_metadata_routes_pass_refresh_to_paperless_client(client):
    paperless = MagicMock()
    paperless.get_tags = AsyncMock(return_value=[{"id": 1, "name": "ai-process"}])
    paperless.get_correspondents = AsyncMock(return_value=[])
    paperless.get_document_types = AsyncMock(return_value=[])

    with patch(
        "app.routers.documents.PaperlessClientManager.get_client",
        AsyncMock(return_value=paperless),
    ):
        tags_response = client.get("/api/documents/tags?refresh=true")
        test_response = client.get("/api/documents/test-connection?refresh=true")

    assert tags_response.status_code == 200
    assert test_response.status_code == 200
    assert paperless.get_tags.call_args_list[0].kwargs == {"force_refresh": True}
    assert paperless.get_correspondents.call_args_list[0].kwargs == {
        "force_refresh": True
    }
    assert paperless.get_document_types.call_args_list[0].kwargs == {
        "force_refresh": True
    }
    assert paperless.get_tags.call_args_list[1].kwargs == {"force_refresh": True}
