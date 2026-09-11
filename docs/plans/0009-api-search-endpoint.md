# Lesson 9 plan — the `/api/search` endpoint

Scope: `NOTES.md`'s lesson 9. Wires lesson 7's job to an actual HTTP route. Builds on: `providers.py`'s
`fetch_and_persist_headlines` (done), the `Headline`/`Company` models (done), ADR 0004 (job enqueue-and-await),
and spec 0001's Outputs section (route contract, Today/Recent split, status model). Not in scope: tests (lesson
10), any frontend code (lessons 11–13).

## What this endpoint actually does — two steps, not one

Easy to under-specify: `fetch_and_persist_headlines`'s job result is just a summary
(`{"status", "providers", "headline_count"}`) — it doesn't hand back the actual headlines, because it already
persisted them to Postgres. So `/api/search` does two things in sequence, not one:

1. **Enqueue and await the fetch job** — ensures Postgres has fresh data for this ticker before step 2 reads it.
2. **Query Postgres directly** for that ticker's headlines from the past week, split into Today/Recent, and
   build the response — combining the job's status info with the actual data now sitting in the database.

A job timeout doesn't skip step 2 — it's still worth returning whatever Postgres already has (possibly from an
earlier successful search) rather than nothing, while honestly reporting `complete_failure` so the UI shows the
right status. Graceful degradation, not silence.

## What gets built

**1. `/health` moves to `/api/health`** — for consistency, per spec 0001's `/api/`-prefix decision. Both
`health_router`'s and `ui_router`'s path operations get the new prefix. `frontend/src/health.ts`'s fetch URL
needs the matching update (out of scope for the backend lesson itself, but flagged so it doesn't get missed —
picked up properly once the frontend lessons start).

**2. `Settings` gets one new field**: `job_timeout_seconds: int = 10` (`config.py`) — the number decided during
the grilling round, now actually wired in instead of just written in a doc.

**3. `main.py`'s `create_app()` gets a conditional lifespan**, scoped to `api` mode only (`ui` never enqueues
jobs, no reason for it to hold a Redis pool open):
```python
@asynccontextmanager
async def api_lifespan(app: FastAPI):
    app.state.arq_redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    yield
    await app.state.arq_redis.aclose()

def create_app() -> FastAPI:
    lifespan = api_lifespan if settings.app_mode == "api" else None
    app = FastAPI(title="ticker-news-analysis", version="0.1.0", lifespan=lifespan)
    match settings.app_mode:
        ...
```
The ARQ Redis pool is created **once, at app startup** — same reasoning as `db.py`'s `engine`: a connection pool
belongs to the app's lifetime, not to any one request.

**4. A `get_arq_redis` dependency**, the idiomatic FastAPI DI point this project hasn't used yet (`Depends()`
has come up in conversation, never in actual code until now):
```python
async def get_arq_redis(request: Request) -> ArqRedis:
    return request.app.state.arq_redis
```
Real requests get the pool `api_lifespan` created; lesson 10's tests override this dependency
(`app.dependency_overrides[get_arq_redis]`) to avoid needing a real Redis connection for endpoint tests that
don't care about the job layer.

**5. New `backend/src/ticker_backend/search.py`** (one file per feature, matching `health.py`'s shape — router
and logic together):

- `split_today_recent(headlines: list[Headline], now: datetime) -> tuple[list[dict], list[dict]]` — a pure
  function, **`now` is a parameter, not `datetime.now()` called internally** — same injection principle as
  `providers.py`'s `client`/`session_factory`, and specifically what lets lesson 10 unit-test the Eastern-
  midnight/DST boundary against a fixed fake "now" instead of waiting for real midnight. Converts `now` and
  each `published_at` to `America/New_York` (a real IANA zone, not a fixed offset — DST-aware, per spec 0001),
  compares calendar dates: today's date → `today` list, the rest of the past week → `recent` list, both
  newest-first.
- `@router.get("/api/search")` `async def search(ticker: str, arq_redis: ArqRedis = Depends(get_arq_redis), session_factory=async_session_factory) -> dict`:
  1. Uppercase `ticker` (matches `providers.py`'s own normalization, so the query in step 3 finds what the job
     in step 2 just wrote).
  2. `job = await arq_redis.enqueue_job("fetch_headlines_job", ticker)`, then
     `await job.result(timeout=settings.job_timeout_seconds)`. Catch `asyncio.TimeoutError` — treat as
     `status="complete_failure"`, `providers={}`, and fall through to step 3 anyway rather than returning early.
  3. Query `headlines` for this ticker, `published_at` within the past week, via `session_factory`.
  4. `split_today_recent(...)`, build the response:
     ```json
     {"ticker": "AAPL", "status": "success", "providers": {"edgar": "ok", "finnhub": "ok"},
      "today": [...], "recent": [...]}
     ```
     Each entry: `title`, `url`, `category`, `provider`, `outlet`, `summary`, `published_at`. No Pydantic
     response model introduced — plain `dict`, same as `health.py`, consistent with the pattern already
     established rather than a new one for this one endpoint.

**6. `main.py`'s `api` branch** gets `app.include_router(search_router)` alongside the existing
`app.include_router(health_router)`.

## Verification

1. Rebuild + restart `api` (and confirm `worker` doesn't need changes — it doesn't, `fetch_headlines_job`
   already exists from lesson 7).
2. `curl "http://localhost:8000/api/search?ticker=AAPL"` — confirm a real response: correct `status`, real
   `today`/`recent` arrays reflecting what's actually in Postgres, correctly split.
3. `curl http://localhost:8000/api/health` — confirm the rename didn't break anything; the old bare `/health`
   should now 404.
4. Search a ticker with no existing data — confirm the job runs, Postgres gets populated, and the *same
   request* returns the freshly-fetched data (not a second search needed).
5. Search again immediately — confirm it still works (dedup from lesson 7 holding, no duplicate rows, response
   still correct).
6. If feasible, simulate a timeout (e.g., temporarily lower `job_timeout_seconds` to something the real fetch
   can't beat) to confirm `complete_failure` + graceful fallback to existing Postgres data — real proof, not
   just trusting the exception-handling code reads correctly.

## Open items

- Whether `/api/search`'s query in step 3 should exclude `headlines` with no meaningful content (there
  shouldn't be any, given lesson 7's normalization always sets a title) — likely a non-issue, noting it as
  a real question rather than silently assuming.

**Resolved**: the "past week" query cutoff uses plain UTC — `published_at >= datetime.now(timezone.utc) -
timedelta(days=7)`, a precise instant, not a day-truncated one. Decided against Eastern time for this specific
bound: being off by a few hours at the *old* edge of a week-long window doesn't matter, and a plain instant
cutoff (rather than truncating to a calendar day) guarantees the newest possible headlines are always included
right up to the current moment — simplest option that still satisfies "always show the most recent news."
Eastern time stays reserved for the Today/Recent split specifically, where the market-day framing is the actual
point.
