"""create_app()'s fail-fast secret check -- see docs/plans/0040-*.md and ADR 0017."""

import pytest

from ticker_backend.config import settings
from ticker_backend.main import create_app


def test_create_app_in_api_mode_refuses_to_start_without_the_db_password(monkeypatch):
    # Arrange: api mode with the Postgres password missing.
    monkeypatch.setattr(settings, "app_mode", "api")
    monkeypatch.setattr(settings, "postgres_password", "")

    # Act + Assert: a clear startup error naming the secret, not a later opaque auth failure.
    with pytest.raises(RuntimeError, match="postgres_password"):
        create_app()


def test_create_app_in_ui_mode_needs_no_secrets(monkeypatch, tmp_path):
    # Arrange: ui mode holds no secrets at all; a throwaway static dir stands in for the built SPA.
    monkeypatch.setattr("ticker_backend.main.STATIC_DIR", tmp_path)
    monkeypatch.setattr(settings, "app_mode", "ui")
    monkeypatch.setattr(settings, "postgres_password", "")

    # Act + Assert: builds fine.
    assert create_app() is not None
