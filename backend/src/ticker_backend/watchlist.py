"""A signed-in user's personal set of tracked tickers -- see spec 0008, ADR 0019.

Three endpoints: add, remove, list-with-counts. "New since last viewed" is a read-time
COUNT against headlines.published_at > watchlist_entries.last_viewed_at, never a stored,
incremented column (ADR 0019's domain-modeling pass) -- the same reasoning CONTEXT.md's
`Today` entry already applies elsewhere in this codebase.
"""

from datetime import datetime, timezone

import structlog
from arq import ArqRedis
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ticker_backend.auth import require_user
from ticker_backend.deps import get_arq_redis, get_session_factory
from ticker_backend.jobs import enqueue_background_fetch
from ticker_backend.models import Headline, User, WatchlistEntry

log = structlog.get_logger()
router = APIRouter()

# Spec 0008's own cap -- enforced here at add time, not the database, since it's a
# count-of-rows rule rather than something a column constraint can express.
MAX_WATCHLIST_SIZE = 10


class AddToWatchlistRequest(BaseModel):
    ticker: str


def _entry_to_dict(entry: WatchlistEntry, new_headlines: int) -> dict:
    return {"ticker": entry.ticker, "added_at": entry.added_at, "new_headlines": new_headlines}


async def _count_new_headlines(session, ticker: str, since: datetime) -> int:
    """Read-time, not stored -- see the module docstring."""
    result = await session.execute(
        select(func.count()).select_from(Headline).where(Headline.ticker == ticker, Headline.published_at > since)
    )
    return result.scalar_one()


@router.post("/api/watchlist")
async def add_to_watchlist(
    body: AddToWatchlistRequest,
    user: User = Depends(require_user),
    session_factory=Depends(get_session_factory),
) -> dict:
    """Idempotent if already watchlisted; 400 at the 10-ticker cap; 404 for a ticker with
    no `companies` row, enforced by the real FK (ADR 0019) rather than a separate
    pre-check -- `companies.ticker` only ever exists once some provider has confirmed the
    ticker is real, same gate `/api/search` itself relies on."""
    ticker = body.ticker.upper()
    async with session_factory() as session:
        # Already watchlisted -- return its current state rather than erroring or duplicating.
        existing = await session.get(WatchlistEntry, (user.sub, ticker))
        if existing is not None:
            count = await _count_new_headlines(session, ticker, existing.last_viewed_at)
            return _entry_to_dict(existing, count)

        current_size = await session.scalar(
            select(func.count()).select_from(WatchlistEntry).where(WatchlistEntry.user_sub == user.sub)
        )
        if current_size >= MAX_WATCHLIST_SIZE:
            raise HTTPException(status_code=400, detail=f"Watchlist is full (max {MAX_WATCHLIST_SIZE} tickers)")

        now = datetime.now(timezone.utc)
        entry = WatchlistEntry(user_sub=user.sub, ticker=ticker, added_at=now, last_viewed_at=now)
        session.add(entry)
        try:
            await session.commit()
        except IntegrityError:
            # The ticker FK rejected this -- no companies row exists for it yet.
            await session.rollback()
            raise HTTPException(status_code=404, detail="Unknown ticker") from None

    return _entry_to_dict(entry, 0)


@router.delete("/api/watchlist/{ticker}")
async def remove_from_watchlist(
    ticker: str,
    user: User = Depends(require_user),
    session_factory=Depends(get_session_factory),
) -> dict:
    """Idempotent -- no error if the ticker wasn't watchlisted to begin with."""
    ticker = ticker.upper()
    async with session_factory() as session:
        entry = await session.get(WatchlistEntry, (user.sub, ticker))
        if entry is not None:
            await session.delete(entry)
            await session.commit()
    return {"ok": True}


@router.get("/api/watchlist")
async def list_watchlist(
    user: User = Depends(require_user),
    session_factory=Depends(get_session_factory),
    arq_redis: ArqRedis = Depends(get_arq_redis),
) -> dict:
    """Both the sidebar's read and its poll target in one call (ADR 0019): returns every
    entry's current count, and -- as an unawaited, exception-swallowed side effect -- offers
    each watchlisted ticker up for a possible background fetch, exactly like
    /api/search/status already does for one ticker. Safe to call this for up to 10 tickers
    at once: each call independently obeys rate_limit.py's existing per-ticker cooldown and
    shared Finnhub window, untouched by this endpoint."""
    async with session_factory() as session:
        rows = await session.execute(
            select(WatchlistEntry).where(WatchlistEntry.user_sub == user.sub).order_by(WatchlistEntry.added_at)
        )
        entries = list(rows.scalars())
        result = [
            _entry_to_dict(entry, await _count_new_headlines(session, entry.ticker, entry.last_viewed_at))
            for entry in entries
        ]

    now = datetime.now(timezone.utc)
    for entry in entries:
        try:
            await enqueue_background_fetch(arq_redis, entry.ticker, now)
        except Exception as exc:  # noqa: BLE001 - swallowed and logged, same discipline as search_status
            log.warning("watchlist.background_check_failed", ticker=entry.ticker, error=f"{type(exc).__name__}: {exc}")

    return {"entries": result}
