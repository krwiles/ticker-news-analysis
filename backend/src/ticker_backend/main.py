"""FastAPI app factory — becomes the `ui` or `api` container depending on
`app_mode`. See docs/adr/0001-single-image-multi-mode-containers.md.
"""

from pathlib import Path

import structlog
from fastapi import FastAPI

from ticker_backend.config import settings
from ticker_backend.health import router as health_router
from ticker_backend.logging import configure_logging

configure_logging()
log = structlog.get_logger()

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="ticker-news-analysis", version="0.1.0")
    app.include_router(health_router)

    if settings.app_mode == "ui":
        log.info("app.mode", mode="ui", static_dir=str(STATIC_DIR))
        # app.frontend() (FastAPI 0.138+) serves the built SPA as low-priority
        # routes: normal path operations above are always checked first,
        # regardless of registration order, and it falls back to index.html
        # for client-side routes. Replaces a hand-rolled StaticFiles(html=True)
        # mount, which relied on registration order to avoid shadowing /health.
        app.frontend("/", directory=STATIC_DIR)
    else:
        log.info("app.mode", mode=settings.app_mode)

    return app


app = create_app()
