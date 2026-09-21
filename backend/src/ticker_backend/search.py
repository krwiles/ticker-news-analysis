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

from ticker_backend.config import RECENT_HEADLINES_WINDOW, derive_sentiment_enum, settings
from ticker_backend.db import async_session_factory
from ticker_backend.jobs import enqueue_or_join_fetch, enqueue_sentiment
from ticker_backend.models import Headline, Story

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
    actually needs, not a raw dump of the row.

    `sentiment_enum` is computed here, not stored anywhere (spec 0005/ADR
    0014's "derive, don't store") -- `None` until a real score exists, same
    as `sentiment_score` itself. Named `sentiment_enum`, not `sentiment` --
    the response's own top-level `sentiment` key is a status
    (ok/skipped/error/processing), a completely different value domain;
    reusing the bare name here would mean the same key holds two unrelated
    kinds of values depending on nesting depth (lesson 28)."""
    return {
        "title": headline.title,
        "url": headline.url,
        "category": headline.category,
        "provider": headline.provider,
        "outlet": headline.outlet,
        "summary": headline.summary,
        "published_at": headline.published_at,
        "sentiment_score": headline.sentiment_score,
        "sentiment_gloss": headline.sentiment_gloss,
        "sentiment_rationale": headline.sentiment_rationale,
        "sentiment_status": headline.sentiment_status,
        "sentiment_enum": derive_sentiment_enum(headline.sentiment_score) if headline.sentiment_score is not None else None,
    }


def _group_into_stories(headlines: list[Headline], stories_by_id: dict) -> list[dict]:
    """Groups same-`story_id` headlines into one Story dict (primary +
    other_members). A `story_id=None` headline (grouping skipped/errored,
    ADR 0012) becomes its own singleton Story rather than merging with other
    null-story headlines or disappearing.

    `sentiment_average`/`sentiment_enum` come from the real `Story` row
    (`stories_by_id`, keyed by id) -- the incrementally-updated aggregate
    lesson 26 maintains, not recomputed here. Always present, nullable --
    `None` until at least one member has a real score (spec 0005: "A Story
    with only one member shows no such aggregate"; the frontend's own
    member-count check, not a missing key here, is what actually hides it)."""
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
        story = stories_by_id.get(primary.story_id)
        has_aggregate = story is not None and story.sentiment_score_count > 0
        stories.append(
            {
                "story_id": str(primary.story_id) if primary.story_id is not None else None,
                "primary": _headline_to_dict(primary),
                "other_members": [_headline_to_dict(h) for h in reversed(rest)],
                "sentiment_average": story.sentiment_average if has_aggregate else None,
                "sentiment_enum": derive_sentiment_enum(story.sentiment_average) if has_aggregate else None,
            }
        )
    return stories


def build_daily_view(headlines: list[Headline], now: datetime, stories_by_id: dict | None = None) -> list[dict]:
    """One entry per calendar day (Eastern), each holding that day's Stories
    (ADR 0013). Pure function — `now` is a parameter, not `datetime.now()`
    called internally, so DST/boundary behavior stays testable without
    waiting for real midnight.

    Today is always included, even with zero Stories; earlier days appear
    only when they have at least one (ADR 0013) -- no padding out to a
    fixed 7-day scaffold.

    `stories_by_id` (lesson 28) is where each Story's own sentiment
    aggregate comes from -- optional, defaulting to empty, so existing
    callers/tests that don't care about sentiment don't need to change."""
    stories_by_id = stories_by_id or {}
    today_date = now.astimezone(EASTERN).date()

    # Bucket raw headlines by their own Eastern day first -- a Story's members already share
    # one day by construction (ADR 0006), so grouping within a bucket can't cross days.
    by_day: dict = {}
    for headline in headlines:
        day = headline.published_at.astimezone(EASTERN).date()
        by_day.setdefault(day, []).append(headline)
    by_day.setdefault(today_date, [])

    # Newest day first; each day's Stories newest-first by primary's published_at.
    days = []
    for day in sorted(by_day.keys(), reverse=True):
        stories = _group_into_stories(by_day[day], stories_by_id)
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

        # Every Story these headlines reference -- a plain second query, not an ORM relationship,
        # matching this codebase's "no SQLAlchemy relationship() annotations" convention.
        story_ids = {h.story_id for h in headlines if h.story_id is not None}
        stories_by_id: dict = {}
        if story_ids:
            story_rows = await session.execute(select(Story).where(Story.id.in_(story_ids)))
            stories_by_id = {story.id: story for story in story_rows.scalars()}

    # One entry per calendar day, each holding that day's Stories (ADR 0013).
    days = build_daily_view(headlines, datetime.now(timezone.utc), stories_by_id)
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
        # Start lesson 7's fetch job -- or join the one already running for this ticker (ADR 0015) -- and wait for it.
        job = await enqueue_or_join_fetch(arq_redis, ticker)
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

    # Fire-and-forget (ADR 0014): the result is never awaited -- the frontend polls /api/search/status
    # instead. Skipped if this ticker's sentiment job is already running (ADR 0015).
    await enqueue_sentiment(arq_redis, ticker)

    # Now that fresh data is in Postgres, query it and build the response.
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
    # Same case-normalization as search() above.
    ticker = ticker.upper()
    days, sentiment_status = await _load_search_results(ticker, session_factory)
    return {"sentiment": sentiment_status, "days": days}
