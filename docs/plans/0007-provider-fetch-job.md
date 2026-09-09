# Lesson 7 plan — the provider-fetch job

Scope: exactly what `NOTES.md`'s lesson 7 describes. Builds on lesson 6's `Headline` model (done). Feeds
lesson 8 (`/api/search` enqueues this job) and lesson 9 (tests this job's logic directly, no ARQ machinery
needed — see why below). Not in scope here: the HTTP endpoint (lesson 8), tests (lesson 9).

## What gets built

**1. New dependency**: `httpx` added to `backend/pyproject.toml` (settled by ADR 0005 — same client FastAPI's
own test tooling uses).

**2. `Settings` gets two new fields** (`config.py`) — deferred here on purpose since this is the first lesson
that actually needs them:
- `finnhub_api_key: str`
- `sec_edgar_user_agent: str`

Both already sit in `.env`/`.env.example`, unused until now.

**3. `backend/src/ticker_backend/providers.py`** (new, flat module per the earlier "one flat module, not a
package" decision) — three functions, all framework-agnostic (no ARQ `ctx`, no FastAPI — plain `async def`s
that lesson 9 can call and test directly without spinning up a worker or a server):

- `fetch_edgar_filings(client: httpx.AsyncClient, ticker: str) -> list[dict]` — calls SEC EDGAR's full-text
  search, sends `User-Agent: settings.sec_edgar_user_agent` (required by SEC's usage policy), normalizes each
  result into a `Headline`-shaped dict (`ticker`, `title`, `url`, `category="filing"`, `provider="sec_edgar"`,
  `published_at`, `raw_content`). Catches its own request/parse failures and raises a typed exception rather
  than letting a malformed response crash silently — the orchestrator (next) decides what a failure here means.
- `fetch_finnhub_news(client: httpx.AsyncClient, ticker: str) -> list[dict]` — same shape, calls Finnhub's
  company-news endpoint with `settings.finnhub_api_key`, `category="news"`, `provider="finnhub"`.
- `fetch_and_persist_headlines(ticker: str) -> dict` — the orchestrator spec 0001 and ADR 0004 describe:
  - Opens one `httpx.AsyncClient`, runs both fetch functions via `asyncio.gather(..., return_exceptions=True)`
    — concurrent, and one provider's exception doesn't cancel the other's in-flight call (this is *why*
    `return_exceptions=True` matters here, not just `gather` alone).
  - For each provider that succeeded: upserts its normalized rows into `headlines` via SQLAlchemy's
    `postgresql.insert(...).on_conflict_do_update(index_elements=["url"], ...)` — the actual dedup-by-URL
    mechanism spec 0001 requires, using `db.py`'s shared `async_session_factory`.
  - Returns `{"status": "success" | "partial_failure" | "complete_failure", "providers": {"edgar": "ok"|"error",
    "finnhub": "ok"|"error"}, "headline_count": N}` — this is the exact shape lesson 8's endpoint will read to
    build its success/partial/complete-failure response.

**4. `worker.py` gets a thin ARQ wrapper**, not the business logic itself:
```python
async def fetch_headlines_job(ctx: dict, ticker: str) -> dict:
    return await fetch_and_persist_headlines(ticker)

class WorkerSettings:
    functions = [fetch_headlines_job]   # new — first non-cron job this project has
    cron_jobs = [cron(heartbeat, second=set(range(0, 60, 5)))]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
```
Keeping `fetch_and_persist_headlines` itself free of `ctx` is deliberate — it's what makes it callable directly
from a test (lesson 9) or, later, from a `cron_jobs` entry for the future watchlist feature, without any ARQ
plumbing in the way.

## Verification (before moving to lesson 8)

Same spirit as the heartbeat's own verification and the multi-worker dedup experiment: enqueue the real job
against the real running stack and check Postgres directly, rather than trusting it because the code looks
right.

1. Rebuild + restart `worker` (and `api`, since `providers.py`/`config.py` changes are picked up on rebuild).
2. From a Python shell against the running stack: `await redis.enqueue_job("fetch_headlines_job", "AAPL")`,
   then poll the job's result via ARQ's `Job(job_id, redis).result(timeout=...)`.
3. Confirm the result dict looks right (`status: "success"`, both providers `"ok"`, a real `headline_count`).
4. Query `headlines` directly in `psql` — confirm real AAPL rows exist with correct `category`/`provider`
   values and non-null `published_at`.
5. Re-enqueue the same ticker a second time — confirm the row count *doesn't* grow (upsert-by-URL dedup
   actually holding across two real fetches, not just in theory).

## Open items this plan surfaces (flagging rather than deciding silently)

- **EDGAR's actual full-text-search response shape** isn't verified yet — the exact JSON fields to normalize
  need a real request against EDGAR's API during implementation, not assumed from memory.
- **Finnhub's actual company-news response shape** — same caveat.
- Neither provider's exact rate limits have been re-confirmed recently; Non-goals already accepts this as fine
  at personal-project scale, just noting it's still an assumption, not a verified fact.
