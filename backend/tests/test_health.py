"""check_milvus()/check_db() tests. Milvus is mocked via a small hand-rolled
fake, same convention as test_grouping.py's _FakeMilvusClient. check_db is
exercised against the real test database (test_session_factory/test_engine,
see conftest.py) -- its default engine only resolves inside the docker
network, so a real DB check needs the injectable engine spec 0004 added.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from ticker_backend.health import check_db, check_milvus
from ticker_backend.models import Company, Headline, Story


class _FakeMilvusClient:
    """Stands in for a real MilvusClient -- configurable existence/count,
    and tracks close() calls so tests can confirm ownership behavior."""

    def __init__(self, collection_exists: bool = True, row_count: int = 0):
        self.collection_exists = collection_exists
        self.row_count = row_count
        self.closed = False

    def has_collection(self, name: str, timeout: float | None = None) -> bool:
        return self.collection_exists

    def get_collection_stats(self, name: str, timeout: float | None = None) -> dict:
        return {"row_count": self.row_count}

    def close(self) -> None:
        self.closed = True


class _BrokenMilvusClient(_FakeMilvusClient):
    """Simulates a reachable-but-failing Milvus (e.g. a query timeout)."""

    def has_collection(self, name: str, timeout: float | None = None) -> bool:
        raise RuntimeError("simulated Milvus outage")


def test_check_milvus_ok_when_collection_exists():
    # Arrange: a fake client with a real, non-empty collection.
    fake = _FakeMilvusClient(collection_exists=True, row_count=1404)

    # Act: run the check with the fake injected.
    result = check_milvus(client=fake)

    # Assert: reports ok with the real vector count.
    assert result == {"status": "ok", "vector_count": 1404}


def test_check_milvus_not_initialized_when_collection_missing():
    # Arrange: a fake client that's reachable but has no collection yet.
    fake = _FakeMilvusClient(collection_exists=False)

    # Act: run the check with the fake injected.
    result = check_milvus(client=fake)

    # Assert: reports the distinct, non-error "not_initialized" state.
    assert result == {"status": "not_initialized"}


def test_check_milvus_error_when_query_fails():
    # Arrange: a fake client that raises once queried.
    fake = _BrokenMilvusClient()

    # Act: run the check with the broken fake injected.
    result = check_milvus(client=fake)

    # Assert: reports error with a human-readable detail, doesn't raise.
    assert result["status"] == "error"
    assert "simulated Milvus outage" in result["detail"]


def test_check_milvus_error_when_construction_fails(monkeypatch):
    # Arrange: make the real MilvusClient constructor fail, as it does
    # against an unreachable URI (verified live against a bad port).
    def _raise(*args, **kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr("ticker_backend.health.MilvusClient", _raise)

    # Act: run the check with no client injected (the real construction path).
    result = check_milvus()

    # Assert: reports error rather than propagating the exception.
    assert result["status"] == "error"
    assert "connection refused" in result["detail"]


def test_check_milvus_never_closes_an_injected_client():
    # Arrange: a fake client passed in, as a test double would be.
    fake = _FakeMilvusClient(collection_exists=True, row_count=0)

    # Act: run the check with the fake injected.
    check_milvus(client=fake)

    # Assert: ownership stays with the caller -- the check never closes it.
    assert fake.closed is False


@pytest.fixture
def test_engine(test_session_factory):
    # Reuses conftest's own test-database URL rather than duplicating it --
    # async_sessionmaker stores its bound engine under kw["bind"].
    return test_session_factory.kw["bind"]


async def test_check_db_reports_real_counts(test_session_factory, test_engine):
    # Arrange: seed a known number of rows across all three tables.
    async with test_session_factory() as session:
        session.add(Company(ticker="AAPL"))
        session.add(Company(ticker="MSFT"))
        session.add(Headline(
            ticker="AAPL", title="A", url="https://example.com/a", category="news",
            provider="finnhub", published_at=datetime.now(timezone.utc),
        ))
        session.add(Story(ticker="AAPL"))
        await session.commit()

    # Act: run the check against the real test database.
    result = await check_db(engine=test_engine)

    # Assert: ok, with the real counts, one per line -- always plural, even for headlines' 1.
    assert result == {"status": "ok", "detail": "2 companies\n1 headlines\n1 stories"}


async def test_check_db_reports_zero_when_empty(test_engine):
    # Arrange: rely on _clean_tables' autouse truncation -- no seeding.

    # Act: run the check against the real, empty test database.
    result = await check_db(engine=test_engine)

    # Assert: a real 0 per table, one per line, not an error.
    assert result == {"status": "ok", "detail": "0 companies\n0 headlines\n0 stories"}


async def test_check_db_error_when_unreachable():
    # Arrange: an engine pointed at a port nothing is listening on.
    broken_engine = create_async_engine("postgresql+asyncpg://ticker:ticker@localhost:1/ticker")

    # Act: run the check against the broken engine.
    result = await check_db(engine=broken_engine)

    # Assert: reports error, same shape as a connection failure always has.
    assert result["status"] == "error"
    assert "detail" in result
