"""Unit tests for build_daily_view -- no DB, no network. Headline objects
are constructed in memory, never persisted; `now` is always passed in
explicitly, exactly what makes this testable without waiting for real
midnight (see search.py's own docstring)."""

from datetime import datetime, timezone
from uuid import uuid4

from ticker_backend.models import Headline, Story
from ticker_backend.search import build_daily_view


def _headline(
    published_at: datetime, title: str = "t", story_id=None, sentiment_score=None, sentiment_status=None
) -> Headline:
    return Headline(
        id=uuid4(),
        ticker="AAPL",
        title=title,
        url=f"https://example.com/{title}",
        category="news",
        provider="finnhub",
        published_at=published_at,
        story_id=story_id,
        sentiment_score=sentiment_score,
        sentiment_gloss="bullish" if sentiment_score is not None else None,
        sentiment_rationale="Real rationale." if sentiment_score is not None else None,
        sentiment_status=sentiment_status,
    )


def _story(sentiment_average=None, sentiment_score_count=0) -> Story:
    return Story(id=uuid4(), ticker="AAPL", sentiment_average=sentiment_average, sentiment_score_count=sentiment_score_count)


def _only_day(days: list[dict]) -> dict:
    assert len(days) == 1, f"expected exactly one day entry, got {[d['date'] for d in days]}"
    return days[0]


def test_same_eastern_day_lands_in_todays_entry():
    now = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)  # 11:00 EDT
    h = _headline(datetime(2026, 9, 10, 23, 30, tzinfo=timezone.utc))  # 19:30 EDT, same day
    day = _only_day(build_daily_view([h], now))
    assert day["is_today"] and len(day["stories"]) == 1


def test_utc_past_midnight_still_eastern_yesterday():
    """The exact boundary spec 0001's Success Criteria names: a UTC
    timestamp just after UTC midnight can still be "yesterday" in Eastern
    time, during EDT (UTC-4)."""
    now = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)  # Eastern "today" = Sept 10
    h = _headline(datetime(2026, 9, 11, 3, 30, tzinfo=timezone.utc))  # 23:30 EDT Sept 10 -- still today
    day = _only_day(build_daily_view([h], now))
    assert day["is_today"] and day["date"] == "2026-09-10"


def test_crosses_into_eastern_tomorrow_is_a_separate_day():
    now = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)  # Eastern "today" = Sept 10
    h = _headline(datetime(2026, 9, 11, 4, 30, tzinfo=timezone.utc))  # 00:30 EDT Sept 11 -- tomorrow
    days = build_daily_view([h], now)
    # Today's entry is still always present, alongside the headline's own day.
    assert len(days) == 2
    today_entry = next(d for d in days if d["is_today"])
    other_entry = next(d for d in days if not d["is_today"])
    assert today_entry["stories"] == []
    assert other_entry["date"] == "2026-09-11" and len(other_entry["stories"]) == 1


def test_dst_aware_not_a_hardcoded_offset_winter_est():
    """Genuinely distinguishes EST (-5) from EDT (-4), not just "some
    timezone conversion happened." Under -5: now -> Jan 14 23:30, headline
    -> Jan 14 21:00, same day, matches. Under a wrong -4: now crosses into
    Jan 15, headline doesn't -- a mismatch only the wrong offset produces."""
    now = datetime(2026, 1, 15, 4, 30, tzinfo=timezone.utc)
    h = _headline(datetime(2026, 1, 15, 2, 0, tzinfo=timezone.utc))
    day = _only_day(build_daily_view([h], now))
    assert day["is_today"]


def test_empty_list_still_returns_todays_entry():
    now = datetime.now(timezone.utc)
    day = _only_day(build_daily_view([], now))
    assert day["is_today"] and day["stories"] == []


def test_earlier_empty_days_are_never_emitted():
    """Only Today is always present -- an earlier day with zero Stories
    never gets its own entry (ADR 0013), unlike a rigid 7-day scaffold."""
    now = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)
    h = _headline(datetime(2026, 9, 10, 16, 0, tzinfo=timezone.utc))  # today only
    days = build_daily_view([h], now)
    assert len(days) == 1  # no entries for Sept 4-9 despite being "in the past week"


def test_days_sorted_newest_first():
    now = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)
    today_h = _headline(datetime(2026, 9, 10, 16, 0, tzinfo=timezone.utc))
    older_h = _headline(datetime(2026, 9, 8, 16, 0, tzinfo=timezone.utc), title="older")
    days = build_daily_view([today_h, older_h], now)
    assert [d["date"] for d in days] == ["2026-09-10", "2026-09-08"]


def test_stories_within_a_day_sorted_newest_first():
    now = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)
    older = _headline(datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc), title="older")
    newer = _headline(datetime(2026, 9, 10, 14, 0, tzinfo=timezone.utc), title="newer")
    day = _only_day(build_daily_view([older, newer], now))
    assert [s["primary"]["title"] for s in day["stories"]] == ["newer", "older"]


def test_shared_story_id_groups_into_one_story_with_correct_primary():
    now = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)
    story_id = uuid4()
    first = _headline(datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc), title="first", story_id=story_id)
    second = _headline(datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc), title="second", story_id=story_id)
    day = _only_day(build_daily_view([first, second], now))
    assert len(day["stories"]) == 1
    story = day["stories"][0]
    assert story["story_id"] == str(story_id)
    assert story["primary"]["title"] == "first"  # earliest-published is primary (ADR 0009)
    assert [m["title"] for m in story["other_members"]] == ["second"]


def test_null_story_id_headlines_become_separate_singleton_stories():
    """Grouping skipped/errored (ADR 0012) must never hide a headline or
    merge unrelated ones together -- each null-story headline is its own Story."""
    now = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)
    a = _headline(datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc), title="a", story_id=None)
    b = _headline(datetime(2026, 9, 10, 11, 0, tzinfo=timezone.utc), title="b", story_id=None)
    day = _only_day(build_daily_view([a, b], now))
    assert len(day["stories"]) == 2
    assert all(s["story_id"] is None for s in day["stories"])
    assert all(s["other_members"] == [] for s in day["stories"])


def test_headline_dict_includes_sentiment_fields_when_resolved():
    now = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)
    h = _headline(datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc), sentiment_score=85, sentiment_status="ok")
    day = _only_day(build_daily_view([h], now))
    primary = day["stories"][0]["primary"]
    assert primary["sentiment_score"] == 85
    assert primary["sentiment_gloss"] == "bullish"
    assert primary["sentiment_rationale"] == "Real rationale."
    assert primary["sentiment_status"] == "ok"
    # Derived from the score, not a second independently-set value (spec 0005/ADR 0014).
    assert primary["sentiment_enum"] == "positive"


def test_headline_dict_sentiment_fields_are_null_while_pending():
    now = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)
    h = _headline(datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc))  # no sentiment set at all
    day = _only_day(build_daily_view([h], now))
    primary = day["stories"][0]["primary"]
    assert primary["sentiment_score"] is None
    assert primary["sentiment_status"] is None
    assert primary["sentiment_enum"] is None


def test_story_dict_includes_aggregate_when_present():
    now = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)
    story_id = uuid4()
    first = _headline(datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc), title="first", story_id=story_id)
    second = _headline(datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc), title="second", story_id=story_id)
    stories_by_id = {story_id: _story(sentiment_average=64.0, sentiment_score_count=2)}

    day = _only_day(build_daily_view([first, second], now, stories_by_id))

    story = day["stories"][0]
    assert story["sentiment_average"] == 64.0
    assert story["sentiment_enum"] == "neutral"


def test_story_dict_aggregate_is_null_when_no_member_has_resolved_yet():
    now = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)
    story_id = uuid4()
    first = _headline(datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc), title="first", story_id=story_id)
    second = _headline(datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc), title="second", story_id=story_id)
    # A real Story row exists, but sentiment_score_count is still 0 -- nothing has resolved yet.
    stories_by_id = {story_id: _story(sentiment_average=None, sentiment_score_count=0)}

    day = _only_day(build_daily_view([first, second], now, stories_by_id))

    story = day["stories"][0]
    assert story["sentiment_average"] is None
    assert story["sentiment_enum"] is None


def test_story_dict_aggregate_is_null_when_stories_by_id_not_provided():
    # Existing callers that don't pass stories_by_id at all still get a valid, null aggregate.
    now = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)
    story_id = uuid4()
    h = _headline(datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc), story_id=story_id)
    day = _only_day(build_daily_view([h], now))
    assert day["stories"][0]["sentiment_average"] is None
