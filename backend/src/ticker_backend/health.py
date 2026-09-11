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

# The worker has no server of its own — it proves it's alive by writing a
# timestamp here on a cron job. If this key is missing or too old, the
# worker is down or wedged.
WORKER_HEARTBEAT_KEY = "worker:heartbeat"
WORKER_STALE_AFTER_SECONDS = 30


async def check_db() -> dict:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001 - report any failure, don't crash the health check
        log.warning("health.db_check_failed", error=str(exc))
        return {"status": "error", "detail": str(exc)}


async def check_redis() -> tuple[dict, Redis | None]:
    client = Redis.from_url(settings.redis_url)
    try:
        await client.ping()
        return {"status": "ok"}, client
    except Exception as exc:  # noqa: BLE001
        log.warning("health.redis_check_failed", error=str(exc))
        await client.aclose()
        return {"status": "error", "detail": str(exc)}, None


async def check_worker(client: Redis | None) -> dict:
    if client is None:
        return {"status": "unknown", "detail": "redis unavailable"}

    raw = await client.get(WORKER_HEARTBEAT_KEY)
    if raw is None:
        return {"status": "error", "detail": "no heartbeat recorded yet"}

    age_seconds = round(time.time() - float(raw), 1)
    if age_seconds > WORKER_STALE_AFTER_SECONDS:
        return {"status": "stale", "age_seconds": age_seconds}
    return {"status": "ok", "age_seconds": age_seconds}


@router.get("/api/health")
async def health() -> dict:
    db_status = await check_db()
    redis_status, redis_client = await check_redis()
    worker_status = await check_worker(redis_client)
    if redis_client is not None:
        await redis_client.aclose()

    return {
        "api": {"status": "ok"},
        "db": db_status,
        "redis": redis_status,
        "worker": worker_status,
    }


# ui mode gets its own router with a trivial self-check — NOT the full
# aggregate above. Each container should only report on what it actually is;
# aggregating the whole system's health belongs to the one container that's
# meant to be asked for it. See docs/adr/0002-cors-over-shared-health-router.md.
ui_router = APIRouter()


@ui_router.get("/health")
async def ui_health() -> dict:
    return {"status": "ok"}
