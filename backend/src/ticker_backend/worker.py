"""ARQ worker entrypoint (`worker` mode — see config.app_mode).

Runs no business jobs yet. The only thing it does is prove it's alive by
writing a heartbeat to Redis every 5 seconds, which the api container's
/health endpoint reads to report worker status on the skeleton page.
"""

import time

import structlog
from arq import cron
from arq.connections import RedisSettings

from ticker_backend.config import settings
from ticker_backend.health import WORKER_HEARTBEAT_KEY
from ticker_backend.logging import configure_logging

configure_logging()
log = structlog.get_logger()


async def heartbeat(ctx: dict) -> None:
    await ctx["redis"].set(WORKER_HEARTBEAT_KEY, str(time.time()))
    log.info("worker.heartbeat")


class WorkerSettings:
    cron_jobs = [cron(heartbeat, second=set(range(0, 60, 5)))]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
