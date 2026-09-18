"""The /api/search endpoint — see docs/plans/0009-api-search-endpoint.md.

Two steps, not one: enqueue-and-await lesson 7's fetch job (so Postgres has
fresh data), then separately query Postgres and shape the response. The job
result is just a status summary — it never hands back headline data.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import structlog
from arq import ArqRedis, create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, FastAPI, Request
from sqlalchemy import select

from ticker_backend.config import RECENT_HEADLINES_WINDOW, settings
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
    """FastAPI dependency, not a plain default -- FastAPI introspects path
    operation parameters, and a bare async_sessionmaker breaks that.
    Depends() injects it without being treated as request data."""
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


def _group_into_stories(headlines: list[Headline]) -> list[dict]:
    """Groups same-`story_id` headlines into one Story dict (primary +
    other_members). A `story_id=None` headline (grouping skipped/errored,
    ADR 0012) becomes its own singleton Story rather than merging with other
    null-story headlines or disappearing."""
    # Bucket by story_id, falling back to the headline's own id when there's no Story yet.
    groups: dict[object, list[Headline]] = {}
    for headline in headlines:
        key = headline.story_id if headline.story_id is not None else headline.id
        groups.setdefault(key, []).append(headline)

    # Within each group, earliest-published is the primary (ADR 0009); the rest are other_members, newest-first.
    stories = []
    for members in groups.values():
        members_oldest_first = sorted(members, key=lambda h: h.published_at)
        primary, *rest = members_oldest_first
        stories.append(
            {
                "story_id": str(primary.story_id) if primary.story_id is not None else None,
                "primary": _headline_to_dict(primary),
                "other_members": [_headline_to_dict(h) for h in reversed(rest)],
            }
        )
    return stories


def build_daily_view(headlines: list[Headline], now: datetime) -> list[dict]:
    """One entry per calendar day (Eastern), each holding that day's Stories
    (ADR 0013). Pure function — `now` is a parameter, not `datetime.now()`
    called internally, so DST/boundary behavior stays testable without
    waiting for real midnight.

    Today is always included, even with zero Stories; earlier days appear
    only when they have at least one (ADR 0013) -- no padding out to a
    fixed 7-day scaffold."""
    today_date = now.astimezone(EASTERN).date()

    # Bucket raw headlines by their own Eastern day first -- a Story's members
    # already share one day by construction (ADR 0006), so grouping within
    # each day bucket below can't accidentally split or merge across days.
    by_day: dict = {}
    for headline in headlines:
        day = headline.published_at.astimezone(EASTERN).date()
        by_day.setdefault(day, []).append(headline)
    by_day.setdefault(today_date, [])

    # Newest day first; each day's Stories newest-first by primary's published_at.
    days = []
    for day in sorted(by_day.keys(), reverse=True):
        stories = _group_into_stories(by_day[day])
        stories.sort(key=lambda story: story["primary"]["published_at"], reverse=True)
        days.append({"date": day.isoformat(), "is_today": day == today_date, "stories": stories})
    return days


def _compute_sentiment_status(headlines: list[Headline]) -> str:
    """The page-level sentiment status -- ok/skipped/error/processing, derived fresh from
    already-queried headline rows, never stored anywhere (spec 0005/ADR 0014). Checked in this
    priority order deliberately: an error surfaces even while other headlines are still pending,
    rather than being masked by "processing"."""
    if not settings.openai_api_key:
        return "skipped"
    if any(h.sentiment_status == "error" for h in headlines):
        return "error"
    if any(h.sentiment_status is None for h in headlines):
        return "processing"
    return "ok"


async def _load_search_results(ticker: str, session_factory) -> tuple[list[dict], str]:
    """Queries Postgres for this ticker's recent headlines and builds both the day view and the
    page-level sentiment status from the same rows -- shared by /api/search and
    /api/search/status (lesson 26) so the two never drift out of sync with each other."""
    cutoff = datetime.now(timezone.utc) - RECENT_HEADLINES_WINDOW

    # Query Postgres directly for this ticker's recent headlines -- neither
    # job hands back headline data itself, per the module docstring.
    async with session_factory() as session:
        rows = await session.execute(
            select(Headline).where(Headline.ticker == ticker, Headline.published_at >= cutoff)
        )
        headlines = list(rows.scalars())

    # One entry per calendar day, each holding that day's Stories (ADR 0013).
    days = build_daily_view(headlines, datetime.now(timezone.utc))
    sentiment_status = _compute_sentiment_status(headlines)
    return days, sentiment_status


@router.get("/api/search")
async def search(
    ticker: str,
    arq_redis: ArqRedis = Depends(get_arq_redis),
    session_factory=Depends(get_session_factory),
) -> dict:
    """See the module docstring for the two-step shape. Ticker
    case-normalization happens here, once -- the frontend deliberately
    doesn't uppercase before calling this."""
    ticker = ticker.upper()

    # Default in case the job below never returns a real result at all.
    providers_status: dict[str, str] = {}
    # "unknown", not "ok"/"skipped"/"error" -- the job never ran, so grouping's outcome can't be known.
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

    # Fire-and-forget (lesson 26/ADR 0014) -- enqueuing is awaited (fast, just submits to the
    # queue), but its *result* never is. Sentiment fills in after this response returns; the
    # frontend polls /api/search/status, not this endpoint, to find out when.
    await arq_redis.enqueue_job("sentiment_job", ticker)

    days, sentiment_status = await _load_search_results(ticker, session_factory)

    return {
        "ticker": ticker,
        "status": status,
        "providers": providers_status,
        # Independent of `status` above -- a grouping problem is a distinct,
        # orthogonal concern from "did EDGAR/Finnhub respond" (ADR 0012).
        "grouping": grouping_status,
        "sentiment": sentiment_status,
        "days": days,
    }


@router.get("/api/search/status")
async def search_status(ticker: str, session_factory=Depends(get_session_factory)) -> dict:
    """Read-only -- no fetch_headlines_job or sentiment_job enqueue, just current Postgres state
    (lesson 26/ADR 0014). The frontend's poll loop calls this, not /api/search itself, so polling
    for sentiment doesn't re-trigger a full EDGAR/Finnhub/embeddings/grouping pass on every tick.
    No status/providers/grouping in the response -- those only ever exist as the fetch job's own
    return value, never persisted, so there's nothing here to report them from."""
    ticker = ticker.upper()
    days, sentiment_status = await _load_search_results(ticker, session_factory)
    return {"sentiment": sentiment_status, "days": days}
