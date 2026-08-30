import logging

import pytest

from app.database import get_session
from app.models import Config
from app.services import scheduler as scheduler_service
from sqlmodel import select


def _automation_headers(client):
    response = client.post("/api/config/automation-token")
    assert response.status_code == 200
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}, token


def test_generate_automation_token_is_stored_hashed_and_masked(client):
    response = client.post("/api/config/automation-token")

    assert response.status_code == 200
    token = response.json()["token"]
    assert token.startswith("paia_")

    with get_session() as session:
        stmt = select(Config).where(Config.key == "automation_api_token_hash")
        stored = session.exec(stmt).first()
        stored_value = stored.value if stored else None

    assert stored is not None
    assert stored_value != token
    assert len(stored_value) == 64

    config_response = client.get("/api/config")
    assert config_response.status_code == 200
    config_payload = config_response.json()
    assert "automation_api_token_hash" not in config_payload["data"]
    assert "automation_api_token_hash" in config_payload["secrets_set"]
    assert token not in str(config_payload)

    direct_response = client.get("/api/config/automation_api_token_hash")
    assert direct_response.status_code == 404


def test_revoke_automation_token_removes_secret_status(client):
    headers, _ = _automation_headers(client)
    assert client.get("/api/automation/status", headers=headers).status_code == 200

    response = client.delete("/api/config/automation-token")

    assert response.status_code == 200
    config_response = client.get("/api/config")
    assert "automation_api_token_hash" not in config_response.json()["secrets_set"]
    assert client.get("/api/automation/status", headers=headers).status_code == 401


def test_automation_status_requires_dedicated_token_even_when_ui_auth_disabled(client):
    response = client.get("/api/automation/status")

    assert response.status_code == 401


def test_automation_status_rejects_invalid_token(client):
    _automation_headers(client)

    response = client.get(
        "/api/automation/status",
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert response.status_code == 401


def test_automation_status_accepts_generated_token(client):
    headers, _ = _automation_headers(client)

    response = client.get("/api/automation/status", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "is_processing" in data
    assert "automation_running" in data
    assert "current_doc_id" not in data


def test_status_is_also_reachable_under_the_process_prefix(client):
    """Start and stop live under /process/, so that is where people look for status.

    Guessing it used to land on a 404 whose JSON body reads like a valid reply, which
    left at least one Home Assistant sensor reporting "idle" indefinitely (#42).
    """
    headers, _ = _automation_headers(client)

    canonical = client.get("/api/automation/status", headers=headers)
    guessed = client.get("/api/automation/process/status", headers=headers)

    assert guessed.status_code == 200
    assert guessed.json().keys() == canonical.json().keys()
    assert guessed.json()["is_processing"] == canonical.json()["is_processing"]


def test_the_alias_is_behind_the_same_token(client):
    """Whatever the canonical path answers unauthenticated, the alias answers too."""
    canonical = client.get("/api/automation/status")
    guessed = client.get("/api/automation/process/status")

    assert canonical.status_code == 401
    assert guessed.status_code == canonical.status_code


def test_only_the_documented_status_path_is_in_the_schema(client):
    paths = client.get("/openapi.json").json()["paths"]

    assert "/api/automation/status" in paths
    assert "/api/automation/process/status" not in paths


def test_automation_status_reports_active_documents_with_runtime(client):
    headers, _ = _automation_headers(client)
    scheduler_service._set_processing()
    scheduler_service.mark_document_started(
        1048,
        trigger_tags=["ai-ocr", "force_ocr"],
        trigger_mode="ai-ocr",
        active_step="ocr",
    )

    try:
        response = client.get("/api/automation/status", headers=headers)
    finally:
        scheduler_service._clear_processing()

    assert response.status_code == 200
    data = response.json()
    assert data["is_processing"] is True
    assert data["current_document_ids"] == [1048]
    assert "current_doc_id" not in data
    assert data["started_at"]
    assert data["running_seconds"] >= 0

    active_document = data["active_documents"][0]
    assert active_document["document_id"] == 1048
    assert active_document["trigger_tags"] == ["ai-ocr", "force_ocr"]
    assert active_document["trigger_mode"] == "ai-ocr"
    assert active_document["active_step"] == "ocr"
    assert active_document["running_seconds"] >= 0


def test_processing_state_tracks_multiple_active_documents():
    scheduler_service._set_processing()
    scheduler_service.mark_document_started(
        101,
        trigger_tags=["ai-ocr"],
        trigger_mode="ai-ocr",
    )
    scheduler_service.mark_document_started(
        102,
        trigger_tags=["ai-process"],
        trigger_mode="ai-process",
    )

    try:
        state = scheduler_service.get_processing_state()
        assert state["current_document_ids"] == [101, 102]
        assert "current_doc_id" not in state

        scheduler_service.mark_document_finished(101)
        state = scheduler_service.get_processing_state()
        assert state["current_document_ids"] == [102]
        assert "current_doc_id" not in state
    finally:
        scheduler_service._clear_processing()


def test_automation_start_preserves_previous_last_result(client, monkeypatch):
    from app.services import automation as automation_service

    last_completed_result = {
        "success": True,
        "status": "completed",
        "processed": 1,
        "failed": 0,
        "results": [{"document_id": 7, "success": True}],
    }
    automation_service._last_result = last_completed_result

    async def slow_legacy_processing():
        import asyncio

        await asyncio.sleep(1)
        return {"success": True, "processed": 0, "failed": 0, "results": []}

    async def skipped_modular_processing():
        return {"success": True, "processed": 0, "failed": 0, "results": []}

    monkeypatch.setattr(
        automation_service, "process_tagged_documents", slow_legacy_processing
    )
    monkeypatch.setattr(
        automation_service,
        "process_modular_tagged_documents",
        skipped_modular_processing,
    )
    headers, _ = _automation_headers(client)

    try:
        start_response = client.post("/api/automation/process/start", headers=headers)
        status_response = client.get("/api/automation/status", headers=headers)
    finally:
        client.post("/api/automation/process/stop", headers=headers)
        scheduler_service._clear_processing()
        automation_service._last_result = None

    assert start_response.status_code == 200
    data = status_response.json()
    assert data["last_result"] == last_completed_result
    assert "previous_result" not in data


@pytest.mark.asyncio
async def test_automation_last_result_omits_proposed_changes(monkeypatch):
    from app.services import automation as automation_service

    async def legacy_processing():
        return {
            "success": True,
            "processed": 1,
            "failed": 0,
            "results": [
                {
                    "success": True,
                    "document_id": 42,
                    "title": "Large tutorial",
                    "proposed_changes": {
                        "content": "large text " * 1000,
                        "custom_fields": [
                            {"id": 1, "name": "Topic", "value": "Automation"}
                        ],
                    },
                    "processing_time_ms": 123,
                }
            ],
        }

    async def skipped_modular_processing():
        return {"success": True, "processed": 0, "failed": 0, "results": []}

    monkeypatch.setattr(
        automation_service, "process_tagged_documents", legacy_processing
    )
    monkeypatch.setattr(
        automation_service,
        "process_modular_tagged_documents",
        skipped_modular_processing,
    )

    try:
        await automation_service._run_process_all()
        status = automation_service.get_automation_status()
    finally:
        scheduler_service._clear_processing()
        automation_service._last_result = None

    result = status["last_result"]["results"][0]
    assert result["document_id"] == 42
    assert result["title"] == "Large tutorial"
    assert result["processing_time_ms"] == 123
    assert "proposed_changes" not in result


@pytest.mark.asyncio
async def test_automation_last_result_survives_service_restart(monkeypatch, tmp_path):
    from app.services import automation as automation_service

    async def legacy_processing():
        return {
            "success": True,
            "processed": 1,
            "failed": 0,
            "results": [{"success": True, "document_id": 99}],
        }

    async def skipped_modular_processing():
        return {"success": True, "processed": 0, "failed": 0, "results": []}

    monkeypatch.setattr(
        automation_service, "process_tagged_documents", legacy_processing
    )
    monkeypatch.setattr(
        automation_service,
        "process_modular_tagged_documents",
        skipped_modular_processing,
    )
    monkeypatch.setattr(
        automation_service,
        "LAST_RESULT_FILE",
        str(tmp_path / "automation_last_result.json"),
        raising=False,
    )

    try:
        await automation_service._run_process_all()
        automation_service._last_result = None
        status = automation_service.get_automation_status()
    finally:
        scheduler_service._clear_processing()
        automation_service._last_result = None

    assert status["last_result"] == {
        "success": True,
        "status": "completed",
        "processed": 1,
        "failed": 0,
        "results": [{"success": True, "document_id": 99}],
    }


def test_automation_api_calls_are_logged_without_token(client, caplog):
    headers, token = _automation_headers(client)
    caplog.set_level(logging.INFO, logger="app.routers.automation")

    client.get("/api/automation/status", headers=headers)
    client.post("/api/automation/process/stop", headers=headers)
    scheduler_service._set_processing(7)
    try:
        client.post("/api/automation/process/start", headers=headers)
    finally:
        scheduler_service._clear_processing()

    log_text = caplog.text
    assert "Automation API status requested" in log_text
    assert "Automation API stop requested" in log_text
    assert "Automation API start requested" in log_text
    assert token not in log_text


def test_automation_start_is_idempotent_when_processing_is_already_running(client):
    headers, _ = _automation_headers(client)
    scheduler_service._set_processing(7)

    try:
        response = client.post("/api/automation/process/start", headers=headers)
    finally:
        scheduler_service._clear_processing()

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["status"] == "already_running"
    assert "Already processing document #7" in data["message"]


def test_automation_start_returns_started_for_valid_token(client, monkeypatch):
    from app.services import automation as automation_service

    async def slow_legacy_processing():
        import asyncio

        await asyncio.sleep(1)
        return {"success": True, "processed": 0, "failed": 0, "results": []}

    async def skipped_modular_processing():
        return {"success": True, "processed": 0, "failed": 0, "results": []}

    monkeypatch.setattr(
        automation_service, "process_tagged_documents", slow_legacy_processing
    )
    monkeypatch.setattr(
        automation_service,
        "process_modular_tagged_documents",
        skipped_modular_processing,
    )
    headers, _ = _automation_headers(client)

    try:
        response = client.post("/api/automation/process/start", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["status"] == "started"
    finally:
        client.post("/api/automation/process/stop", headers=headers)
        scheduler_service._clear_processing()


def test_automation_stop_without_running_task_is_idempotent(client):
    headers, _ = _automation_headers(client)

    response = client.post("/api/automation/process/stop", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["status"] == "not_running"
