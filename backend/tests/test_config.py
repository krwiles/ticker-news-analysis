"""Tests for config.py's own pure helpers -- see docs/plans/0039-*.md for recent_headlines_cutoff.
derive_sentiment_enum's tests currently live in test_providers.py (a leftover from before lesson 28
moved that function out of providers.py) -- this file is the properly-named home for what belongs
here, not a relocation of those."""

from datetime import datetime, timezone

from ticker_backend.config import recent_headlines_cutoff


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
