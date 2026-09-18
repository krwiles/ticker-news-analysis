"""Health checks, aggregated by the api container for the status page.

See docs/adr/0001-single-image-multi-mode-containers.md for why one
endpoint (this one) reports on the whole skeleton instead of the browser
polling each container directly.
"""

import asyncio
import time

import structlog
from fastapi import APIRouter
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from ticker_backend.config import settings
from ticker_backend.db import engine as default_engine
from ticker_backend.milvus_client import STORY_PRIMARIES_COLLECTION

# Must come after the ticker_backend imports above -- pymilvus's own import unconditionally
# loads this repo's root .env, which can corrupt DATABASE_URL if it happens first (verified live).
from pymilvus import MilvusClient

log = structlog.get_logger()
router = APIRouter()

# The worker proves it's alive by writing a timestamp here on a cron job.
WORKER_HEARTBEAT_KEY = "worker:heartbeat"
WORKER_STALE_AFTER_SECONDS = 30

# Short and explicit -- a hanging/unreachable Milvus must fail fast, not
# stall the rest of /api/health (spec 0003).
MILVUS_CHECK_TIMEOUT_SECONDS = 2.0


async def check_db(engine: AsyncEngine | None = None) -> dict:
    """SELECT 1, the cheapest real proof the database is answering, plus a row count per app
    table (spec 0004), named explicitly so dbmate's own schema_migrations table never appears.
    `engine` is injectable for tests, same convention as check_milvus's `client`."""
    engine = engine or default_engine
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            # One round trip for all three -- see spec 0004.
            counts = (
                await conn.execute(
                    text(
                        "SELECT (SELECT count(*) FROM companies) AS companies, "
                        "(SELECT count(*) FROM headlines) AS headlines, "
                        "(SELECT count(*) FROM stories) AS stories"
                    )
                )
            ).one()
        # One line per table -- StatusTile splits `detail` on "\n" to render each on its own
        # line. Always plural, even at 1 (spec 0004).
        detail = f"{counts.companies} companies\n{counts.headlines} headlines\n{counts.stories} stories"
        return {"status": "ok", "detail": detail}
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


def check_milvus(client: MilvusClient | None = None) -> dict:
    """Vector-store check for the status page (spec 0003). Sync, like every
    pymilvus call -- health() below runs it off the event loop, same reason
    providers.py's _run_milvus exists. `client` is injectable for tests,
    same convention as ensure_story_primaries_collection.

    A fresh client per call, closed when we made it -- mirrors check_redis's
    own convention, not milvus_client.py's long-lived worker singleton,
    which has a different lifecycle and no timeout."""
    owns_client = client is None
    try:
        if client is None:
            client = MilvusClient(uri=settings.milvus_uri, timeout=MILVUS_CHECK_TIMEOUT_SECONDS)
        # Reachable, but grouping may never have run yet -- a real, expected
        # state (e.g. no OPENAI_API_KEY configured), not an error.
        if not client.has_collection(STORY_PRIMARIES_COLLECTION, timeout=MILVUS_CHECK_TIMEOUT_SECONDS):
            return {"status": "not_initialized"}
        # Collection exists -- report how many Stories are actually indexed.
        stats = client.get_collection_stats(STORY_PRIMARIES_COLLECTION, timeout=MILVUS_CHECK_TIMEOUT_SECONDS)
        return {"status": "ok", "vector_count": stats["row_count"]}
    except Exception as exc:  # noqa: BLE001 - report any failure, don't crash the health check
        log.warning("health.milvus_check_failed", error=str(exc))
        return {"status": "error", "detail": str(exc)}
    finally:
        # Only close what we opened ourselves -- an injected test client isn't ours to close.
        if owns_client and client is not None:
            client.close()


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
    # Milvus is sync/blocking (pymilvus) -- run off the event loop, like providers.py's _run_milvus.
    milvus_status = await asyncio.get_running_loop().run_in_executor(None, check_milvus)

    return {
        "api": {"status": "ok"},
        "db": db_status,
        "redis": redis_status,
        "worker": worker_status,
        "milvus": milvus_status,
    }


# ui's own trivial self-check, not the full aggregate above -- see ADR 0002.
ui_router = APIRouter()


@ui_router.get("/health")
async def ui_health() -> dict:
    """Deliberately trivial -- proves this container itself is up, nothing
    more. The real aggregate is `health()` above, on the api container."""
    return {"status": "ok"}
