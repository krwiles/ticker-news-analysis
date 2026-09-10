# Lesson 7 plan — the provider-fetch job

Scope: what `NOTES.md`'s lesson 7 describes, expanded during planning once real EDGAR/Finnhub research surfaced
a real need for a `companies` cache table too (see below — not scope creep, EDGAR fetching can't work without
a CIK, and re-deriving it from SEC's full ticker list on every search is wasteful). Builds on lesson 6's
`Headline` model (done). Feeds lesson 8 (`/api/search` enqueues this job) and lesson 9 (tests this job's logic
directly, no ARQ machinery needed — see why below). Not in scope here: the HTTP endpoint (lesson 8), tests
(lesson 9).

## What gets built

**0. New migration** — one file, three changes:
- New table `companies`: `ticker TEXT PRIMARY KEY`, `cik TEXT` (nullable), `company_name TEXT` (nullable).
  Created *before* the FK below, since the FK needs it to exist first.
- `headlines` gets two new nullable columns: `outlet TEXT` (original publisher, e.g. `"Yahoo"`) and
  `summary TEXT` (a short blurb, shown under the headline in the UI) — both added after live-checking
  Finnhub's real response revealed a real need for them, not planned when lesson 6 shipped.
- `headlines.ticker` gets a real foreign key: `REFERENCES companies(ticker)`.

None of this edits lesson 6's already-applied migration — it's additive, a new `dbmate` file.

**1. New dependency**: `httpx` added to `backend/pyproject.toml` (settled by ADR 0005 — same client FastAPI's
own test tooling uses).

**2. `Settings` gets two new fields** (`config.py`) — deferred here on purpose since this is the first lesson
that actually needs them:
- `finnhub_api_key: str`
- `sec_edgar_user_agent: str`

Both already sit in `.env`/`.env.example`, unused until now.

**3. `backend/src/ticker_backend/providers.py`** (new, flat module per the earlier "one flat module, not a
package" decision) — four functions, all framework-agnostic (no ARQ `ctx`, no FastAPI — plain `async def`s
that lesson 9 can call and test directly without spinning up a worker or a server):

- `get_company(ticker: str, session_factory=async_session_factory) -> CompanyInfo` — the ticker → CIK/name
  cache-or-lookup step. Checks `companies` first; if missing, fetches `company_tickers.json` and looks for a
  match. **If found**, upserts `companies` with `cik` and `company_name` both populated in one step (the
  lookup gives both at once — no null-then-backfill needed here). **If not found**, returns a "no CIK" result
  *without writing anything yet* — whether a row eventually gets created depends on what Finnhub returns,
  decided later in the orchestrator, not here.
- `fetch_edgar_filings(client: httpx.AsyncClient, cik: str, ticker: str) -> list[dict]` — takes the already-
  resolved `cik` (not looked up internally), calls `data.sec.gov/submissions/CIK{cik:0>10}.json`, sends
  `User-Agent: settings.sec_edgar_user_agent` (required by SEC's usage policy). Verified live against AAPL's
  real filings:
  - The response is a **dict of parallel arrays** (`recent["form"][i]`, `recent["filingDate"][i]`, etc.), not a
    list of objects like Finnhub — normalization has to zip across them.
  - **Filtered to an allowlist**: `10-K`, `10-Q`, `8-K`, `S-1`, `DEF 14A`. The raw feed is dominated by routine
    Form 3/4/5 ownership filings (verified live — AAPL's three most recent filings were all Form 3/4) that
    would otherwise flood the results. Not an exhaustive list of every "real" filing type (e.g. `6-K`, `S-3`,
    `10-K/A` amendments aren't included) — a reasonable v1 cut, not exhaustively researched, worth revisiting
    if a real gap shows up in practice.
  - **No natural title** — constructed from `form` + `primaryDocDescription` (e.g. `"Form 4 — Statement of
    Changes in Beneficial Ownership"`).
  - **`published_at` comes from `acceptanceDateTime`** (a real timestamp), not `filingDate` (a bare date, no
    time) — the Eastern-midnight Today/Recent boundary needs actual time-of-day.
  - **URL is constructed**, not given directly: `https://www.sec.gov/Archives/edgar/data/{cik}/
    {accessionNumber-without-dashes}/{primaryDocument}` — verified live, resolves with a real `200 OK`.
  - `outlet=None`, `summary=None` always — EDGAR is the authoritative source, not an aggregator; confirmed live,
    nothing in the response resembles either concept.
- `fetch_finnhub_news(client: httpx.AsyncClient, ticker: str) -> list[dict]` — calls Finnhub's company-news
  endpoint (`GET /company-news?symbol=...&from=...&to=...&token=settings.finnhub_api_key` — auth is a query
  param, verified live) with `category="news"`, `provider="finnhub"`. Maps Finnhub's own `source` field to
  `outlet` (e.g. `"Yahoo"`) and `summary` directly to `summary` — both verified against a real response.
  Finnhub's `related` field is **not** used to filter results — verified live that it isn't a reliable "this
  article is genuinely about the requested ticker" signal (an NVDA-focused article came back tagged
  `related: "AAPL"`); accepted as noise per spec 0001's Non-goals, not filtered.
- `fetch_and_persist_headlines(ticker: str, session_factory=async_session_factory) -> dict` — the orchestrator
  spec 0001 and ADR 0004 describe:
  1. Calls `get_company(ticker, session_factory)` to resolve (or attempt to resolve) the CIK.
  2. Opens one `httpx.AsyncClient`, runs the two provider fetches via `asyncio.gather(..., return_exceptions=True)`
     — concurrent, one provider's exception doesn't cancel the other's in-flight call. If no CIK was resolved,
     EDGAR contributes zero filings (not an error — just nothing to fetch) rather than being called at all.
  3. **Finalizes the `companies` row**: if `get_company` found no CIK but Finnhub returned at least one real
     headline, upsert `companies` now with `cik`/`company_name` left null — a legitimate state (an EDGAR-
     uncovered but real, Finnhub-covered ticker), not a placeholder to fix later. If *neither* provider
     returned anything, no `companies` row is created at all. This sequencing is what keeps `companies` free of
     rows for typos/nonexistent tickers without a separate cleanup job.
  4. Only now upserts `Headline` rows (via `postgresql.insert(...).on_conflict_do_update(index_elements=["url"])`,
     the dedup-by-URL mechanism spec 0001 requires) — safe to do because a `companies` row is guaranteed to
     exist by this point if there's any headline that needs to reference it via the FK.
  5. Returns `{"status": "success" | "partial_failure" | "complete_failure", "providers": {"edgar": "ok"|"error",
     "finnhub": "ok"|"error"}, "headline_count": N}` — the exact shape lesson 8's endpoint will read.

  **`session_factory` is a parameter with a default, not a direct import of `db.py`'s `async_session_factory`.**
  Same reasoning as `Depends()` in FastAPI routes, applied where `Depends()` itself doesn't reach — there's no
  FastAPI request cycle inside an ARQ job. Real callers (the worker wrapper below) never pass it explicitly and
  get the real database; lesson 9's tests pass a test-database session factory instead, without needing to
  monkeypatch an import. This is dependency injection without a framework — just "accept it as an argument"
  instead of "reach out and import a global."

**4. `worker.py` gets a thin ARQ wrapper**, not the business logic itself:
```python
async def fetch_headlines_job(ctx: dict, ticker: str) -> dict:
    return await fetch_and_persist_headlines(ticker)

class WorkerSettings:
    functions = [fetch_headlines_job]   # new — first non-cron job this project has
    cron_jobs = [cron(heartbeat, second=set(range(0, 60, 5)))]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
```
Keeping `fetch_and_persist_headlines` itself free of `ctx`, and taking `session_factory` as an injectable
parameter rather than importing one, is what makes it callable directly from a test (lesson 9) or, later, from
a `cron_jobs` entry for the future watchlist feature — without any ARQ plumbing, or a hardcoded database, in
the way.

## Verification (before moving to lesson 8)

Same spirit as the heartbeat's own verification and the multi-worker dedup experiment: enqueue the real job
against the real running stack and check Postgres directly, rather than trusting it because the code looks
right.

1. Rebuild + restart `worker` (and `api`, since `providers.py`/`config.py` changes are picked up on rebuild).
2. From a Python shell against the running stack: `await redis.enqueue_job("fetch_headlines_job", "AAPL")`,
   then poll the job's result via ARQ's `Job(job_id, redis).result(timeout=...)`.
3. Confirm the result dict looks right (`status: "success"`, both providers `"ok"`, a real `headline_count`).
4. Query `companies` directly — confirm a real AAPL row exists with the correct `cik` (`320193`) and
   `company_name` (`"Apple Inc."`).
5. Query `headlines` directly — confirm real AAPL rows exist with correct `category`/`provider` values,
   non-null `published_at`, correctly-filtered filing types (no Form 3/4/5 among them), and — for
   Finnhub-sourced rows — a real `outlet` (e.g. `"Yahoo"`, not `"finnhub"`) and a non-empty `summary`.
6. Re-enqueue the same ticker a second time — confirm the `headlines` row count *doesn't* grow (upsert-by-URL
   dedup holding across two real fetches), and that `companies` still has exactly one AAPL row (not a second
   lookup creating a duplicate or overwriting with different data).
7. Enqueue a fake/nonsense ticker (e.g. `"ZZZQX"`) — confirm **no** `companies` row and **no** `headlines` rows
   get created, proving the no-garbage-rows sequencing actually holds, not just in theory.

## Open items this plan surfaces (flagging rather than deciding silently)

- Neither provider's exact rate limits have been re-confirmed recently; Non-goals already accepts this as fine
  at personal-project scale, just noting it's still an assumption, not a verified fact.
- Whether Finnhub's `url` (a Finnhub-hosted link, not the original outlet's page) resolves correctly for a
  server-side fetch (not just a browser click) is unconfirmed — relevant later if spec 0002 ever follows this
  URL to fetch full article content for `raw_content`. Not blocking now, since `raw_content` isn't populated in
  this pass anyway.
- The filing-type allowlist (`10-K`/`10-Q`/`8-K`/`S-1`/`DEF 14A`) is a reasonable v1 cut, not an exhaustive
  survey of every SEC form type that could plausibly count as "news" — worth revisiting if real use surfaces a
  gap (e.g. `6-K` for foreign private issuers).
