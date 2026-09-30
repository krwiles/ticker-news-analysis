"""Integration test for /api/search via httpx's ASGITransport -- no running
server needed. get_arq_redis and get_session_factory are both overridden:
this tests the endpoint's own two-step logic, not lesson 7's real job or a
real Redis connection. See docs/plans/0010-testing-search-feature.md."""

import asyncio
from datetime import datetime, timezone

from httpx import ASGITransport, AsyncClient

from arq.jobs import JobStatus

from fakes import FakeRedisKV

from ticker_backend.auth import SESSION_COOKIE_NAME
from ticker_backend.main import app
from ticker_backend.models import Company, Headline, Story, User, WatchlistEntry
from ticker_backend.search import _compute_sentiment_status, get_arq_redis, get_session_factory


class _FakeJob:
    # Stands in for a real ARQ Job; status defaults to complete since only ADR 0018's new
    # deferred-job test needs to override it.
    def __init__(self, result=None, exc: Exception | None = None, status=JobStatus.complete):
        self._result = result
        self._exc = exc
        self._status = status

    async def result(self, timeout=None):
        if self._exc is not None:
            raise self._exc
        return self._result

    async def status(self):
        return self._status


class _FakeArqRedis(FakeRedisKV):
    # Stands in for a real ArqRedis pool -- records every enqueue_job() call; FakeRedisKV supplies
    # get/set/incr/expire (ADR 0016/0018: the rate-limit gate runs on the same connection).
    def __init__(self, job: _FakeJob):
        super().__init__()
        self._job = job
        self.enqueued_job_names: list[str] = []
        self.enqueued_job_ids: list[str | None] = []

    async def enqueue_job(self, name, *args, _job_id=None, **kwargs):
        self.enqueued_job_names.append(name)
        self.enqueued_job_ids.append(_job_id)
        return self._job


async def _seed_headline(
    session_factory, ticker: str, title: str, url: str, category="news", story_id=None,
    sentiment_score=None, sentiment_status=None,
):
    async with session_factory() as session:
        # headlines.ticker is a real foreign key into companies(ticker) --
        # a row has to exist there first, same as providers.py's own flow.
        await session.merge(Company(ticker=ticker))
        session.add(
            Headline(
                ticker=ticker,
                title=title,
                url=url,
                category=category,
                provider="finnhub",
                outlet="Yahoo",
                published_at=datetime.now(timezone.utc),
                story_id=story_id,
                sentiment_score=sentiment_score,
                sentiment_gloss="bullish" if sentiment_score is not None else None,
                sentiment_rationale="Real rationale." if sentiment_score is not None else None,
                sentiment_status=sentiment_status,
            )
        )
        await session.commit()


async def test_search_success_returns_seeded_data(test_session_factory):
    # Real data already in the DB, plus a fake job that reports a clean success.
    await _seed_headline(test_session_factory, "AAPL", "A real headline", "https://example.com/1")

    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: _FakeArqRedis(
        _FakeJob(
            result={
                "status": "success",
                "providers": {"edgar": "ok", "finnhub": "ok"},
                "headline_count": 1,
                "grouping": "ok",
            }
        )
    )
    # Act: hit the real endpoint, backed by the fakes above.
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/search", params={"ticker": "AAPL"})
    finally:
        app.dependency_overrides.clear()

    # Assert: the real, already-seeded headline comes back in the response shape.
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["ticker"] == "AAPL"
    assert body["grouping"] == "ok"
    today = next(d for d in body["days"] if d["is_today"])
    assert len(today["stories"]) == 1
    assert today["stories"][0]["primary"]["title"] == "A real headline"


async def test_search_skips_awaiting_a_deferred_job_and_returns_existing_data(test_session_factory):
    """ADR 0018 -- a background-refresh check can defer this ticker's job via ARQ's own
    scheduling (rate limit or cooldown). /api/search must never sit waiting on that: joining a
    deferred job should return immediately with current data, not hang for job_timeout_seconds."""
    await _seed_headline(test_session_factory, "NVDA", "Existing headline", "https://example.com/3")

    # The fake job is deferred -- records whether .result() was ever awaited, rather than
    # raising from inside it (which search()'s own broad except would just swallow, hiding a bug).
    result_calls: list[None] = []

    async def _record_call(*args, **kwargs):
        result_calls.append(None)
        return {"status": "success", "providers": {}, "grouping": "ok"}

    job = _FakeJob(status=JobStatus.deferred)
    job.result = _record_call

    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: _FakeArqRedis(job)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/search", params={"ticker": "NVDA"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert result_calls == []  # .result() was never awaited
    body = response.json()
    assert body["status"] == "complete_failure"
    assert body["providers"] == {}
    assert body["grouping"] == "unknown"
    today = next(d for d in body["days"] if d["is_today"])
    assert today["stories"][0]["primary"]["title"] == "Existing headline"


async def test_search_job_timeout_still_returns_existing_data(test_session_factory):
    """Reproduces the worker-down check done manually in lesson 9 -- now
    automated, no need to actually stop a container."""
    await _seed_headline(test_session_factory, "AMZN", "Existing headline", "https://example.com/2")

    # The fake job never returns -- the endpoint should still fall back to existing DB data.
    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: _FakeArqRedis(_FakeJob(exc=asyncio.TimeoutError()))
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/search", params={"ticker": "AMZN"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "complete_failure"
    assert body["providers"] == {}
    # The job never returned at all -- grouping's outcome genuinely can't be
    # known, distinct from "ok"/"skipped"/"error" which all mean it ran (ADR 0012).
    assert body["grouping"] == "unknown"
    today = next(d for d in body["days"] if d["is_today"])
    assert len(today["stories"]) == 1
    assert today["stories"][0]["primary"]["title"] == "Existing headline"


async def test_search_returns_grouped_daily_view(test_session_factory):
    """One real round trip proving the full nested shape: a grouped pair
    sharing a story_id, an ungrouped (null-story) headline, and a filing --
    all in one Story list, none dropped or incorrectly merged (ADR 0013)."""
    # headlines.story_id is a real FK into stories -- both rows need to exist first.
    async with test_session_factory() as session:
        shared_story = Story(ticker="NFLX")
        filing_story = Story(ticker="NFLX")
        session.add_all([shared_story, filing_story])
        await session.commit()
        shared_story_id, filing_story_id = shared_story.id, filing_story.id

    # Seed one grouped pair, one ungrouped headline, and one filing -- all same ticker/day.
    await _seed_headline(
        test_session_factory, "NFLX", "Grouped primary", "https://example.com/grp-1", story_id=shared_story_id
    )
    await _seed_headline(
        test_session_factory, "NFLX", "Grouped member", "https://example.com/grp-2", story_id=shared_story_id
    )
    await _seed_headline(test_session_factory, "NFLX", "Ungrouped headline", "https://example.com/ungrouped")
    await _seed_headline(
        test_session_factory, "NFLX", "8-K: filing", "https://example.com/filing-1",
        category="filing", story_id=filing_story_id,
    )

    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: _FakeArqRedis(
        _FakeJob(result={"status": "success", "providers": {"edgar": "ok", "finnhub": "ok"}, "headline_count": 4, "grouping": "ok"})
    )
    # Act: hit the real endpoint.
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/search", params={"ticker": "NFLX"})
    finally:
        app.dependency_overrides.clear()

    # Assert: three distinct Story entries, correctly nested.
    body = response.json()
    today = next(d for d in body["days"] if d["is_today"])
    assert len(today["stories"]) == 3  # the grouped pair, the ungrouped headline, and the filing

    grouped = next(s for s in today["stories"] if s["story_id"] == str(shared_story_id))
    assert grouped["primary"]["title"] == "Grouped primary"
    assert [m["title"] for m in grouped["other_members"]] == ["Grouped member"]

    ungrouped = next(s for s in today["stories"] if s["primary"]["title"] == "Ungrouped headline")
    assert ungrouped["story_id"] is None
    assert ungrouped["other_members"] == []


def _headline_with_status(status):
    # Bare, unpersisted Headline -- _compute_sentiment_status only ever reads sentiment_status.
    return Headline(sentiment_status=status)


def test_sentiment_status_skipped_when_not_configured(monkeypatch):
    from ticker_backend.config import settings

    monkeypatch.setattr(settings, "sentiment_configured", False)
    # Even a headline with a real score doesn't override "skipped" -- the
    # config check runs first, before any headline row is even considered.
    assert _compute_sentiment_status([_headline_with_status("ok")]) == "skipped"


def test_sentiment_status_error_even_while_others_are_still_pending(monkeypatch):
    from ticker_backend.config import settings

    monkeypatch.setattr(settings, "sentiment_configured", True)
    # Error takes priority over "processing" -- it must surface, not be masked by a pending headline.
    assert _compute_sentiment_status([_headline_with_status("error"), _headline_with_status(None)]) == "error"


def test_sentiment_status_processing_when_any_headline_still_pending(monkeypatch):
    from ticker_backend.config import settings

    monkeypatch.setattr(settings, "sentiment_configured", True)
    # One headline still unresolved (NULL status) is enough to keep the page "processing".
    assert _compute_sentiment_status([_headline_with_status("ok"), _headline_with_status(None)]) == "processing"


def test_sentiment_status_ok_when_everything_resolved(monkeypatch):
    from ticker_backend.config import settings

    monkeypatch.setattr(settings, "sentiment_configured", True)
    # Every headline resolved to a real score -- nothing left pending or failed.
    assert _compute_sentiment_status([_headline_with_status("ok"), _headline_with_status("ok")]) == "ok"


async def test_search_only_enqueues_the_fetch_job(test_session_factory):
    """Plan 0036: /api/search no longer enqueues sentiment_job itself -- that's triggered from
    the fetch job's own completion (worker.py's fetch_headlines_job), so it can never start
    scoring a headline before grouping assigns it a real story_id. Covered directly in
    test_jobs.py (enqueue_sentiment_after_fetch) and test_worker.py (the wiring)."""
    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    fake_redis = _FakeArqRedis(
        _FakeJob(result={"status": "success", "providers": {"edgar": "ok", "finnhub": "ok"}, "headline_count": 0, "grouping": "skipped"})
    )
    app.dependency_overrides[get_arq_redis] = lambda: fake_redis
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/search", params={"ticker": "AAPL"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_redis.enqueued_job_names == ["fetch_headlines_job"]
    assert fake_redis.enqueued_job_ids == ["fetch_headlines:AAPL"]


async def test_search_status_triggers_a_background_check_but_never_awaits_its_result(test_session_factory):
    """ADR 0018 -- the polling endpoint now triggers a background refresh check (for the shared
    rate limit's sake), but must never await that check's own eventual result; a fake whose
    .result() would record a call if ever invoked proves it stays fire-and-forget."""
    await _seed_headline(test_session_factory, "TSLA", "Polled headline", "https://example.com/poll-1")

    result_calls: list[None] = []

    async def _record_call(*args, **kwargs):
        result_calls.append(None)
        return {}

    job = _FakeJob()
    job.result = _record_call
    redis = _FakeArqRedis(job)

    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: redis
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/search/status", params={"ticker": "TSLA"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"sentiment", "days"}
    today = next(d for d in body["days"] if d["is_today"])
    assert today["stories"][0]["primary"]["title"] == "Polled headline"
    assert result_calls == []  # never awaited
    assert redis.enqueued_job_names == ["fetch_headlines_job"]  # but a background check did fire


async def test_search_status_survives_a_background_check_that_blows_up(test_session_factory):
    """ADR 0018/spec 0007 -- a hiccup in the rate-limit check (a Redis blip, say) must never turn
    an otherwise-healthy poll into a 500; same swallow-and-log discipline as jobs.py's own
    enqueue_sentiment_after_fetch."""
    await _seed_headline(test_session_factory, "TSLA", "Still here", "https://example.com/poll-2")

    class _BrokenRedis(_FakeArqRedis):
        async def enqueue_job(self, *args, **kwargs):
            raise ConnectionError("redis hiccup")

    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: _BrokenRedis(_FakeJob())
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/search/status", params={"ticker": "TSLA"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    today = next(d for d in body["days"] if d["is_today"])
    assert today["stories"][0]["primary"]["title"] == "Still here"


async def test_search_status_includes_per_headline_and_story_sentiment(test_session_factory):
    """Real HTTP round trip (lesson 28): a resolved Headline's own fields,
    and its Story's aggregate, both show up correctly in the response."""
    async with test_session_factory() as session:
        story = Story(ticker="GOOGL", sentiment_average=64.0, sentiment_score_count=2)
        session.add(story)
        await session.commit()
        story_id = story.id

    await _seed_headline(
        test_session_factory, "GOOGL", "Resolved headline", "https://example.com/sent-int-1",
        story_id=story_id, sentiment_score=82, sentiment_status="ok",
    )
    await _seed_headline(
        test_session_factory, "GOOGL", "Second member", "https://example.com/sent-int-2",
        story_id=story_id, sentiment_score=46, sentiment_status="ok",
    )

    # ADR 0018: search_status now also depends on get_arq_redis for its background-check trigger.
    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: _FakeArqRedis(_FakeJob())
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/search/status", params={"ticker": "GOOGL"})
    finally:
        app.dependency_overrides.clear()

    body = response.json()
    today = next(d for d in body["days"] if d["is_today"])
    story_dict = today["stories"][0]

    primary = story_dict["primary"]
    assert primary["sentiment_score"] == 82
    assert primary["sentiment_gloss"] == "bullish"
    assert primary["sentiment_status"] == "ok"
    assert primary["sentiment_enum"] == "positive"

    assert story_dict["sentiment_average"] == 64.0
    assert story_dict["sentiment_enum"] == "neutral"


async def _sign_in(client: AsyncClient, redis: FakeRedisKV, sub: str) -> None:
    # A direct Redis write, matching auth.py's own session:{id} -> sub shape -- not a full
    # Google sign-in round trip, which is already covered by test_auth.py.
    session_id = f"test-session-{sub}"
    await redis.set(f"session:{session_id}", sub)
    client.cookies.set(SESSION_COOKIE_NAME, session_id)


def _success_job() -> _FakeJob:
    return _FakeJob(result={"status": "success", "providers": {}, "grouping": "skipped"})


async def test_search_records_a_view_for_a_signed_in_user_with_a_matching_watchlist_entry(test_session_factory):
    """ADR 0019: a signed-in user's own view of a watchlisted ticker resets that entry's
    last_viewed_at, which is what its "new since last viewed" count is computed from."""
    await _seed_headline(test_session_factory, "MSFT", "A headline", "https://example.com/wl-1")
    async with test_session_factory() as session:
        await session.merge(User(sub="user-1"))
        old = datetime(2020, 1, 1, tzinfo=timezone.utc)
        session.add(WatchlistEntry(user_sub="user-1", ticker="MSFT", added_at=old, last_viewed_at=old))
        await session.commit()

    redis = _FakeArqRedis(_success_job())
    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: redis
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _sign_in(client, redis, "user-1")
            response = await client.get("/api/search", params={"ticker": "MSFT"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    async with test_session_factory() as session:
        entry = await session.get(WatchlistEntry, ("user-1", "MSFT"))
    assert entry.last_viewed_at > old


async def test_search_does_not_create_an_entry_for_a_ticker_not_on_the_watchlist(test_session_factory):
    """A signed-in user searching a ticker they haven't watchlisted must not gain a
    watchlist entry as a side effect -- only an existing entry's view is ever recorded.
    A real companies row exists for MSFT (it's been searched before, just never
    watchlisted) so a broken auto-create wouldn't be accidentally masked by the ticker FK
    rejecting the insert outright -- caught by a deliberate break that a companies-less
    ticker let through silently."""
    await _seed_headline(test_session_factory, "MSFT", "A headline", "https://example.com/wl-3")
    async with test_session_factory() as session:
        await session.merge(User(sub="user-1"))
        await session.commit()

    redis = _FakeArqRedis(_success_job())
    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: redis
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _sign_in(client, redis, "user-1")
            response = await client.get("/api/search", params={"ticker": "MSFT"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    async with test_session_factory() as session:
        entry = await session.get(WatchlistEntry, ("user-1", "MSFT"))
    assert entry is None


async def test_search_view_recording_survives_a_broken_session_factory(test_session_factory):
    """ADR 0019: a hiccup recording the view must never turn an otherwise-healthy search
    into a failure -- same swallow-and-log discipline as jobs.py's own
    enqueue_sentiment_after_fetch. Forced by handing the view-recording step a session
    factory that raises, while the endpoint's own data load still uses the real one."""
    await _seed_headline(test_session_factory, "MSFT", "A headline", "https://example.com/wl-2")
    async with test_session_factory() as session:
        await session.merge(User(sub="user-1"))
        old = datetime(2020, 1, 1, tzinfo=timezone.utc)
        session.add(WatchlistEntry(user_sub="user-1", ticker="MSFT", added_at=old, last_viewed_at=old))
        await session.commit()

    class _BrokenSessionFactory:
        def __call__(self):
            return self

        async def __aenter__(self):
            raise RuntimeError("db hiccup")

        async def __aexit__(self, *args):
            return False

    from ticker_backend import search as search_module

    original_record = search_module._record_view_if_watchlisted

    async def _broken_record(session_factory, user, ticker):
        # Exercises the real function's own try/except with a factory engineered to raise,
        # rather than swapping in a fake that skips the function's own error handling.
        return await original_record(_BrokenSessionFactory(), user, ticker)

    redis = _FakeArqRedis(_success_job())
    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: redis
    try:
        search_module._record_view_if_watchlisted = _broken_record
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _sign_in(client, redis, "user-1")
            response = await client.get("/api/search", params={"ticker": "MSFT"})
    finally:
        search_module._record_view_if_watchlisted = original_record
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    today = next(d for d in body["days"] if d["is_today"])
    assert today["stories"][0]["primary"]["title"] == "A headline"
    # The broken factory means the view was never actually recorded -- still 200, not 500.
    async with test_session_factory() as session:
        entry = await session.get(WatchlistEntry, ("user-1", "MSFT"))
    assert entry.last_viewed_at == old

