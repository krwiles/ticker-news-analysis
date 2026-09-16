"""The /api/search endpoint — see docs/plans/0009-api-search-endpoint.md.

Two steps, not one: enqueue-and-await lesson 7's fetch job (so Postgres has
fresh data), then separately query Postgres and shape the response. The job
result is just a status summary — it never hands back headline data.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import structlog
from arq import ArqRedis, create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, FastAPI, Request
from sqlalchemy import select

from ticker_backend.config import settings
from ticker_backend.db import async_session_factory
from ticker_backend.models import Headline

log = structlog.get_logger()
router = APIRouter()

# The US market's trading day, not UTC and not the viewer's local timezone —
# see CONTEXT.md's `Today` entry. A real IANA zone, DST-aware.
EASTERN = ZoneInfo("America/New_York")


@asynccontextmanager
async def api_lifespan(app: FastAPI):
    """Creates the ARQ Redis pool once, for the app's whole lifetime — same
    reasoning as db.py's `engine`. Only wired in for `api` mode; `ui` never
    enqueues jobs."""
    app.state.arq_redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    # The app runs here, between startup (above) and shutdown (below).
    yield
    await app.state.arq_redis.aclose()


async def get_arq_redis(request: Request) -> ArqRedis:
    """FastAPI dependency — real requests get api_lifespan's pool; lesson
    10's tests override this to avoid needing a real Redis connection for
    endpoint tests that don't care about the job layer."""
    return request.app.state.arq_redis


def get_session_factory():
    """FastAPI dependency, not a plain default parameter — a path operation's
    parameters are introspected by FastAPI itself (for request validation,
    OpenAPI docs), unlike providers.py's plain functions. A raw
    `async_sessionmaker` object as a bare default breaks that introspection
    (it tries to deep-copy it); Depends() is the FastAPI-specific way to
    inject something without FastAPI trying to treat it as request data."""
    return async_session_factory


def _headline_to_dict(headline: Headline) -> dict:
    """The response shape for one headline -- deliberately not every column
    on the ORM model (no `id`, no `fetched_at`): this is what the frontend
    actually needs, not a raw dump of the row."""
    return {
        "title": headline.title,
        "url": headline.url,
        "category": headline.category,
        "provider": headline.provider,
        "outlet": headline.outlet,
        "summary": headline.summary,
        "published_at": headline.published_at,
    }


def split_today_recent(headlines: list[Headline], now: datetime) -> tuple[list[dict], list[dict]]:
    """Pure function — `now` is a parameter, not `datetime.now()` called
    internally, so lesson 10 can test the Eastern-midnight/DST boundary
    against a fixed fake time instead of waiting for real midnight."""
    # Anchor "today" to the US market's calendar day, not UTC.
    today_date = now.astimezone(EASTERN).date()
    # Two buckets to fill below.
    today: list[dict] = []
    recent: list[dict] = []
    # Walk every headline newest-first, so each bucket ends up sorted too.
    for headline in sorted(headlines, key=lambda h: h.published_at, reverse=True):
        # Convert to the response shape before bucketing.
        entry = _headline_to_dict(headline)
        # Same-day headlines go in Today, everything else in Recent.
        if headline.published_at.astimezone(EASTERN).date() == today_date:
            today.append(entry)
        else:
            recent.append(entry)
    return today, recent


@router.get("/api/search")
async def search(
    ticker: str,
    arq_redis: ArqRedis = Depends(get_arq_redis),
    session_factory=Depends(get_session_factory),
) -> dict:
    """See the module docstring for the two-step shape. Also this project's
    frontend/backend case-insensitivity boundary: the frontend (lesson 13)
    deliberately does *not* uppercase a ticker read from the URL before
    calling this endpoint -- this line is where that normalization
    actually happens, once, so every caller can stay careless about case."""
    ticker = ticker.upper()

    # Default in case the job below never returns a real result at all.
    providers_status: dict[str, str] = {}
    # "unknown", not "ok"/"skipped"/"error" -- those three (ADR 0012) all
    # mean grouping was actually evaluated; if the job itself never
    # returned, grouping's outcome genuinely can't be known. Same "unknown
    # means can't tell" convention health.py's check_worker already uses.
    grouping_status = "unknown"
    try:
        # Enqueue lesson 7's fetch job and wait for it to finish, so Postgres has fresh data before we query it.
        job = await arq_redis.enqueue_job("fetch_headlines_job", ticker)
        result = await job.result(timeout=settings.job_timeout_seconds)
        # Pull the job's own status, per-provider detail, and grouping outcome out of its result.
        status = result["status"]
        providers_status = result["providers"]
        grouping_status = result["grouping"]
    except Exception as exc:  # noqa: BLE001 - timeout or unexpected job failure both surface the same way
        # asyncio.TimeoutError carries no message (str(exc) is empty) -- the
        # exception's own type is the only thing that says what happened.
        log.warning("search.job_failed", ticker=ticker, error=f"{type(exc).__name__}: {exc}")
        status = "complete_failure"

    # Trailing 7-day window in plain UTC -- precision only matters for the Today/Recent split below.
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    # Query Postgres directly for this ticker's recent headlines -- the job
    # itself never hands back headline data, per the module docstring.
    async with session_factory() as session:
        rows = await session.execute(
            select(Headline).where(Headline.ticker == ticker, Headline.published_at >= cutoff)
        )
        headlines = list(rows.scalars())

    # Split into Today/Recent buckets for the response.
    today, recent = split_today_recent(headlines, datetime.now(timezone.utc))

    return {
        "ticker": ticker,
        "status": status,
        "providers": providers_status,
        # Independent of `status` above -- a grouping problem is a distinct,
        # orthogonal concern from "did EDGAR/Finnhub respond" (ADR 0012).
        "grouping": grouping_status,
        "today": today,
        "recent": recent,
    }
