"""ARQ worker entrypoint (`worker` mode — see config.app_mode).

Proves it's alive by writing a heartbeat to Redis every 5 seconds (read by
the api container's /health endpoint), and — as of lesson 7 — runs the
provider-fetch job triggered by /api/search (see ADR 0004).
"""

import time

import structlog
from arq import cron, func
from arq.connections import RedisSettings

from ticker_backend.config import settings
from ticker_backend.health import WORKER_HEARTBEAT_KEY
from ticker_backend.jobs import FETCH_RESULT_TTL_SECONDS, enqueue_sentiment_after_fetch
from ticker_backend.logging import configure_logging
from ticker_backend.providers import fetch_and_persist_headlines
from ticker_backend.sentiment import compute_and_persist_sentiment

configure_logging()
log = structlog.get_logger()


async def heartbeat(ctx: dict) -> None:
    """An ARQ cron job, not enqueued by anything -- runs on its own schedule
    (see WorkerSettings.cron_jobs below), the only proof-of-life this
    process has since it runs no HTTP server of its own."""
    # Write the current timestamp -- health.py's check_worker reads this key
    # and compares its age to decide ok/stale.
    await ctx["redis"].set(WORKER_HEARTBEAT_KEY, str(time.time()))
    log.info("worker.heartbeat")


async def fetch_headlines_job(ctx: dict, ticker: str) -> dict:
    """Thin ARQ wrapper — the actual logic stays framework-agnostic in
    providers.py so it's callable directly from a test (lesson 9) or, later,
    from a cron_jobs entry for the future watchlist feature."""
    result = await fetch_and_persist_headlines(ticker)
    # Sentiment starts only once this job's own fetch+grouping is truly done (plan 0036) --
    # never from search(), which can't know when a background-run job finishes.
    await enqueue_sentiment_after_fetch(ctx["redis"], ticker)
    return result


async def sentiment_job(ctx: dict, ticker: str) -> dict:
    """Thin ARQ wrapper, same shape as fetch_headlines_job -- the real logic
    stays framework-agnostic in sentiment.py. Unlike fetch_headlines_job,
    /api/search enqueues this without awaiting its result (lesson 26/ADR
    0014) -- it's a separate, decoupled job, not a step inside the fetch."""
    return await compute_and_persist_sentiment(ticker)


class WorkerSettings:
    """ARQ discovers this class by name (`arq ticker_backend.worker.WorkerSettings`,
    see docker-compose.yml's worker command) -- not imported and called
    directly anywhere in this codebase."""

    # Enqueue-able job functions -- what /api/search's `enqueue_job(...)` is dispatching to (ADR 0004).
    # func() wraps each to set how long ARQ keeps its result: brief for fetch, none for sentiment (ADR 0015).
    functions = [
        func(fetch_headlines_job, keep_result=FETCH_RESULT_TTL_SECONDS),
        func(sentiment_job, keep_result=0),
    ]
    # Runs on its own, every 5 seconds, no external trigger -- the other
    # ARQ pattern this project deliberately exercises alongside `functions`.
    cron_jobs = [cron(heartbeat, second=set(range(0, 60, 5)))]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
