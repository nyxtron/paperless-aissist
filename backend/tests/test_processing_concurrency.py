"""Configurable parallel processing limit (issue #36)."""

import pytest
from sqlmodel import select

from app.database import get_session
from app.models import Config
from app.services.config_cache import ConfigCache
from app.services.scheduler import get_max_concurrent_processing


async def _set_limit(value: str | None) -> None:
    with get_session() as session:
        stmt = select(Config).where(Config.key == "max_concurrent_processing")
        row = session.exec(stmt).first()
        if value is None:
            if row:
                session.delete(row)
        elif row:
            row.value = value
        else:
            session.add(Config(key="max_concurrent_processing", value=value))
    await (await ConfigCache.get_instance()).invalidate()


@pytest.mark.asyncio
async def test_defaults_to_three_when_unset():
    await _set_limit(None)
    assert await get_max_concurrent_processing() == 3


@pytest.mark.asyncio
async def test_reads_configured_value():
    await _set_limit("1")
    assert await get_max_concurrent_processing() == 1
    await _set_limit("8")
    assert await get_max_concurrent_processing() == 8
    await _set_limit(None)


@pytest.mark.asyncio
async def test_clamps_to_minimum_of_one():
    await _set_limit("0")
    assert await get_max_concurrent_processing() == 1
    await _set_limit("-2")
    assert await get_max_concurrent_processing() == 1
    await _set_limit(None)


@pytest.mark.asyncio
async def test_falls_back_on_invalid_value():
    await _set_limit("many")
    assert await get_max_concurrent_processing() == 3
    await _set_limit(None)
