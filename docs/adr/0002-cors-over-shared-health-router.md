# CORS over a shared health router

The `ui` container's `create_app()` used to unconditionally include the same `/health` router the `api` container uses — an accident of `include_router()` not being gated by `app_mode`, not a decision. It meant the full system-aggregate health check (db, redis, worker) was reachable through the `ui` container's port too, and — because the frontend's health fetch was a relative URL — the status page was actually calling the `ui` container's copy of it in the real docker-compose setup, not the `api` container at all.

The fix: each container reports only on what it actually is. `api` keeps the one full aggregate. `ui` gets its own trivial self-check (`{"status": "ok"}`) instead of a duplicate of the aggregate. The frontend now calls the `api` container's origin explicitly (`http://localhost:8000`) rather than a relative path, which makes this a genuine cross-origin request — so `api` adds `CORSMiddleware`, allowing in only the known `ui` origin.

## Considered options

- **Keep the aggregate router shared across both modes** (status quo): simplest, no CORS needed, but every container falsely claims to speak for the whole system's health, and the same problem would recur for any future business router included the same unconditional way — the `ui` container would become a full shadow copy of the api surface.
- **A reverse proxy at the `ui` edge** (forward `/health` and future `/api/*` calls to the `api` container transparently, keeping the browser on one origin): the "textbook" production pattern, but real infrastructure to build and maintain for a project with exactly one endpoint so far.
- **CORS** (chosen): one `CORSMiddleware` call, restricted to the single known `ui` origin. Standard for exactly this shape — a browser-served SPA on one origin calling a separately-hosted API on another — and proportionate to the project's current size.

## Consequences

- The frontend now hardcodes the `api` origin (`frontend/src/config.ts`) rather than using a relative path. Revisit if this project ever targets a real deployment beyond local dev (would need to become env-driven).
- The webpack dev server's proxy config (which existed only to dodge this same cross-origin issue for `npm run dev`) is now unnecessary and was removed — CORS covers both the dev-server and docker-compose cases identically.
- Every future business router should follow the same api-only pattern this ADR establishes, not the accidental shared-router pattern it replaces.
