"""Unit tests for split_today_recent -- no DB, no network. Headline objects
are constructed in memory, never persisted; `now` is always passed in
explicitly, exactly what makes this testable without waiting for real
midnight (see search.py's own docstring)."""

from datetime import datetime, timezone

from ticker_backend.models import Headline
from ticker_backend.search import split_today_recent


def _headline(published_at: datetime, title: str = "t") -> Headline:
    return Headline(
        ticker="AAPL",
        title=title,
        url=f"https://example.com/{title}",
        category="news",
        provider="finnhub",
        published_at=published_at,
    )


def test_same_eastern_day_lands_in_today():
    now = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)  # 11:00 EDT
    h = _headline(datetime(2026, 9, 10, 23, 30, tzinfo=timezone.utc))  # 19:30 EDT, same day
    today, recent = split_today_recent([h], now)
    assert len(today) == 1 and len(recent) == 0


def test_utc_past_midnight_still_eastern_yesterday():
    """The exact boundary spec 0001's Success Criteria names: a UTC
    timestamp just after UTC midnight can still be "yesterday" in Eastern
    time, during EDT (UTC-4)."""
    now = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)  # Eastern "today" = Sept 10
    h = _headline(datetime(2026, 9, 11, 3, 30, tzinfo=timezone.utc))  # 23:30 EDT Sept 10 -- still today
    today, recent = split_today_recent([h], now)
    assert len(today) == 1 and len(recent) == 0


def test_crosses_into_eastern_tomorrow_is_recent_not_today():
    now = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)  # Eastern "today" = Sept 10
    h = _headline(datetime(2026, 9, 11, 4, 30, tzinfo=timezone.utc))  # 00:30 EDT Sept 11 -- tomorrow
    today, recent = split_today_recent([h], now)
    assert len(today) == 0 and len(recent) == 1


def test_dst_aware_not_a_hardcoded_offset_winter_est():
    """Genuinely distinguishes EST (-5) from EDT (-4), not just "some
    timezone conversion happened at all" -- found via the lesson's own
    verify-the-tests step that an earlier version of this test didn't
    actually do this (both timestamps landed on the same date either way).
    Under the correct -5: now -> Jan 14 23:30, headline -> Jan 14 21:00,
    same day, matches. Under a wrong hardcoded -4: now -> Jan 15 00:30
    (crosses into the next day), headline -> Jan 14 22:00 (does not) --
    a real mismatch only the wrong offset would produce."""
    now = datetime(2026, 1, 15, 4, 30, tzinfo=timezone.utc)
    h = _headline(datetime(2026, 1, 15, 2, 0, tzinfo=timezone.utc))
    today, recent = split_today_recent([h], now)
    assert len(today) == 1 and len(recent) == 0


def test_empty_list():
    today, recent = split_today_recent([], datetime.now(timezone.utc))
    assert today == [] and recent == []


def test_sorted_newest_first_within_each_bucket():
    now = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)
    older = _headline(datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc), title="older")
    newer = _headline(datetime(2026, 9, 10, 14, 0, tzinfo=timezone.utc), title="newer")
    today, _ = split_today_recent([older, newer], now)
    assert [entry["title"] for entry in today] == ["newer", "older"]
