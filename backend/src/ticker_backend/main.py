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

    # Explicit three-way match, not `if api ... else ui`: `worker` mode should
    # never reach this function at all — it's selected entirely by
    # docker-compose's `command:` override, which replaces this image's
    # default CMD outright (see docs/adr/0001). An `if/else` would silently
    # treat a misconfigured worker container (or any typo'd APP_MODE) as `ui`
    # instead of failing loudly. This fails loudly instead.
    match settings.app_mode:
        case "api":
            log.info("app.mode", mode="api")
            # The status page is served by the ui container (a different
            # origin, same host different port) and fetches this container's
            # /health directly — a real cross-origin request, not a
            # same-origin one. Only ui's own origin is allowed in. See
            # docs/adr/0002-cors-over-shared-health-router.md for why this
            # beats the alternative (ui exposing the same aggregate router
            # api does).
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
            # Trivial per-container liveness only — the full aggregate lives
            # on the api container exclusively, fetched cross-origin by the
            # page.
            app.include_router(ui_health_router)
            # app.frontend() (FastAPI 0.138+) serves the built SPA as
            # low-priority routes: normal path operations above are always
            # checked first, regardless of registration order, and it falls
            # back to index.html for client-side routes. Replaces a
            # hand-rolled StaticFiles(html=True) mount, which relied on
            # registration order to avoid shadowing routes.
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
