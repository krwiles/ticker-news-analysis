"""check_milvus() tests -- Milvus mocked via a small hand-rolled fake, same
convention as test_grouping.py's _FakeMilvusClient, not a real connection.
"""

from ticker_backend.health import check_milvus


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
