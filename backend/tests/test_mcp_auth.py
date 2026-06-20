import pytest
from app.mcp.auth import AissistTokenVerifier
from app.auth import hash_automation_token

@pytest.mark.asyncio
async def test_verify_token_accepts_matching_paia_token(monkeypatch):
    token = "paia_secret"
    verifier = AissistTokenVerifier()
    monkeypatch.setattr(
        "app.mcp.auth._get_automation_token_hash",
        lambda: hash_automation_token(token),
    )
    result = await verifier.verify_token(token)
    assert result is not None

@pytest.mark.asyncio
async def test_verify_token_rejects_wrong_token(monkeypatch):
    verifier = AissistTokenVerifier()
    monkeypatch.setattr(
        "app.mcp.auth._get_automation_token_hash",
        lambda: hash_automation_token("paia_correct"),
    )
    assert await verifier.verify_token("paia_wrong") is None

@pytest.mark.asyncio
async def test_verify_token_rejects_when_unconfigured(monkeypatch):
    verifier = AissistTokenVerifier()
    monkeypatch.setattr("app.mcp.auth._get_automation_token_hash", lambda: "")
    assert await verifier.verify_token("paia_anything") is None
