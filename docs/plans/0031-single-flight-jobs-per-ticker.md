# Plan 0031 — single-flight fetch and sentiment jobs per ticker

Not a spec-driven feature — a concurrency fix, prompted by the user asking whether two simultaneous requests
for the same ticker would race, with multi-user accounts and background ticker fetching as the planned
direction. The architectural decision and its rejected alternatives are in
`docs/adr/0015-single-flight-jobs-per-ticker.md`; this plan is just the how.

## What the investigation found (by reading code — the baseline section below says which parts held up live)

- Headline upserts are safe under concurrency (`ON CONFLICT (url)`, only one writer sees a row as new).
- A ticker's first-ever lookup can crash the losing request: both jobs miss the `companies` cache and both
  `session.merge(Company(...))` → `INSERT`; the unhandled `IntegrityError` becomes `complete_failure`.
- Two concurrent sentiment jobs double-call OpenAI and double-count into `Story.sentiment_score_count` /
  average. This is the most realistic trigger: sentiment is slow (60-100+ seconds) and every `/api/search`
  fires a new one, so any Refresh during that window overlaps.

## Baseline — measured live on 2026-09-21, before any code change

Two simultaneous `curl /api/search?ticker=ORCL` calls against the running stack (ORCL not yet in `companies`).

**Run 1 — a fresh ticker.**
- The two requests disagreed: one returned `complete_failure` (`providers: {}`, zero stories), the other
  `success`. The worker log shows why — one `fetch_headlines_job` died with
  `UniqueViolationError: duplicate key value violates unique constraint "companies_pkey"`. That's the
  `get_company` cache-miss → `merge` → `INSERT` race, **confirmed live, not just a code-reading guess**.
- Two `sentiment_job('ORCL')` runs overlapped for ~65s each.
- Story aggregates nonetheless matched (131/131 Stories, 112 = 112) — by luck of timing, not by design: the
  first sentiment job started before the winning fetch finished grouping, so its loaded headlines still had
  `story_id = None` and `_persist_result` skipped the aggregate update. Only the second job folded scores in.

**Run 2 — ORCL's sentiment reset (`sentiment_*` columns NULLed, Story aggregates zeroed), then the same two calls.**
- Two fetch jobs and two overlapping sentiment jobs (58.4s and 64.1s), both over fully grouped headlines.
- `SUM(stories.sentiment_score_count)` = **224** against **112** headlines actually at `ok` — every score
  folded in twice; **105 of 131 Stories inflated**, 26 matching, 0 undercounted. Permanent, too: an `ok`
  headline is never re-scored, so nothing ever corrects the count.

After the fix, Run 2's exact procedure should give 112 = 112 and one job of each kind.

## Decisions (approved by the user)

1. **A second request joins the in-flight fetch and shares its result** — it doesn't queue behind it and
   repeat the fetch. Chosen with multi-user and background fetching in mind.
2. Deterministic ARQ job IDs: `fetch_headlines:{TICKER}` and `sentiment:{TICKER}` (ticker already uppercased
   by the caller).
3. `keep_result` = 5 seconds for the fetch job (must be > 0 or a joiner can hit `ResultNotFound`), 0 for
   sentiment.
4. No `_expires` on enqueue — see ADR 0015's Consequences for why.

## What gets built

- **`backend/src/ticker_backend/jobs.py`** (new): the one place job IDs and the enqueue-or-join rule live, so
  the future background refresher reuses it.
  - `fetch_job_id(ticker)` / `sentiment_job_id(ticker)`, and the `FETCH_RESULT_TTL_SECONDS = 5` constant.
  - `enqueue_or_join_fetch(arq_redis, ticker, job_factory=Job)` — enqueues with the deterministic ID; on `None`,
    returns `job_factory(job_id, redis=arq_redis)`. Always returns something awaitable via `.result(timeout=...)`.
    `job_factory` is injectable, same pattern as ADR 0012's `milvus=None` — tests pass a fake, no monkeypatching.
  - `enqueue_sentiment(arq_redis, ticker)` — enqueues with the deterministic ID and ignores a `None` return.
- **`search.py`**: `search()` calls those two helpers instead of the raw `enqueue_job(...)` calls. Everything
  else in the function (timeout handling, `complete_failure` on any exception, the response shape) is unchanged.
- **`worker.py`**: `WorkerSettings.functions` becomes
  `[func(fetch_headlines_job, keep_result=FETCH_RESULT_TTL_SECONDS), func(sentiment_job, keep_result=0)]`.
  `func()` defaults the registered name to the function's `__qualname__`, so the string `search.py` enqueues
  by is unchanged.

Every new function gets the block-level comments per `CODING_STANDARDS.md`.

## Tests — 8 new in `backend/tests/test_jobs.py`, plus one extended assertion (78 → 86 passing)

The join behavior is tested at the **helper** level, not through `/api/search`: the endpoint tests can't inject a
`job_factory`, and a real ARQ `Job` built on a fake Redis fails the moment it calls `.result()`. The fake Redis
mimics the one ARQ rule this relies on — the first enqueue of a job ID claims it, later ones get `None`.

- Fetch and sentiment IDs are per-ticker, case-insensitive (`aapl` = `AAPL`), and never collide with each other.
- First caller enqueues by name under the deterministic ID and never takes the join path.
- A caller arriving while the ID is taken joins the existing job and awaits *its* result.
- Two callers via `asyncio.gather`: exactly one real enqueue, one join, both see the same result.
- A different ticker is not blocked by an in-flight one.
- `enqueue_sentiment` uses the deterministic ID and tolerates ARQ's `None`.
- `WorkerSettings.functions` registers fetch with `keep_result` = 5s and sentiment with 0 — the regression
  guard for the "Refresh returns an hour-old result" failure, which no other test would catch.
- In `test_search_endpoint.py`, the existing fire-and-forget test now also asserts `search()` sends
  `fetch_headlines:AAPL` and `sentiment:AAPL` as the job IDs.

**Proved able to fail:** deliberately broke three things and watched the right tests go red each time —
dropping `.upper()` from the ID (2 failures), making the join return `None` (2 failures), and setting fetch's
`keep_result=0` (1 failure) — then restored the files byte-for-byte and confirmed 8/8 green.

A real-Redis test of ARQ's own uniqueness is deliberately not added — CI has no Redis service, and that
behavior is ARQ's, not this code's. The live checks below cover it against the real stack.

## Live verification — after the change (same stack, rebuilt with `docker compose up --build -d`)

1. **Run 2's exact procedure, repeated** (ORCL sentiment reset, two simultaneous requests): both responses
   `success` with identical `providers`/`grouping`; the worker ran **one** `fetch_headlines:ORCL` job and **one**
   `sentiment:ORCL` job (the deterministic IDs now show up in ARQ's own log lines);
   `SUM(sentiment_score_count)` = **112** against **112** `ok` headlines, **0 of 131** Stories inflated
   (baseline: 224 vs 112, 105 inflated).
2. **The 5-second window:** a request right after another finished returned in 11 ms with no new fetch (it
   shared the kept result); a request 7 seconds later ran a genuinely new fetch — so `keep_result` isn't pinning
   stale results.
3. **Different tickers stay parallel:** simultaneous `AAPL` and `MSFT` searches started their fetch jobs in the
   same second and overlapped — nothing over-serialized.
4. The rebuild recreated the `db` and `redis` containers; Postgres's named volume kept all data (3,958 headlines).

## Out of scope (noticed, deliberately not fixed here)

- Global rate limiting across tickers (Finnhub free tier, OpenAI) and the worker's `max_jobs=10` ceiling — real
  at multi-user scale, a separate decision.
- The background refresher itself — this only makes sure it can call `jobs.py` and coalesce. Noted for it: it
  should also enqueue `sentiment_job` through `enqueue_sentiment` after its fetch.
- Seen in Run 1's timing, not addressed: `search()` enqueues `sentiment_job` even when the fetch job timed out
  or failed, so a sentiment job can start while a fetch is still grouping in the background. Its headlines
  then have `story_id = None`, and its scores never reach the Story aggregate — and since `ok` is never
  re-scored, they never will. Needs a fix of its own (e.g. re-reading `story_id` at write time).
- Row-level locking on `Story.record_sentiment()` — unneeded while sentiment is single-flight per ticker; see
  the ADR's last consequence.
- Noticed while reading, not verified: `headlines.url` is globally unique but `ticker` isn't in the upsert's
  `set_` list, so an article shared by two tickers' feeds is attributed only to whichever ticker fetched it
  first. A spec-level question, not a concurrency bug.
