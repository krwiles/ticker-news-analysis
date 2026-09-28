"""Tests for config.py's own pure helpers -- see docs/plans/0039-*.md for recent_headlines_cutoff.
derive_sentiment_enum's tests currently live in test_providers.py (a leftover from before lesson 28
moved that function out of providers.py) -- this file is the properly-named home for what belongs
here, not a relocation of those."""

from datetime import datetime, timezone

import pytest

from ticker_backend.config import Settings, recent_headlines_cutoff, require_secrets


def test_cutoff_is_midnight_utc_of_the_oldest_included_day():
    # Arrange: a "now" partway through a day, well past midnight.
    now = datetime(2026, 9, 27, 16, 50, tzinfo=timezone.utc)

    # Act.
    cutoff = recent_headlines_cutoff(now)

    # Assert: the start of the day 7 days before "now"'s own date, not now - 7 days exactly.
    assert cutoff == datetime(2026, 9, 20, 0, 0, tzinfo=timezone.utc)


def test_includes_a_headline_finnhub_fetched_that_an_exact_instant_cutoff_would_have_excluded():
    # Arrange: the exact regression case -- Finnhub's day-granularity fetch just pulled in a
    # headline from early on the oldest included day, hours before the exact instant 7 days ago.
    now = datetime(2026, 9, 27, 16, 50, tzinfo=timezone.utc)
    headline_published_at = datetime(2026, 9, 20, 0, 5, tzinfo=timezone.utc)

    # Act.
    cutoff = recent_headlines_cutoff(now)

    # Assert: included -- an exact `now - RECENT_HEADLINES_WINDOW` cutoff would have excluded this
    # (2026-09-20T16:50 > 2026-09-20T00:05), permanently stranding it from ever being scored.
    assert headline_published_at >= cutoff


def test_excludes_a_headline_from_the_day_before_the_oldest_included_day():
    # Arrange: one day older than the window's oldest included day.
    now = datetime(2026, 9, 27, 16, 50, tzinfo=timezone.utc)
    headline_published_at = datetime(2026, 9, 19, 23, 59, tzinfo=timezone.utc)

    # Act.
    cutoff = recent_headlines_cutoff(now)

    # Assert: still excluded -- the fix widens the window by at most a day, not unboundedly.
    assert headline_published_at < cutoff


# ---- secrets (docs/plans/0040-*.md, ADR 0017) ----


@pytest.fixture(autouse=True)
def _no_ambient_secrets(monkeypatch):
    # conftest.py seeds POSTGRES_PASSWORD for the rest of the suite -- these tests need a clean slate.
    for name in ("POSTGRES_PASSWORD", "FINNHUB_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def _settings(tmp_path, **overrides):
    # _env_file=None ignores any real .env; _secrets_dir points at a throwaway dir, never /run/secrets.
    return Settings(_env_file=None, _secrets_dir=tmp_path, **overrides)


def test_secret_is_read_from_a_file_named_after_the_field(tmp_path):
    # Arrange: a secrets dir holding one file, with the trailing newline editors add.
    (tmp_path / "finnhub_api_key").write_text("file-value\n")

    # Act.
    cfg = _settings(tmp_path)

    # Assert: the value is read from the file, whitespace stripped.
    assert cfg.finnhub_api_key == "file-value"


def test_an_env_var_silently_outranks_the_secrets_file(tmp_path, monkeypatch):
    # Arrange: the same secret set in both places.
    (tmp_path / "finnhub_api_key").write_text("file-value")
    monkeypatch.setenv("FINNHUB_API_KEY", "env-value")

    # Act.
    cfg = _settings(tmp_path)

    # Assert: env wins -- why scripts/init-secrets.sh --from-env strips keys out of .env.
    assert cfg.finnhub_api_key == "env-value"


def test_database_url_is_built_from_parts_with_the_password_escaped(tmp_path):
    # Arrange: a password full of characters that would corrupt a hand-concatenated URL.
    (tmp_path / "postgres_password").write_text("p@ss:/w#rd")

    # Act.
    url = _settings(tmp_path).database_url

    # Assert: the parsed password round-trips, and the rendered string has it percent-encoded.
    assert url.password == "p@ss:/w#rd"
    assert "p%40ss%3A%2Fw%23rd" in url.render_as_string(hide_password=False)


def test_api_mode_requires_the_postgres_password(tmp_path):
    # Arrange: api mode with no secrets present at all.
    cfg = _settings(tmp_path, app_mode="api")

    # Act + Assert: fails fast, naming the missing secret and the fix -- never its value.
    with pytest.raises(RuntimeError, match="postgres_password.*init-secrets"):
        require_secrets(cfg)


def test_worker_mode_requires_the_finnhub_key_too(tmp_path):
    # Arrange: worker mode with the DB password but no Finnhub key.
    (tmp_path / "postgres_password").write_text("pw")
    cfg = _settings(tmp_path, app_mode="worker")

    # Act + Assert.
    with pytest.raises(RuntimeError, match="finnhub_api_key"):
        require_secrets(cfg)


def test_openai_key_stays_optional_and_ui_needs_nothing(tmp_path):
    # Arrange: worker with both required secrets but no OpenAI key (spec 0005's designed degradation).
    (tmp_path / "postgres_password").write_text("pw")
    (tmp_path / "finnhub_api_key").write_text("key")

    # Act + Assert: neither worker-without-OpenAI nor bare ui raises.
    require_secrets(_settings(tmp_path, app_mode="worker"))
    empty = tmp_path / "empty"
    empty.mkdir()
    require_secrets(_settings(empty, app_mode="ui"))
