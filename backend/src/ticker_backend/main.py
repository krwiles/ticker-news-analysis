"""FastAPI app factory — becomes the `ui` or `api` container depending on
`app_mode`. See docs/adr/0001-single-image-multi-mode-containers.md.
"""

from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ticker_backend.config import settings
from ticker_backend.health import router as health_router
from ticker_backend.health import ui_router as ui_health_router
from ticker_backend.logging import configure_logging
from ticker_backend.search import api_lifespan
from ticker_backend.search import router as search_router

configure_logging()
log = structlog.get_logger()

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"


def create_app() -> FastAPI:
    # Only api mode enqueues jobs -- ui has no reason to hold an ARQ Redis
    # pool open for its whole lifetime.
    lifespan = api_lifespan if settings.app_mode == "api" else None
    app = FastAPI(title="ticker-news-analysis", version="0.1.0", lifespan=lifespan)

    # Explicit match, not if/else -- worker mode should never reach here (it's
    # selected via docker-compose's command: override); this fails loudly instead of silently defaulting to ui.
    match settings.app_mode:
        case "api":
            log.info("app.mode", mode="api")
            # ui fetches this container's /health cross-origin -- only ui's own origin is allowed in (ADR 0002).
            app.add_middleware(
                CORSMiddleware,
                allow_origins=[settings.ui_origin],
                allow_methods=["*"],
                allow_headers=["*"],
            )
            app.include_router(health_router)
            app.include_router(search_router)
        case "ui":
            log.info("app.mode", mode="ui", static_dir=str(STATIC_DIR))
            # Trivial per-container liveness only -- the full aggregate lives on api, see above.
            app.include_router(ui_health_router)
            # app.frontend() (FastAPI 0.138+) serves the SPA as low-priority routes -- other
            # routes always match first, and it falls back to index.html for client-side routes.
            app.frontend("/", directory=STATIC_DIR)
        case other:
            raise RuntimeError(
                f"Unrecognized APP_MODE {other!r} reached create_app(). "
                "Expected 'api' or 'ui' — 'worker' mode should never call "
                "create_app() at all; it's selected entirely by "
                "docker-compose's command: override (see "
                "docs/adr/0001-single-image-multi-mode-containers.md). If "
                "this fired, that override was likely dropped or "
                "misconfigured."
            )

    return app


app = create_app()
