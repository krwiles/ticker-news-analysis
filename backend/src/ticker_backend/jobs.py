"""Job IDs and the enqueue-or-join rule for the fetch and sentiment jobs -- see
docs/adr/0015-single-flight-jobs-per-ticker.md.

Anything that starts one of these jobs (`/api/search` today, a background refresher
later) goes through here, so every caller coalesces on the same per-ticker job ID.
"""

from arq import ArqRedis
from arq.jobs import Job

# How long ARQ keeps a finished fetch's result; must be > 0 or a joiner can hit ResultNotFound (ADR 0015).
FETCH_RESULT_TTL_SECONDS = 5


def fetch_job_id(ticker: str) -> str:
    """The one ARQ job ID a ticker's fetch job ever uses, so two callers can't both start one."""
    # Uppercase so `aapl` and `AAPL` map to the same ID.
    return f"fetch_headlines:{ticker.upper()}"


def sentiment_job_id(ticker: str) -> str:
    """The one ARQ job ID a ticker's sentiment job ever uses -- a separate namespace from fetch's."""
    # Uppercase for the same reason as fetch_job_id.
    return f"sentiment:{ticker.upper()}"


async def enqueue_or_join_fetch(arq_redis: ArqRedis, ticker: str, job_factory=Job) -> Job:
    """Starts the ticker's fetch job, or -- if one is already queued, running, or just finished --
    returns a handle to that one instead. Either way the caller gets something to `await .result()` on.
    `job_factory` is injectable for tests, same convention as `milvus` in providers.py (ADR 0012)."""
    # Enqueue under the deterministic ID; returns a Job, or None if that ID is already taken.
    job_id = fetch_job_id(ticker)
    job = await arq_redis.enqueue_job("fetch_headlines_job", ticker, _job_id=job_id)

    # ID already taken -- another caller's fetch is in flight, so join it rather than start a second.
    if job is None:
        job = job_factory(job_id, redis=arq_redis)
    return job


async def enqueue_sentiment(arq_redis: ArqRedis, ticker: str) -> None:
    """Starts the ticker's sentiment job unless one is already queued or running. Fire-and-forget:
    nothing awaits it, so a duplicate needs no handling -- the running job already covers this ticker."""
    # enqueue_job() returns None when the ID is taken; deliberately ignored for that reason.
    await arq_redis.enqueue_job("sentiment_job", ticker, _job_id=sentiment_job_id(ticker))
