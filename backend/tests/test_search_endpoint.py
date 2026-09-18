"""Integration test for /api/search via httpx's ASGITransport -- no running
server needed. get_arq_redis and get_session_factory are both overridden:
this tests the endpoint's own two-step logic, not lesson 7's real job or a
real Redis connection. See docs/plans/0010-testing-search-feature.md."""

import asyncio
from datetime import datetime, timezone

from httpx import ASGITransport, AsyncClient

from ticker_backend.main import app
from ticker_backend.models import Company, Headline, Story
from ticker_backend.search import _compute_sentiment_status, get_arq_redis, get_session_factory


class _FakeJob:
    # Stands in for a real ARQ Job -- lets a test dictate the job's outcome
    # (a result, or a raised exception) without a real queue behind it.
    def __init__(self, result=None, exc: Exception | None = None):
        self._result = result
        self._exc = exc

    async def result(self, timeout=None):
        if self._exc is not None:
            raise self._exc
        return self._result


class _FakeArqRedis:
    # Stands in for a real ArqRedis pool -- enqueue_job() just hands back the
    # pre-built fake job above, instead of actually talking to Redis. Records
    # every job name enqueued (lesson 26) so a test can prove sentiment_job
    # really does get fired alongside fetch_headlines_job, fire-and-forget.
    def __init__(self, job: _FakeJob):
        self._job = job
        self.enqueued_job_names: list[str] = []

    async def enqueue_job(self, name, *args, **kwargs):
        self.enqueued_job_names.append(name)
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
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/search", params={"ticker": "AAPL"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["ticker"] == "AAPL"
    assert body["grouping"] == "ok"
    today = next(d for d in body["days"] if d["is_today"])
    assert len(today["stories"]) == 1
    assert today["stories"][0]["primary"]["title"] == "A real headline"


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
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/search", params={"ticker": "NFLX"})
    finally:
        app.dependency_overrides.clear()

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

    monkeypatch.setattr(settings, "openai_api_key", "")
    # Even a headline with a real score doesn't override "skipped" -- the
    # config check runs first, before any headline row is even considered.
    assert _compute_sentiment_status([_headline_with_status("ok")]) == "skipped"


def test_sentiment_status_error_even_while_others_are_still_pending(monkeypatch):
    from ticker_backend.config import settings

    monkeypatch.setattr(settings, "openai_api_key", "test-key-not-real")
    # Error takes priority over "processing" -- it must surface, not be masked by a pending headline.
    assert _compute_sentiment_status([_headline_with_status("error"), _headline_with_status(None)]) == "error"


def test_sentiment_status_processing_when_any_headline_still_pending(monkeypatch):
    from ticker_backend.config import settings

    monkeypatch.setattr(settings, "openai_api_key", "test-key-not-real")
    assert _compute_sentiment_status([_headline_with_status("ok"), _headline_with_status(None)]) == "processing"


def test_sentiment_status_ok_when_everything_resolved(monkeypatch):
    from ticker_backend.config import settings

    monkeypatch.setattr(settings, "openai_api_key", "test-key-not-real")
    assert _compute_sentiment_status([_headline_with_status("ok"), _headline_with_status("ok")]) == "ok"


async def test_search_enqueues_sentiment_job_fire_and_forget(test_session_factory):
    """/api/search must enqueue sentiment_job alongside fetch_headlines_job
    (lesson 26/ADR 0014) -- fire-and-forget, so the endpoint never calls
    .result() on it (only _FakeJob's constructor result matters here, since
    a hang on the second job's result would make this test hang too)."""
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
    assert fake_redis.enqueued_job_names == ["fetch_headlines_job", "sentiment_job"]


async def test_search_status_endpoint_never_touches_arq(test_session_factory):
    """The polling endpoint takes no arq_redis dependency at all -- it
    structurally cannot enqueue a job, proven here by never overriding
    get_arq_redis and still getting a clean 200 (lesson 26/ADR 0014)."""
    await _seed_headline(test_session_factory, "TSLA", "Polled headline", "https://example.com/poll-1")

    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
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

    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
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
