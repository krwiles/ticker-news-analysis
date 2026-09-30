"""Integration tests for /api/watchlist -- see docs/specs/0008-watchlists.md, ADR 0019.

Mirrors test_search_endpoint.py's shape: httpx's ASGITransport, get_arq_redis/get_session_factory
overridden, a real test Postgres for everything else. A signed-in caller is a real User row plus
a fake Redis session key set directly (auth.py's own _session_key format), not a full sign-in
round trip -- these tests are about the watchlist endpoints, not Google sign-in itself.
"""

from datetime import datetime, timedelta, timezone

from arq.jobs import JobStatus
from fakes import FakeRedisKV, sign_in as _sign_in
from httpx import ASGITransport, AsyncClient

from ticker_backend.main import app
from ticker_backend.models import Company, Headline, User, WatchlistEntry
from ticker_backend.search import get_arq_redis, get_session_factory


class _FakeJob:
    # .result() records rather than raises -- raising is swallowed by the endpoint's own
    # broad except, which would make "never awaits" pass for the wrong reason (deliberate break).
    def __init__(self, result_calls: list, status=JobStatus.complete):
        self._result_calls = result_calls
        self._status = status

    async def status(self):
        return self._status

    async def result(self, timeout=None):
        self._result_calls.append(None)
        return {}


class _FakeArqRedis(FakeRedisKV):
    # Records every enqueue_job() call -- same shape as test_search_endpoint.py's own fake.
    def __init__(self):
        super().__init__()
        self.enqueued_job_ids: list[str | None] = []
        self.result_calls: list = []

    async def enqueue_job(self, name, *args, _job_id=None, **kwargs):
        self.enqueued_job_ids.append(_job_id)
        return _FakeJob(self.result_calls)


async def _seed_user(session_factory, sub: str) -> None:
    async with session_factory() as session:
        await session.merge(User(sub=sub))
        await session.commit()


async def _seed_company(session_factory, ticker: str) -> None:
    async with session_factory() as session:
        await session.merge(Company(ticker=ticker))
        await session.commit()


async def _seed_headline(session_factory, ticker: str, title: str, url: str, published_at: datetime) -> None:
    async with session_factory() as session:
        await session.merge(Company(ticker=ticker))
        session.add(
            Headline(
                ticker=ticker,
                title=title,
                url=url,
                category="news",
                provider="finnhub",
                published_at=published_at,
            )
        )
        await session.commit()


async def _seed_watchlist_entry(session_factory, sub: str, ticker: str, last_viewed_at: datetime) -> None:
    async with session_factory() as session:
        now = datetime.now(timezone.utc)
        session.add(WatchlistEntry(user_sub=sub, ticker=ticker, added_at=now, last_viewed_at=last_viewed_at))
        await session.commit()


async def test_add_creates_an_entry_for_an_already_known_ticker(test_session_factory):
    await _seed_user(test_session_factory, "user-1")
    await _seed_company(test_session_factory, "MSFT")
    redis = _FakeArqRedis()
    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: redis
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _sign_in(client, redis, "user-1")
            response = await client.post("/api/watchlist", json={"ticker": "msft"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"ticker": "MSFT", "added_at": response.json()["added_at"], "new_headlines": 0}
    async with test_session_factory() as session:
        entry = await session.get(WatchlistEntry, ("user-1", "MSFT"))
    assert entry is not None


async def test_add_rejects_a_ticker_with_no_companies_row(test_session_factory):
    await _seed_user(test_session_factory, "user-1")
    redis = _FakeArqRedis()
    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: redis
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _sign_in(client, redis, "user-1")
            # Act: NVDA was never searched/fetched, so no companies row exists for it.
            response = await client.post("/api/watchlist", json={"ticker": "NVDA"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    async with test_session_factory() as session:
        entry = await session.get(WatchlistEntry, ("user-1", "NVDA"))
    assert entry is None


async def test_add_is_idempotent_for_an_already_watchlisted_ticker(test_session_factory):
    await _seed_user(test_session_factory, "user-1")
    await _seed_company(test_session_factory, "MSFT")
    redis = _FakeArqRedis()
    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: redis
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _sign_in(client, redis, "user-1")
            first = await client.post("/api/watchlist", json={"ticker": "MSFT"})
            second = await client.post("/api/watchlist", json={"ticker": "MSFT"})
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert second.status_code == 200
    async with test_session_factory() as session:
        from sqlalchemy import select

        rows = (
            (await session.execute(select(WatchlistEntry).where(WatchlistEntry.user_sub == "user-1")))
            .scalars()
            .all()
        )
    assert len(rows) == 1


async def test_add_recovers_from_a_concurrent_duplicate_insert_instead_of_reporting_404(test_session_factory):
    """A rare race: two near-simultaneous adds for the same (user, ticker) can both pass the
    'already watchlisted?' check before either commits (neither sees the other's not-yet-committed
    row). The loser's commit hits the PRIMARY KEY violation, not the ticker FK -- it must recover
    as an idempotent success, not misreport a perfectly valid, already-watchlisted ticker as 404.
    Simulated deterministically: a real conflicting row already exists (as if a concurrent request
    just won), and this request's own "already watchlisted?" check is forced to miss it once,
    exactly as READ COMMITTED isolation would for two truly concurrent transactions."""
    await _seed_user(test_session_factory, "user-1")
    await _seed_company(test_session_factory, "MSFT")
    now = datetime.now(timezone.utc)
    await _seed_watchlist_entry(test_session_factory, "user-1", "MSFT", now)

    from sqlalchemy.ext.asyncio import AsyncSession

    from ticker_backend import watchlist as watchlist_module

    original_get = AsyncSession.get
    missed_once = {"done": False}

    async def get_that_misses_once(self, model, ident, *args, **kwargs):
        if model is watchlist_module.WatchlistEntry and not missed_once["done"]:
            missed_once["done"] = True
            return None
        return await original_get(self, model, ident, *args, **kwargs)

    redis = _FakeArqRedis()
    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: redis
    try:
        AsyncSession.get = get_that_misses_once
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _sign_in(client, redis, "user-1")
            response = await client.post("/api/watchlist", json={"ticker": "MSFT"})
    finally:
        AsyncSession.get = original_get
        app.dependency_overrides.clear()

    # A false 404 here would be the bug -- MSFT is a real, already-watchlisted ticker.
    assert response.status_code == 200
    assert response.json()["ticker"] == "MSFT"
    async with test_session_factory() as session:
        from sqlalchemy import select

        rows = (
            (await session.execute(select(WatchlistEntry).where(WatchlistEntry.user_sub == "user-1")))
            .scalars()
            .all()
        )
    assert len(rows) == 1  # never duplicated


async def test_add_rejects_an_eleventh_ticker(test_session_factory):
    await _seed_user(test_session_factory, "user-1")
    now = datetime.now(timezone.utc)
    for i in range(10):
        ticker = f"TICK{i}"
        await _seed_company(test_session_factory, ticker)
        await _seed_watchlist_entry(test_session_factory, "user-1", ticker, now)
    await _seed_company(test_session_factory, "ELEVENTH")
    redis = _FakeArqRedis()
    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: redis
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _sign_in(client, redis, "user-1")
            response = await client.post("/api/watchlist", json={"ticker": "ELEVENTH"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    async with test_session_factory() as session:
        entry = await session.get(WatchlistEntry, ("user-1", "ELEVENTH"))
    assert entry is None


async def test_add_requires_sign_in(test_session_factory):
    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: _FakeArqRedis()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Act: no cookie at all.
            response = await client.post("/api/watchlist", json={"ticker": "MSFT"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


async def test_remove_deletes_an_existing_entry(test_session_factory):
    await _seed_user(test_session_factory, "user-1")
    await _seed_company(test_session_factory, "MSFT")
    await _seed_watchlist_entry(test_session_factory, "user-1", "MSFT", datetime.now(timezone.utc))
    redis = _FakeArqRedis()
    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: redis
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _sign_in(client, redis, "user-1")
            response = await client.delete("/api/watchlist/MSFT")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    async with test_session_factory() as session:
        entry = await session.get(WatchlistEntry, ("user-1", "MSFT"))
    assert entry is None


async def test_remove_is_idempotent_for_a_ticker_never_watchlisted(test_session_factory):
    await _seed_user(test_session_factory, "user-1")
    redis = _FakeArqRedis()
    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: redis
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _sign_in(client, redis, "user-1")
            response = await client.delete("/api/watchlist/MSFT")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


async def test_remove_requires_sign_in(test_session_factory):
    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: _FakeArqRedis()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete("/api/watchlist/MSFT")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


async def test_list_returns_entries_ordered_by_added_at_with_current_counts(test_session_factory):
    await _seed_user(test_session_factory, "user-1")
    now = datetime.now(timezone.utc)
    await _seed_company(test_session_factory, "MSFT")
    await _seed_company(test_session_factory, "AAPL")
    # MSFT added first, viewed a while ago -- one fresh headline since then.
    async with test_session_factory() as session:
        session.add(WatchlistEntry(user_sub="user-1", ticker="MSFT", added_at=now - timedelta(minutes=10), last_viewed_at=now - timedelta(hours=1)))
        session.add(WatchlistEntry(user_sub="user-1", ticker="AAPL", added_at=now - timedelta(minutes=5), last_viewed_at=now))
        await session.commit()
    await _seed_headline(test_session_factory, "MSFT", "New MSFT headline", "https://example.com/msft-1", now)

    redis = _FakeArqRedis()
    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: redis
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _sign_in(client, redis, "user-1")
            response = await client.get("/api/watchlist")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    entries = response.json()["entries"]
    # Add-order: MSFT (added first) before AAPL.
    assert [e["ticker"] for e in entries] == ["MSFT", "AAPL"]
    assert entries[0]["new_headlines"] == 1
    assert entries[1]["new_headlines"] == 0


async def test_list_is_empty_not_an_error_for_a_signed_in_user_with_no_entries(test_session_factory):
    await _seed_user(test_session_factory, "user-1")
    redis = _FakeArqRedis()
    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: redis
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _sign_in(client, redis, "user-1")
            response = await client.get("/api/watchlist")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"entries": []}


async def test_list_requires_sign_in(test_session_factory):
    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: _FakeArqRedis()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/watchlist")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


async def test_list_triggers_a_background_check_per_entry_without_awaiting_any_result(test_session_factory):
    await _seed_user(test_session_factory, "user-1")
    await _seed_company(test_session_factory, "MSFT")
    await _seed_company(test_session_factory, "AAPL")
    await _seed_watchlist_entry(test_session_factory, "user-1", "MSFT", datetime.now(timezone.utc))
    await _seed_watchlist_entry(test_session_factory, "user-1", "AAPL", datetime.now(timezone.utc))

    redis = _FakeArqRedis()
    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: redis
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _sign_in(client, redis, "user-1")
            response = await client.get("/api/watchlist")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert set(redis.enqueued_job_ids) == {"fetch_headlines:MSFT", "fetch_headlines:AAPL"}
    assert redis.result_calls == []  # enqueued, but never awaited


async def test_list_survives_a_background_check_that_blows_up(test_session_factory):
    await _seed_user(test_session_factory, "user-1")
    await _seed_company(test_session_factory, "MSFT")
    await _seed_watchlist_entry(test_session_factory, "user-1", "MSFT", datetime.now(timezone.utc))

    class _BrokenRedis(_FakeArqRedis):
        async def enqueue_job(self, *args, **kwargs):
            raise ConnectionError("redis hiccup")

    redis = _BrokenRedis()
    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: redis
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _sign_in(client, redis, "user-1")
            response = await client.get("/api/watchlist")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["entries"][0]["ticker"] == "MSFT"
