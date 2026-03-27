import logging
from fastapi import APIRouter, HTTPException, Depends, Body
from sqlmodel import select, Session
from typing import Optional
from datetime import datetime
import httpx
from pydantic import BaseModel

from ..database import get_db, get_session
from ..models import Config
from ..services.log_stream import apply_log_level


class ConfigUpdate(BaseModel):
    key: str
    value: str


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])


async def get_llm_config():
    """Get LLM configuration from database."""
    with get_session() as session:

        def _get(key: str, default: str = "") -> str:
            stmt = select(Config).where(Config.key == key)
            c = session.exec(stmt).first()
            return c.value if c and c.value else default

        provider = _get("llm_provider", "ollama")
        api_base = _get("llm_api_base")
        model = _get("llm_model", "llama3")
        api_key = _get("llm_api_key")
        enable_vision = _get("enable_vision", "false").lower() == "true"
        provider_vision = _get("llm_provider_vision", "ollama")
        api_base_vision = _get("llm_api_base_vision")
        api_key_vision = _get("llm_api_key_vision")

        return {
            "provider": provider,
            "api_base": api_base,
            "model": model,
            "api_key": api_key,
            "enable_vision": enable_vision,
            "provider_vision": provider_vision,
            "api_base_vision": api_base_vision,
            "api_key_vision": api_key_vision,
        }


async def test_ollama_url(api_base: str) -> dict:
    """Test a single Ollama URL."""
    try:
        logger.debug(f"[Test Ollama] Testing connection to: {api_base}/api/tags")

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{api_base}/api/tags")

            if response.status_code < 400:
                data = response.json()
                models = data.get("models", [])
                logger.debug(f"[Test Ollama] Success! Found {len(models)} models")
                return {
                    "success": True,
                    "message": f"Connected! Found {len(models)} models.",
                    "models": [m.get("name") for m in models[:10]],
                }
            else:
                logger.error(f"[Test Ollama] Error: status {response.status_code}")
                return {"success": False, "message": f"Status {response.status_code}"}
    except httpx.ConnectError as e:
        logger.error(f"[Test Ollama] Connection error: {e}")
        return {"success": False, "message": f"Cannot connect: {str(e)}"}
    except Exception as e:
        logger.error(f"[Test Ollama] Error: {e}")
        return {"success": False, "message": f"Error: {str(e)}"}


async def test_openai_url(api_base: str, api_key: str) -> dict:
    """Test an OpenAI-compatible endpoint."""
    try:
        logger.debug(f"[Test OpenAI] Testing connection to: {api_base}/models")

        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{api_base}/models", headers=headers)

            if response.status_code == 401:
                return {
                    "success": False,
                    "message": "Authentication failed — check your API key",
                }
            elif response.status_code < 400:
                data = response.json()
                models = [m.get("id") for m in data.get("data", [])[:5]]
                logger.debug(f"[Test OpenAI] Success! Models: {models}")
                return {
                    "success": True,
                    "message": f"Connected! Models: {', '.join(models)}"
                    if models
                    else "Connected!",
                    "models": models,
                }
            else:
                return {"success": False, "message": f"Status {response.status_code}"}
    except httpx.ConnectError as e:
        logger.error(f"[Test OpenAI] Connection error: {e}")
        return {"success": False, "message": f"Cannot connect: {str(e)}"}
    except Exception as e:
        logger.error(f"[Test OpenAI] Error: {e}")
        return {"success": False, "message": f"Error: {str(e)}"}


@router.post("/test-ollama")
async def test_ollama_connection():
    """Test LLM connection(s) from backend."""
    config = await get_llm_config()

    # Test main LLM
    if config["provider"] in ("openai", "grok"):
        main_result = await test_openai_url(config["api_base"], config["api_key"])
    else:
        main_result = await test_ollama_url(config["api_base"])

    result = {
        "success": main_result["success"],
        "main": main_result,
    }

    # Test vision LLM if enabled
    if config["enable_vision"]:
        if config["provider_vision"] in ("openai", "grok"):
            vision_result = await test_openai_url(
                config["api_base_vision"], config["api_key_vision"]
            )
        else:
            logger.debug(f"[Test] Vision enabled, testing: {config['api_base_vision']}")
            vision_result = await test_ollama_url(config["api_base_vision"])
        result["vision"] = vision_result
        result["success"] = main_result["success"] and vision_result["success"]
    else:
        result["vision"] = None

    return result


@router.get("")
async def get_configs():
    with get_session() as session:
        stmt = select(Config)
        configs = session.exec(stmt).all()
        return {c.key: c.value for c in configs}


@router.get("/{key}")
async def get_config(key: str):
    with get_session() as session:
        stmt = select(Config).where(Config.key == key)
        config = session.exec(stmt).first()
        if not config:
            raise HTTPException(status_code=404, detail="Config not found")
        return {"key": config.key, "value": config.value}


@router.post("")
async def set_config(data: ConfigUpdate = Body(...), description: Optional[str] = None):
    with get_session() as session:
        stmt = select(Config).where(Config.key == data.key)
        config = session.exec(stmt).first()

        if config:
            config.value = data.value
            config.description = description
            config.updated_at = datetime.utcnow()
        else:
            config = Config(key=data.key, value=data.value, description=description)
            session.add(config)

        if data.key == "log_level":
            apply_log_level(data.value)

        return {"key": data.key, "value": data.value}


@router.delete("/{key}")
async def delete_config(key: str):
    with get_session() as session:
        stmt = select(Config).where(Config.key == key)
        config = session.exec(stmt).first()
        if not config:
            raise HTTPException(status_code=404, detail="Config not found")
        session.delete(config)
        return {"message": "Config deleted"}
