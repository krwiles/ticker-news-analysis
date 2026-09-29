"""Tests for rate_limit.py's Finnhub budget and per-ticker cooldown -- see docs/adr/0018-*.md.

A real in-memory fake, not canned responses -- incr/get/set behave like real Redis well enough
to test against directly (same choice test_auth.py's _FakeRedis makes). `now` is always passed
in, never read internally, matching recent_headlines_cutoff's own testable-purity style."""

from datetime import datetime, timedelta, timezone

from fakes import FakeRedisKV
from ticker_backend.rate_limit import (
    FETCH_COOLDOWN_SECONDS,
    FINNHUB_RATE_LIMIT_PER_MINUTE,
    record_finnhub_fetch,
    should_defer_fetch,
)


async def test_first_check_for_a_ticker_never_defers():
    # Arrange: nothing recorded yet for this ticker or this window.
    redis = FakeRedisKV()
    now = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)

    # Act.
    should_defer, defer_by = await should_defer_fetch(redis, "AAPL", now)

    # Assert: nothing to defer for -- runs now.
    assert should_defer is False
    assert defer_by == 0.0


async def test_defers_when_the_shared_window_is_at_capacity():
    # Arrange: the shared Finnhub window already has 60 recorded calls this minute.
    redis = FakeRedisKV()
    now = datetime(2026, 9, 29, 12, 0, 10, tzinfo=timezone.utc)
    for _ in range(FINNHUB_RATE_LIMIT_PER_MINUTE):
        await record_finnhub_fetch(redis, "MSFT", now)

    # Act: a different ticker, still gated by the shared budget.
    should_defer, defer_by = await should_defer_fetch(redis, "AAPL", now)

    # Assert: deferred until roughly the next minute boundary (50s left in this one).
    assert should_defer is True
    assert 49 <= defer_by <= 50


async def test_a_fresh_window_is_not_capped_by_the_previous_one():
    # Arrange: the window a minute ago was maxed out.
    redis = FakeRedisKV()
    earlier = datetime(2026, 9, 29, 12, 0, 30, tzinfo=timezone.utc)
    for _ in range(FINNHUB_RATE_LIMIT_PER_MINUTE):
        await record_finnhub_fetch(redis, "MSFT", earlier)

    # Act: check a minute later, a new window.
    now = earlier + timedelta(minutes=1)
    should_defer, defer_by = await should_defer_fetch(redis, "AAPL", now)

    # Assert: the new window starts uncounted.
    assert should_defer is False
    assert defer_by == 0.0


async def test_defers_a_ticker_fetched_too_recently_even_with_budget_free():
    # Arrange: AAPL was just fetched a second ago; the shared window has plenty of room.
    redis = FakeRedisKV()
    now = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
    await record_finnhub_fetch(redis, "AAPL", now)

    # Act: check again one second later.
    should_defer, defer_by = await should_defer_fetch(redis, "AAPL", now + timedelta(seconds=1))

    # Assert: deferred by roughly the remaining cooldown, not the shared budget.
    assert should_defer is True
    assert (FETCH_COOLDOWN_SECONDS - 2) <= defer_by <= (FETCH_COOLDOWN_SECONDS - 1)


async def test_cooldown_expiring_lets_the_ticker_run_again():
    # Arrange: AAPL was fetched exactly at the cooldown boundary.
    redis = FakeRedisKV()
    now = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
    await record_finnhub_fetch(redis, "AAPL", now)

    # Act: check right as the cooldown has fully elapsed.
    should_defer, defer_by = await should_defer_fetch(
        redis, "AAPL", now + timedelta(seconds=FETCH_COOLDOWN_SECONDS)
    )

    # Assert: no longer on cooldown.
    assert should_defer is False
    assert defer_by == 0.0


async def test_one_tickers_calls_dont_affect_another_tickers_cooldown():
    # Arrange: AAPL fetched just now; MSFT has never been fetched.
    redis = FakeRedisKV()
    now = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
    await record_finnhub_fetch(redis, "AAPL", now)

    # Act: MSFT is checked a second later.
    should_defer, defer_by = await should_defer_fetch(redis, "MSFT", now + timedelta(seconds=1))

    # Assert: MSFT's own cooldown is untouched by AAPL's recent fetch.
    assert should_defer is False
    assert defer_by == 0.0
