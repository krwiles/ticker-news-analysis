"""Integration tests for /api/watchlist -- see docs/specs/0008-watchlists.md, ADR 0019.

Mirrors test_search_endpoint.py's shape: httpx's ASGITransport, get_arq_redis/get_session_factory
overridden, a real test Postgres for everything else. A signed-in caller is a real User row plus
a fake Redis session key set directly (auth.py's own _session_key format), not a full sign-in
round trip -- these tests are about the watchlist endpoints, not Google sign-in itself.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from arq.jobs import JobStatus
from fakes import FakeRedisKV, sign_in as _sign_in
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

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


@asynccontextmanager
async def _client(test_session_factory, redis, *, sub: str | None = None):
    """Overrides get_session_factory/get_arq_redis for the lifetime of the client, clearing them
    afterward -- the dependency-override/try-finally shape every test here needs, extracted after
    it was duplicated line-for-line across more than a dozen tests (code review finding). Signs in
    as `sub` first when given; leaves the client signed-out (no cookie at all) otherwise."""
    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_arq_redis] = lambda: redis
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            if sub is not None:
                await _sign_in(client, redis, sub)
            yield client
    finally:
        app.dependency_overrides.clear()


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
    # Arrange: a signed-in user, and a ticker that's already been searched/fetched before.
    await _seed_user(test_session_factory, "user-1")
    await _seed_company(test_session_factory, "MSFT")
    redis = _FakeArqRedis()

    # Act: add it, lowercase, to prove case-normalization too.
    async with _client(test_session_factory, redis, sub="user-1") as client:
        response = await client.post("/api/watchlist", json={"ticker": "msft"})

    # Assert: a normalized, zero-count entry comes back, and the row really exists.
    assert response.status_code == 200
    assert response.json() == {"ticker": "MSFT", "added_at": response.json()["added_at"], "new_headlines": 0}
    async with test_session_factory() as session:
        entry = await session.get(WatchlistEntry, ("user-1", "MSFT"))
    assert entry is not None


async def test_add_rejects_a_ticker_with_no_companies_row(test_session_factory):
    # Arrange: a signed-in user, but no companies row for the ticker they'll try to add.
    await _seed_user(test_session_factory, "user-1")
    redis = _FakeArqRedis()

    # Act: NVDA was never searched/fetched, so no companies row exists for it.
    async with _client(test_session_factory, redis, sub="user-1") as client:
        response = await client.post("/api/watchlist", json={"ticker": "NVDA"})

    # Assert: rejected, and nothing was inserted.
    assert response.status_code == 404
    async with test_session_factory() as session:
        entry = await session.get(WatchlistEntry, ("user-1", "NVDA"))
    assert entry is None


async def test_add_is_idempotent_for_an_already_watchlisted_ticker(test_session_factory):
    # Arrange: a signed-in user with a real, addable ticker.
    await _seed_user(test_session_factory, "user-1")
    await _seed_company(test_session_factory, "MSFT")
    redis = _FakeArqRedis()

    # Act: add the same ticker twice.
    async with _client(test_session_factory, redis, sub="user-1") as client:
        first = await client.post("/api/watchlist", json={"ticker": "MSFT"})
        second = await client.post("/api/watchlist", json={"ticker": "MSFT"})

    # Assert: both succeed, but only one row ever exists.
    assert first.status_code == 200
    assert second.status_code == 200
    async with test_session_factory() as session:
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
    # Arrange: MSFT is already watchlisted for real (the "winning" concurrent request).
    await _seed_user(test_session_factory, "user-1")
    await _seed_company(test_session_factory, "MSFT")
    now = datetime.now(timezone.utc)
    await _seed_watchlist_entry(test_session_factory, "user-1", "MSFT", now)

    # Arrange: force this request's own existence check to miss that row exactly once, simulating
    # the losing side of a real race rather than waiting on genuine, non-deterministic concurrency.
    from sqlalchemy.ext.asyncio import AsyncSession

    from ticker_backend import watchlist as watchlist_module

    original_get = AsyncSession.get
    missed_once = {"done": False}

    async def get_that_misses_once(self, model, ident, *args, **kwargs):
        if model is watchlist_module.WatchlistEntry and not missed_once["done"]:
            missed_once["done"] = True
            return None
        return await original_get(self, model, ident, *args, **kwargs)

    # Act: add the already-watchlisted ticker while the existence check is forced blind.
    redis = _FakeArqRedis()
    try:
        AsyncSession.get = get_that_misses_once
        async with _client(test_session_factory, redis, sub="user-1") as client:
            response = await client.post("/api/watchlist", json={"ticker": "MSFT"})
    finally:
        AsyncSession.get = original_get

    # Assert: a false 404 here would be the bug -- MSFT is a real, already-watchlisted ticker.
    assert response.status_code == 200
    assert response.json()["ticker"] == "MSFT"
    async with test_session_factory() as session:
        rows = (
            (await session.execute(select(WatchlistEntry).where(WatchlistEntry.user_sub == "user-1")))
            .scalars()
            .all()
        )
    assert len(rows) == 1  # never duplicated


async def test_add_rejects_an_eleventh_ticker(test_session_factory):
    # Arrange: a signed-in user already at the 10-ticker cap, plus one more addable ticker.
    await _seed_user(test_session_factory, "user-1")
    now = datetime.now(timezone.utc)
    for i in range(10):
        ticker = f"TICK{i}"
        await _seed_company(test_session_factory, ticker)
        await _seed_watchlist_entry(test_session_factory, "user-1", ticker, now)
    await _seed_company(test_session_factory, "ELEVENTH")
    redis = _FakeArqRedis()

    # Act: try to add an 11th.
    async with _client(test_session_factory, redis, sub="user-1") as client:
        response = await client.post("/api/watchlist", json={"ticker": "ELEVENTH"})

    # Assert: rejected, and nothing was inserted.
    assert response.status_code == 400
    async with test_session_factory() as session:
        entry = await session.get(WatchlistEntry, ("user-1", "ELEVENTH"))
    assert entry is None


async def test_add_requires_sign_in(test_session_factory):
    # Act: no cookie at all.
    async with _client(test_session_factory, _FakeArqRedis()) as client:
        response = await client.post("/api/watchlist", json={"ticker": "MSFT"})

    # Assert: rejected before it ever reaches the endpoint body.
    assert response.status_code == 401


async def test_remove_deletes_an_existing_entry(test_session_factory):
    # Arrange: a signed-in user with an existing watchlist entry.
    await _seed_user(test_session_factory, "user-1")
    await _seed_company(test_session_factory, "MSFT")
    await _seed_watchlist_entry(test_session_factory, "user-1", "MSFT", datetime.now(timezone.utc))
    redis = _FakeArqRedis()

    # Act: remove it.
    async with _client(test_session_factory, redis, sub="user-1") as client:
        response = await client.delete("/api/watchlist/MSFT")

    # Assert: success, and the row is actually gone.
    assert response.status_code == 200
    async with test_session_factory() as session:
        entry = await session.get(WatchlistEntry, ("user-1", "MSFT"))
    assert entry is None


async def test_remove_is_idempotent_for_a_ticker_never_watchlisted(test_session_factory):
    # Arrange: a signed-in user with nothing watchlisted.
    await _seed_user(test_session_factory, "user-1")
    redis = _FakeArqRedis()

    # Act: remove a ticker that was never added.
    async with _client(test_session_factory, redis, sub="user-1") as client:
        response = await client.delete("/api/watchlist/MSFT")

    # Assert: still a clean success, not an error.
    assert response.status_code == 200


async def test_remove_requires_sign_in(test_session_factory):
    # Act: no cookie at all.
    async with _client(test_session_factory, _FakeArqRedis()) as client:
        response = await client.delete("/api/watchlist/MSFT")

    # Assert: rejected before it ever reaches the endpoint body.
    assert response.status_code == 401


async def test_list_returns_entries_ordered_by_added_at_with_current_counts(test_session_factory):
    # Arrange: two watchlisted tickers, MSFT added first; only MSFT has a fresh headline since
    # its own last_viewed_at.
    await _seed_user(test_session_factory, "user-1")
    now = datetime.now(timezone.utc)
    await _seed_company(test_session_factory, "MSFT")
    await _seed_company(test_session_factory, "AAPL")
    async with test_session_factory() as session:
        session.add(WatchlistEntry(user_sub="user-1", ticker="MSFT", added_at=now - timedelta(minutes=10), last_viewed_at=now - timedelta(hours=1)))
        session.add(WatchlistEntry(user_sub="user-1", ticker="AAPL", added_at=now - timedelta(minutes=5), last_viewed_at=now))
        await session.commit()
    await _seed_headline(test_session_factory, "MSFT", "New MSFT headline", "https://example.com/msft-1", now)
    redis = _FakeArqRedis()

    # Act: list the watchlist.
    async with _client(test_session_factory, redis, sub="user-1") as client:
        response = await client.get("/api/watchlist")

    # Assert: add-order, each with its own current count.
    assert response.status_code == 200
    entries = response.json()["entries"]
    assert [e["ticker"] for e in entries] == ["MSFT", "AAPL"]  # MSFT added first
    assert entries[0]["new_headlines"] == 1
    assert entries[1]["new_headlines"] == 0


async def test_list_is_empty_not_an_error_for_a_signed_in_user_with_no_entries(test_session_factory):
    # Arrange: a signed-in user with nothing watchlisted.
    await _seed_user(test_session_factory, "user-1")
    redis = _FakeArqRedis()

    # Act: list the (empty) watchlist.
    async with _client(test_session_factory, redis, sub="user-1") as client:
        response = await client.get("/api/watchlist")

    # Assert: an empty list, not an error.
    assert response.status_code == 200
    assert response.json() == {"entries": []}


async def test_list_requires_sign_in(test_session_factory):
    # Act: no cookie at all.
    async with _client(test_session_factory, _FakeArqRedis()) as client:
        response = await client.get("/api/watchlist")

    # Assert: rejected before it ever reaches the endpoint body.
    assert response.status_code == 401


async def test_list_triggers_a_background_check_per_entry_without_awaiting_any_result(test_session_factory):
    # Arrange: two watchlisted tickers.
    await _seed_user(test_session_factory, "user-1")
    await _seed_company(test_session_factory, "MSFT")
    await _seed_company(test_session_factory, "AAPL")
    await _seed_watchlist_entry(test_session_factory, "user-1", "MSFT", datetime.now(timezone.utc))
    await _seed_watchlist_entry(test_session_factory, "user-1", "AAPL", datetime.now(timezone.utc))
    redis = _FakeArqRedis()

    # Act: list the watchlist.
    async with _client(test_session_factory, redis, sub="user-1") as client:
        response = await client.get("/api/watchlist")

    # Assert: a background check fired for each entry, but none was ever awaited.
    assert response.status_code == 200
    assert set(redis.enqueued_job_ids) == {"fetch_headlines:MSFT", "fetch_headlines:AAPL"}
    assert redis.result_calls == []  # enqueued, but never awaited


async def test_list_survives_a_background_check_that_blows_up(test_session_factory):
    # Arrange: one watchlisted ticker, and a Redis fake whose enqueue always raises.
    await _seed_user(test_session_factory, "user-1")
    await _seed_company(test_session_factory, "MSFT")
    await _seed_watchlist_entry(test_session_factory, "user-1", "MSFT", datetime.now(timezone.utc))

    class _BrokenRedis(_FakeArqRedis):
        async def enqueue_job(self, *args, **kwargs):
            raise ConnectionError("redis hiccup")

    redis = _BrokenRedis()

    # Act: list the watchlist anyway.
    async with _client(test_session_factory, redis, sub="user-1") as client:
        response = await client.get("/api/watchlist")

    # Assert: the blown-up background check never surfaces as a failed response.
    assert response.status_code == 200
    assert response.json()["entries"][0]["ticker"] == "MSFT"
