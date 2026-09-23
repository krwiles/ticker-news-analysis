"""Tests for jobs.py's single-flight rule and the worker's job registration -- see
docs/adr/0015-single-flight-jobs-per-ticker.md and docs/plans/0031-*.md. No real Redis:
the fakes below mimic the one ARQ behavior this relies on (a taken job ID makes
enqueue_job() return None), which the live stack check in plan 0031 proves for real."""

import asyncio

from ticker_backend.jobs import (
    FETCH_RESULT_TTL_SECONDS,
    enqueue_or_join_fetch,
    enqueue_sentiment,
    fetch_job_id,
    sentiment_job_id,
)
from ticker_backend.worker import WorkerSettings


class _FakeJob:
    # Stands in for an ARQ Job handle -- carries a canned result and remembers which ID it is.
    def __init__(self, job_id: str, result=None):
        self.job_id = job_id
        self._result = result

    async def result(self, timeout=None):
        return self._result


class _FakeArqRedis:
    """Mimics ArqRedis.enqueue_job()'s uniqueness rule: the first enqueue of a job ID claims it
    and returns a Job; any later enqueue of the same ID returns None."""

    def __init__(self, taken_ids: set[str] | None = None):
        self.taken_ids = set(taken_ids or ())
        # Every enqueue attempt (name, args, job ID), and just the IDs that were actually accepted.
        self.attempts: list[tuple[str, tuple, str | None]] = []
        self.accepted_ids: list[str] = []

    async def enqueue_job(self, name, *args, _job_id=None, **kwargs):
        self.attempts.append((name, args, _job_id))
        # Yield once so two concurrent callers genuinely interleave, like two real requests would.
        await asyncio.sleep(0)
        if _job_id in self.taken_ids:
            return None
        self.taken_ids.add(_job_id)
        self.accepted_ids.append(_job_id)
        return _FakeJob(_job_id, result="own result")


def _join_factory(shared_result):
    # Builds a job_factory that records what it was asked to join and returns a job with a known result.
    joined: list[tuple[str, object]] = []

    def factory(job_id, redis):
        joined.append((job_id, redis))
        return _FakeJob(job_id, result=shared_result)

    return factory, joined


def test_fetch_job_id_is_per_ticker_and_case_insensitive():
    # Act + assert: any casing of a ticker maps to the one uppercase ID.
    assert fetch_job_id("aapl") == fetch_job_id("AAPL") == "fetch_headlines:AAPL"
    # Different tickers must never share an ID, or they'd wrongly block each other.
    assert fetch_job_id("AAPL") != fetch_job_id("MSFT")


def test_sentiment_job_id_is_per_ticker_and_distinct_from_fetch():
    # Act + assert: same case-insensitive rule as fetch, under its own prefix.
    assert sentiment_job_id("aapl") == sentiment_job_id("AAPL") == "sentiment:AAPL"
    # A fetch job and a sentiment job for one ticker are separate jobs and must not collide.
    assert sentiment_job_id("AAPL") != fetch_job_id("AAPL")


async def test_first_fetch_caller_enqueues_and_gets_its_own_job():
    # Arrange: nothing in flight yet, and a factory that would record any (wrong) join.
    redis = _FakeArqRedis()
    factory, joined = _join_factory("joined result")

    # Act: the first caller for this ticker.
    job = await enqueue_or_join_fetch(redis, "AAPL", job_factory=factory)

    # Assert: it enqueued by name with the deterministic ID, and never took the join path.
    assert redis.attempts == [("fetch_headlines_job", ("AAPL",), "fetch_headlines:AAPL")]
    assert await job.result() == "own result"
    assert joined == []


async def test_second_fetch_caller_joins_the_existing_job():
    # Arrange: a fetch for AAPL is already in flight (its ID is taken).
    redis = _FakeArqRedis(taken_ids={"fetch_headlines:AAPL"})
    factory, joined = _join_factory("in-flight result")

    # Act: another caller arrives for the same ticker, in different casing.
    job = await enqueue_or_join_fetch(redis, "aapl", job_factory=factory)

    # Assert: it was handed a handle to the *existing* job's ID, and awaits that job's result.
    assert joined == [("fetch_headlines:AAPL", redis)]
    assert await job.result() == "in-flight result"
    assert redis.accepted_ids == []


async def test_concurrent_fetch_callers_share_one_fetch():
    # Arrange: a clean queue and a factory whose joined job returns the same result the first job would.
    redis = _FakeArqRedis()
    factory, joined = _join_factory("own result")

    # Act: two callers for one ticker at the same moment, like a double-click or two users.
    first, second = await asyncio.gather(
        enqueue_or_join_fetch(redis, "AAPL", job_factory=factory),
        enqueue_or_join_fetch(redis, "AAPL", job_factory=factory),
    )

    # Assert: exactly one fetch was really enqueued, the other caller joined it, and both see one result.
    assert redis.accepted_ids == ["fetch_headlines:AAPL"]
    assert len(joined) == 1
    assert await first.result() == await second.result() == "own result"


async def test_different_tickers_do_not_block_each_other():
    # Arrange: an AAPL fetch is already in flight.
    redis = _FakeArqRedis(taken_ids={"fetch_headlines:AAPL"})
    factory, joined = _join_factory("should not be used")

    # Act: a fetch for a different ticker.
    job = await enqueue_or_join_fetch(redis, "MSFT", job_factory=factory)

    # Assert: MSFT got its own real job -- coalescing is strictly per ticker.
    assert redis.accepted_ids == ["fetch_headlines:MSFT"]
    assert joined == []
    assert await job.result() == "own result"


async def test_sentiment_enqueue_uses_deterministic_id_and_tolerates_a_duplicate():
    # Arrange: a sentiment job for AAPL is already running.
    redis = _FakeArqRedis(taken_ids={"sentiment:AAPL"})

    # Act: enqueue again -- ARQ returns None, which fire-and-forget must simply ignore.
    result = await enqueue_sentiment(redis, "AAPL")

    # Assert: it tried the deterministic ID by job name, nothing new was accepted, and nothing raised.
    assert redis.attempts == [("sentiment_job", ("AAPL",), "sentiment:AAPL")]
    assert redis.accepted_ids == []
    assert result is None


async def test_sentiment_enqueue_returns_the_job_when_nothing_is_running():
    # Arrange: no sentiment job for AAPL in flight yet.
    redis = _FakeArqRedis()

    # Act: enqueue -- ARQ accepts the deterministic ID and hands back a real Job.
    result = await enqueue_sentiment(redis, "AAPL")

    # Assert: callers (search.py's error-reset) can tell a *new* job actually started, not just that
    # the call didn't raise -- this is the same signal enqueue_or_join_fetch already relies on.
    assert redis.accepted_ids == ["sentiment:AAPL"]
    assert result is not None
    assert await result.result() == "own result"


def test_worker_registers_both_jobs_with_the_intended_result_retention():
    # Arrange: index the registered ARQ Function objects by the name enqueue_job() dispatches to.
    functions = {fn.name: fn for fn in WorkerSettings.functions}

    # Assert: fetch keeps its result briefly (joiners need it; ARQ's 1h default would pin Refresh to it).
    assert functions["fetch_headlines_job"].keep_result_s == FETCH_RESULT_TTL_SECONDS
    assert FETCH_RESULT_TTL_SECONDS > 0
    # Sentiment is fire-and-forget, so nothing keeps its result.
    assert functions["sentiment_job"].keep_result_s == 0
