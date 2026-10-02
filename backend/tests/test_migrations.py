"""Migration safety tests, especially upgrading pre-Alembic databases.

Regression guard for the bug where run_migrations() stamped an existing
pre-Alembic database to head, skipping the column-adding migrations and leaving
the schema missing `prompts.sample_key` etc.
"""

import sqlite3

from sqlalchemy import create_engine, inspect

from app.database import run_migrations


def _columns(db_path: str, table: str) -> set[str]:
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        return {c["name"] for c in inspect(engine).get_columns(table)}
    finally:
        engine.dispose()


def _old_prompts_schema(db_path: str) -> None:
    """Simulate a pre-Alembic DB (no alembic_version) with the OLD prompts schema
    that lacks the sample_* columns."""
    con = sqlite3.connect(db_path)
    con.executescript(
        """
        CREATE TABLE prompts (
            id INTEGER PRIMARY KEY, name VARCHAR, prompt_type VARCHAR,
            document_type_filter VARCHAR, system_prompt VARCHAR, user_template VARCHAR,
            is_active BOOLEAN, created_at DATETIME, updated_at DATETIME
        );
        CREATE TABLE config (
            id INTEGER PRIMARY KEY, key VARCHAR, value VARCHAR,
            description VARCHAR, updated_at DATETIME
        );
        CREATE TABLE processing_logs (
            id INTEGER PRIMARY KEY, document_id INTEGER, status VARCHAR, processed_at DATETIME
        );
        """
    )
    con.commit()
    con.close()


def test_old_pre_alembic_db_gets_missing_columns(tmp_path):
    db = tmp_path / "old.db"
    _old_prompts_schema(str(db))
    run_migrations(f"sqlite:///{db}")
    assert {"sample_key", "sample_hash", "sample_updated_at"} <= _columns(str(db), "prompts")
    # The previously-crashing query must now succeed.
    con = sqlite3.connect(str(db))
    try:
        con.execute("SELECT sample_key FROM prompts").fetchall()
    finally:
        con.close()


def test_current_schema_pre_alembic_db_is_idempotent(tmp_path):
    # A pre-Alembic DB that ALREADY has the sample columns + indexes must not error.
    db = tmp_path / "cur.db"
    con = sqlite3.connect(str(db))
    con.executescript(
        """
        CREATE TABLE prompts (
            id INTEGER PRIMARY KEY, name VARCHAR, prompt_type VARCHAR,
            document_type_filter VARCHAR, system_prompt VARCHAR, user_template VARCHAR,
            is_active BOOLEAN, sample_key VARCHAR, sample_hash VARCHAR,
            sample_updated_at DATETIME, created_at DATETIME, updated_at DATETIME
        );
        CREATE INDEX ix_prompts_sample_key ON prompts (sample_key);
        CREATE TABLE config (id INTEGER PRIMARY KEY, key VARCHAR, value VARCHAR);
        CREATE TABLE processing_logs (
            id INTEGER PRIMARY KEY, document_id INTEGER, status VARCHAR, processed_at DATETIME
        );
        CREATE INDEX ix_log_document_id ON processing_logs (document_id);
        CREATE INDEX ix_log_status ON processing_logs (status);
        CREATE INDEX ix_log_processed_at ON processing_logs (processed_at);
        """
    )
    con.commit()
    con.close()
    run_migrations(f"sqlite:///{db}")  # must not raise on already-present columns/indexes
    assert {"sample_key", "sample_hash", "sample_updated_at"} <= _columns(str(db), "prompts")


def test_fresh_empty_db_migrates_from_scratch(tmp_path):
    db = tmp_path / "fresh.db"
    run_migrations(f"sqlite:///{db}")
    assert {"sample_key", "sample_hash", "sample_updated_at"} <= _columns(str(db), "prompts")



def test_migrations_switch_the_app_loggers_back_on_and_no_others(tmp_path):
    """Startup runs the migrations; a step's warnings must still be logged afterwards."""
    import logging

    step_logger = logging.getLogger("app.services.steps.fields_step")
    sql_logger = logging.getLogger("aiosqlite")
    step_logger.disabled = sql_logger.disabled = False
    run_migrations(f"sqlite:///{tmp_path / 'log.db'}")
    assert step_logger.disabled is False
    # aiosqlite prints SQL parameters at DEBUG, saved API keys included.
    assert sql_logger.disabled is True
