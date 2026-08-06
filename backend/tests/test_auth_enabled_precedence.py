"""Precedence between the AUTH_ENABLED env var and the UI setting (issue #39).

Reported symptom: enabling "Anmeldung erforderlich" in the UI was persisted and
reported back as true, but every endpoint kept answering without a token. Cause:
when AUTH_ENABLED was set at all, the database was never consulted — so a
docker-compose carrying AUTH_ENABLED=false silently disarmed the UI switch.

Rule: the UI setting decides, except that an explicit AUTH_ENABLED=true keeps
auth on so protection can never be lost by a stray click.
"""

import os
from unittest.mock import patch

import pytest
from sqlmodel import select

from app.auth import _is_auth_enabled
from app.database import get_session
from app.models import Config


def _set_ui_value(value: str | None) -> None:
    with get_session() as session:
        row = session.exec(select(Config).where(Config.key == "auth_enabled")).first()
        if value is None:
            if row:
                session.delete(row)
        elif row:
            row.value = value
        else:
            session.add(Config(key="auth_enabled", value=value))


@pytest.fixture(autouse=True)
def _clean_config():
    yield
    _set_ui_value(None)


def test_ui_switch_wins_over_env_false():
    """The reported bug: AUTH_ENABLED=false must not disarm the UI switch."""
    _set_ui_value("true")
    with patch.dict(os.environ, {"AUTH_ENABLED": "false"}):
        assert _is_auth_enabled() is True


def test_env_true_stays_binding():
    """An operator who forces auth on keeps it on, even if the UI says otherwise."""
    _set_ui_value("false")
    with patch.dict(os.environ, {"AUTH_ENABLED": "true"}):
        assert _is_auth_enabled() is True


def test_ui_switch_decides_when_env_is_unset():
    _set_ui_value("true")
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("AUTH_ENABLED", None)
        assert _is_auth_enabled() is True

    _set_ui_value("false")
    assert _is_auth_enabled() is False


def test_env_false_without_ui_value_stays_off():
    _set_ui_value(None)
    with patch.dict(os.environ, {"AUTH_ENABLED": "false"}):
        assert _is_auth_enabled() is False


def test_defaults_to_off_when_nothing_is_configured():
    _set_ui_value(None)
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("AUTH_ENABLED", None)
        assert _is_auth_enabled() is False
