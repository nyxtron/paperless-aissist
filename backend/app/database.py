"""SQLite database engine and session management.

Provides both sync and async SQLModel session factories backed by SQLite,
with tables created on startup. The async engine uses aiosqlite.
"""

import os
import pathlib
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator

from sqlmodel import create_engine, Session, SQLModel
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.pool import StaticPool

data_dir = os.environ.get("DATA_DIR", "/app/data")
pathlib.Path(data_dir).mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{data_dir}/paperless-aissist.db"
ASYNC_DATABASE_URL = f"sqlite+aiosqlite:///{data_dir}/paperless-aissist.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


def create_db_and_tables():
    """Create all tables defined by SQLModel metadata."""
    SQLModel.metadata.create_all(engine)


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager providing an AsyncSession.

    Yields:
        An AsyncSession instance that auto-commits on success or rolls back on error.
    """
    async with AsyncSession(async_engine, expire_on_commit=False) as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Sync context manager providing a Session.

    Yields:
        A Session instance that auto-commits on success or rolls back on error.
    """
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def run_migrations() -> None:
    """Run Alembic migrations, stamping existing DBs if needed.

    Detects whether this is an existing database (tables present but no
    alembic_version table) and stamps it as already migrated before running
    any pending migrations.
    """
    import logging
    from alembic.config import Config
    from alembic import command
    from sqlalchemy import inspect

    logger = logging.getLogger(__name__)

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", DATABASE_URL)

    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    if "alembic_version" not in existing_tables and len(existing_tables) > 0:
        logger.info("Existing database detected without Alembic — stamping as migrated")
        command.stamp(alembic_cfg, "head")

    logger.info("Running Alembic migrations...")
    command.upgrade(alembic_cfg, "head")
    logger.info("Migrations complete")
