"""FastAPI app factory — becomes the `ui` or `api` container depending on
`app_mode`. See docs/adr/0001-single-image-multi-mode-containers.md.
"""

from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ticker_backend.config import settings
from ticker_backend.health import router as health_router
from ticker_backend.logging import configure_logging

configure_logging()
log = structlog.get_logger()

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="ticker-news-analysis", version="0.1.0")

    # Registered before the static mount below so it isn't shadowed by it.
    app.include_router(health_router)

    if settings.app_mode == "ui":
        log.info("app.mode", mode="ui", static_dir=str(STATIC_DIR))
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    else:
        log.info("app.mode", mode=settings.app_mode)

    return app


app = create_app()
