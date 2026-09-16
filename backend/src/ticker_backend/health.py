"""Health checks, aggregated by the api container for the status page.

See docs/adr/0001-single-image-multi-mode-containers.md for why one
endpoint (this one) reports on the whole skeleton instead of the browser
polling each container directly.
"""

import time

import structlog
from fastapi import APIRouter
from redis.asyncio import Redis
from sqlalchemy import text

from ticker_backend.config import settings
from ticker_backend.db import engine

log = structlog.get_logger()
router = APIRouter()

# The worker proves it's alive by writing a timestamp here on a cron job.
WORKER_HEARTBEAT_KEY = "worker:heartbeat"
WORKER_STALE_AFTER_SECONDS = 30


async def check_db() -> dict:
    """A real query, not just "is the connection object truthy" -- SELECT 1
    is the cheapest possible proof the database is actually answering."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001 - report any failure, don't crash the health check
        log.warning("health.db_check_failed", error=str(exc))
        return {"status": "error", "detail": str(exc)}


async def check_redis() -> tuple[dict, Redis | None]:
    """Returns the live client alongside the status, not just the status --
    check_worker (below) needs a real connection to read the heartbeat key,
    and opening a second one there would be redundant."""
    client = Redis.from_url(settings.redis_url)
    try:
        await client.ping()
        return {"status": "ok"}, client
    except Exception as exc:  # noqa: BLE001
        log.warning("health.redis_check_failed", error=str(exc))
        await client.aclose()
        return {"status": "error", "detail": str(exc)}, None


async def check_worker(client: Redis | None) -> dict:
    """"unknown" (can't tell -- Redis itself is down) is a distinct state
    from "error" (Redis works, but the worker has never checked in) and
    "stale" (it checked in, just not recently enough to trust) -- three
    different failure shapes an operator would want to tell apart."""
    # Redis itself was unreachable -- there's no way to even ask the question.
    if client is None:
        return {"status": "unknown", "detail": "redis unavailable"}

    # Redis works, but the worker has never written a heartbeat at all.
    raw = await client.get(WORKER_HEARTBEAT_KEY)
    if raw is None:
        return {"status": "error", "detail": "no heartbeat recorded yet"}

    # A heartbeat exists -- check whether it's recent enough to trust.
    age_seconds = round(time.time() - float(raw), 1)
    if age_seconds > WORKER_STALE_AFTER_SECONDS:
        return {"status": "stale", "age_seconds": age_seconds}
    return {"status": "ok", "age_seconds": age_seconds}


@router.get("/api/health")
async def health() -> dict:
    """The one aggregate endpoint `api` mode exposes -- see the module
    docstring for why the browser calls this instead of polling db/redis/
    worker separately itself."""
    # Check the database first.
    db_status = await check_db()
    # Check Redis, keeping the live client around -- the worker check below needs it.
    redis_status, redis_client = await check_redis()
    # Check the worker via that same Redis connection.
    worker_status = await check_worker(redis_client)
    # Close the connection now that both Redis-dependent checks are done.
    if redis_client is not None:
        await redis_client.aclose()

    return {
        "api": {"status": "ok"},
        "db": db_status,
        "redis": redis_status,
        "worker": worker_status,
    }


# ui's own trivial self-check, not the full aggregate above -- see ADR 0002.
ui_router = APIRouter()


@ui_router.get("/health")
async def ui_health() -> dict:
    """Deliberately trivial -- proves this container itself is up, nothing
    more. The real aggregate is `health()` above, on the api container."""
    return {"status": "ok"}
