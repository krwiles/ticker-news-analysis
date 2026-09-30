"""A signed-in user's personal set of tracked tickers -- see spec 0008, ADR 0019.

Three endpoints: add, remove, list-with-counts. "New since last viewed" is a read-time
COUNT against headlines.published_at > watchlist_entries.last_viewed_at, never a stored,
incremented column (ADR 0019's domain-modeling pass) -- the same reasoning CONTEXT.md's
`Today` entry already applies elsewhere in this codebase.
"""

import asyncio
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
    # Normalize case the same way /api/search does, so "msft" and "MSFT" hit one row.
    ticker = body.ticker.upper()
    async with session_factory() as session:
        # Already watchlisted -- return its current state rather than erroring or duplicating.
        existing = await session.get(WatchlistEntry, (user.sub, ticker))
        if existing is not None:
            count = await _count_new_headlines(session, ticker, existing.last_viewed_at)
            return _entry_to_dict(existing, count)

        # Enforce the spec's hard cap before inserting an 11th row.
        current_size = await session.scalar(
            select(func.count()).select_from(WatchlistEntry).where(WatchlistEntry.user_sub == user.sub)
        )
        if current_size >= MAX_WATCHLIST_SIZE:
            raise HTTPException(status_code=400, detail=f"Watchlist is full (max {MAX_WATCHLIST_SIZE} tickers)")

        # Insert the new entry, starting its count at 0 (last_viewed_at = now).
        now = datetime.now(timezone.utc)
        entry = WatchlistEntry(user_sub=user.sub, ticker=ticker, added_at=now, last_viewed_at=now)
        session.add(entry)
        try:
            await session.commit()
        except IntegrityError:
            # Either the ticker FK rejected this, or a concurrent request for the same
            # (user, ticker) won the race and committed first -- re-check rather than assume.
            await session.rollback()
            concurrent_entry = await session.get(WatchlistEntry, (user.sub, ticker))
            if concurrent_entry is not None:
                count = await _count_new_headlines(session, ticker, concurrent_entry.last_viewed_at)
                return _entry_to_dict(concurrent_entry, count)
            raise HTTPException(status_code=404, detail="Unknown ticker") from None

    return _entry_to_dict(entry, 0)


@router.delete("/api/watchlist/{ticker}")
async def remove_from_watchlist(
    ticker: str,
    user: User = Depends(require_user),
    session_factory=Depends(get_session_factory),
) -> dict:
    """Idempotent -- no error if the ticker wasn't watchlisted to begin with."""
    # Same case-normalization as add/search.
    ticker = ticker.upper()
    async with session_factory() as session:
        # Look up the entry; deleting only if it actually exists is what makes this idempotent.
        entry = await session.get(WatchlistEntry, (user.sub, ticker))
        if entry is not None:
            await session.delete(entry)
            await session.commit()
    # Always ok, whether or not there was anything to remove.
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
    shared Finnhub window, untouched by this endpoint. The background-fetch checks below run
    concurrently, not one at a time -- each is an independent Redis round trip, so awaiting
    them sequentially would needlessly multiply this endpoint's latency by the watchlist size."""
    # Load this user's entries, oldest-added first (spec 0008's own add-order).
    async with session_factory() as session:
        rows = await session.execute(
            select(WatchlistEntry).where(WatchlistEntry.user_sub == user.sub).order_by(WatchlistEntry.added_at)
        )
        entries = list(rows.scalars())
        # Each entry's current "new since last viewed" count, computed read-time.
        result = [
            _entry_to_dict(entry, await _count_new_headlines(session, entry.ticker, entry.last_viewed_at))
            for entry in entries
        ]

    # Offer every entry up for a possible background fetch, concurrently and unawaited by the
    # caller of this function's own result -- a failure on one ticker never blocks another.
    now = datetime.now(timezone.utc)
    checks = await asyncio.gather(
        *(enqueue_background_fetch(arq_redis, entry.ticker, now) for entry in entries), return_exceptions=True
    )
    for entry, outcome in zip(entries, checks):
        if isinstance(outcome, Exception):
            log.warning("watchlist.background_check_failed", ticker=entry.ticker, error=f"{type(outcome).__name__}: {outcome}")

    return {"entries": result}
