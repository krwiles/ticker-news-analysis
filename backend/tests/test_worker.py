"""Tests for worker.py's thin ARQ wrappers -- see docs/plans/0036-*.md. No dedicated tests
existed for these before; fetch_headlines_job gained real logic (triggering sentiment) worth
covering directly, rather than only through the framework-agnostic functions it wraps."""

from ticker_backend.worker import fetch_headlines_job


async def test_fetch_headlines_job_triggers_sentiment_after_fetch_finishes(monkeypatch):
    """Plan 0036: sentiment must start only once this job's own fetch+grouping is truly done --
    triggered from here, not from search(), which can't know when a background-run job finishes."""
    calls = []

    async def fake_fetch_and_persist_headlines(ticker):
        # Arrange: records that the real fetch ran, before sentiment is ever triggered.
        calls.append(("fetch", ticker))
        return {"status": "success", "providers": {}, "grouping": "ok"}

    async def fake_enqueue_sentiment_after_fetch(redis, ticker, session_factory=None):
        # Arrange: records the exact redis handle and ticker sentiment triggering received.
        calls.append(("sentiment", redis, ticker))

    monkeypatch.setattr("ticker_backend.worker.fetch_and_persist_headlines", fake_fetch_and_persist_headlines)
    monkeypatch.setattr("ticker_backend.worker.enqueue_sentiment_after_fetch", fake_enqueue_sentiment_after_fetch)

    # Act: run the real job wrapper, ARQ's own ctx dict carries the Redis pool under "redis".
    result = await fetch_headlines_job({"redis": "the-real-redis-pool"}, "AAPL")

    # Assert: fetch ran first, sentiment triggered after with the ticker and ctx's redis handle,
    # and the fetch job's own result is returned unchanged.
    assert calls == [("fetch", "AAPL"), ("sentiment", "the-real-redis-pool", "AAPL")]
    assert result == {"status": "success", "providers": {}, "grouping": "ok"}
