"""Job IDs and the enqueue-or-join rule for the fetch and sentiment jobs -- see
docs/adr/0015-single-flight-jobs-per-ticker.md.

Anything that starts one of these jobs (`/api/search` today, a background refresher
later) goes through here, so every caller coalesces on the same per-ticker job ID.
"""

from datetime import datetime, timezone

import structlog
from arq import ArqRedis
from arq.jobs import Job
from sqlalchemy import update

from ticker_backend.config import RECENT_HEADLINES_WINDOW, settings
from ticker_backend.db import async_session_factory
from ticker_backend.models import Headline

log = structlog.get_logger()

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


async def enqueue_sentiment(arq_redis: ArqRedis, ticker: str) -> Job | None:
    """Starts the ticker's sentiment job unless one is already queued or running. Fire-and-forget:
    nobody awaits the returned Job -- but callers do care whether a *new* job actually started
    (a real Job) versus one already being in flight (None), e.g. this module's own stale-status
    reset below, which must only run when a fresh retry is genuinely about to happen."""
    # enqueue_job() returns None when the ID is taken -- handed straight back, not swallowed.
    return await arq_redis.enqueue_job("sentiment_job", ticker, _job_id=sentiment_job_id(ticker))


async def _reset_stale_sentiment_status(ticker: str, session_factory) -> None:
    """Clears a previously-failed/skipped headline's status back to pending right as a *new*
    sentiment job actually starts, so a later request/poll shows it as still-in-progress rather
    than stuck on a stale outcome while the retry runs (plan 0032, relocated here by plan 0036).

    Only called when settings.openai_api_key is truthy -- without it, an impending job just
    re-batches everything to 'skipped' almost instantly (sentiment.py:_mark_skipped), so 'skipped'
    is left out of the target set entirely and there's nothing worth resetting to pending for.
    The WHERE below only ever matches 'error'/'skipped' rows, so it can never race against and
    overwrite a row the job just wrote 'ok' to (plan 0032's safety property)."""
    cutoff = datetime.now(timezone.utc) - RECENT_HEADLINES_WINDOW
    async with session_factory() as session:
        await session.execute(
            update(Headline)
            .where(
                Headline.ticker == ticker,
                Headline.published_at >= cutoff,
                Headline.sentiment_status.in_(["error", "skipped"]),
            )
            .values(sentiment_status=None)
        )
        await session.commit()


async def enqueue_sentiment_after_fetch(
    arq_redis: ArqRedis, ticker: str, session_factory=async_session_factory
) -> None:
    """Called once a ticker's fetch job (fetch + grouping) has genuinely finished -- from
    worker.py's fetch_headlines_job, never from search() -- so sentiment can never start scoring a
    headline before grouping has assigned it a real story_id (plan 0036's fix for the timed-out-
    fetch race, lesson 34). Swallows its own failures: a hiccup here must never turn an otherwise-
    successful fetch job's reported result into a failure."""
    try:
        sentiment_job_handle = await enqueue_sentiment(arq_redis, ticker)
        if sentiment_job_handle is not None and settings.openai_api_key:
            await _reset_stale_sentiment_status(ticker, session_factory)
    except Exception as exc:  # noqa: BLE001 - logged and swallowed, see docstring
        log.warning("jobs.sentiment_trigger_failed", ticker=ticker, error=f"{type(exc).__name__}: {exc}")
