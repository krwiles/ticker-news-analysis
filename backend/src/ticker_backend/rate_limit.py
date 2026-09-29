"""A shared Finnhub call budget plus a per-ticker fetch cooldown -- see docs/adr/0018-*.md.

Gates the *whole* fetch job at enqueue time (jobs.py), not the Finnhub call alone inside it --
`should_defer_fetch` never touches `/api/search`'s own always-immediate path, only the
background-refresh trigger. `now` is always a parameter, never read internally, matching
config.py's `recent_headlines_cutoff` testable-purity style.
"""

from datetime import datetime

# Finnhub's free-tier cap, shared across every ticker and every viewer -- not per-ticker.
FINNHUB_RATE_LIMIT_PER_MINUTE = 60
# Floor between two real fetch attempts for one ticker -- stops it monopolizing the shared budget.
FETCH_COOLDOWN_SECONDS = 30.0


def _finnhub_window_key(now: datetime) -> str:
    # Bucketed per calendar minute -- a fixed window, not a sliding one (ADR 0018's accepted trade-off).
    return f"finnhub_calls:{now.strftime('%Y%m%dT%H%M')}"


def _last_fetch_key(ticker: str) -> str:
    return f"last_fetch:{ticker}"


async def record_finnhub_fetch(redis, ticker: str, now: datetime) -> None:
    """Called once, right when a real Finnhub call is about to be made (providers.py) -- records
    both the shared window's count and this ticker's own cooldown timestamp together, since both
    exist for the same reason: a real call just happened."""
    window_key = _finnhub_window_key(now)
    await redis.incr(window_key)
    # Generous cleanup buffer past the window itself -- the decision logic keys off the bucketed
    # name, not this TTL, so an untested fake with a no-op expire() is still correct to test against.
    await redis.expire(window_key, 120)
    await redis.set(_last_fetch_key(ticker), now.isoformat())


async def should_defer_fetch(redis, ticker: str, now: datetime) -> tuple[bool, float]:
    """Whether a background-triggered fetch for this ticker should be deferred right now, and by
    how many seconds -- checked before enqueueing (jobs.py), never awaited from inside the job
    itself. Two independent gates, either one defers: this ticker's own cooldown, then the shared
    Finnhub window."""
    last_fetch_raw = await redis.get(_last_fetch_key(ticker))
    if last_fetch_raw is not None:
        # redis-py hands back bytes unless decode_responses is set -- same fact ADR 0016's
        # session helpers already accounted for; normalize either way.
        if isinstance(last_fetch_raw, bytes):
            last_fetch_raw = last_fetch_raw.decode()
        last_fetch = datetime.fromisoformat(last_fetch_raw)
        since_last = (now - last_fetch).total_seconds()
        if since_last < FETCH_COOLDOWN_SECONDS:
            return True, FETCH_COOLDOWN_SECONDS - since_last

    window_calls_raw = await redis.get(_finnhub_window_key(now))
    window_calls = int(window_calls_raw) if window_calls_raw is not None else 0
    if window_calls >= FINNHUB_RATE_LIMIT_PER_MINUTE:
        # Defer roughly until the next minute boundary, where a fresh window starts uncounted.
        seconds_into_minute = now.second + now.microsecond / 1_000_000
        return True, 60.0 - seconds_into_minute

    return False, 0.0
