# Fetch and sentiment jobs are single-flight per ticker, via deterministic ARQ job IDs

Status: accepted — extends `0004-fetch-runs-as-an-arq-job.md` and `0014-sentiment-analysis-technical-approach.md`

Every `/api/search` call enqueues a fresh `fetch_headlines_job` and a fresh `sentiment_job`, each with a random
ARQ job ID, and the worker runs up to 10 jobs concurrently (ADR 0014). So two requests for the same ticker
close together — a double-click, Refresh while a search is still running, two users, or (planned) a background
job refreshing tickers on a schedule — run two full jobs against the same ticker at the same time.

Reading the code found what that costs today:

- **Fetch:** the `headlines` upsert (`ON CONFLICT (url)`) is already safe — the DB serializes the two writers
  and only one sees a headline as new. But both jobs still call EDGAR and Finnhub, and on a ticker's very first
  lookup both miss the `companies` cache and both `INSERT` the row, so the loser can fail with an unhandled
  primary-key violation.
- **Sentiment (the real problem):** both jobs read the same pending headlines, both call OpenAI, and both run
  `_persist_result` — last write wins on each headline, and `story.record_sentiment()` runs twice per headline,
  inflating the Story's count and skewing its average. Its read-modify-write is not row-locked across jobs.

Decision: at most one fetch job and one sentiment job per ticker exists at a time, enforced by giving each a
deterministic ARQ job ID (`fetch_headlines:{TICKER}`, `sentiment:{TICKER}`). ARQ's `enqueue_job` returns `None`
when a job with that ID is already queued, running, or has a stored result. A caller that gets `None` doesn't
fail and doesn't start a second job — it **joins** the existing one:

- **Fetch:** wraps the existing ID in an `arq.jobs.Job` and awaits its result exactly as the enqueuing caller
  would. Both callers get the same result from one fetch.
- **Sentiment:** nobody awaits it (fire-and-forget, ADR 0014), so `None` is simply ignored.

The ID scheme and the enqueue-or-join logic live in one small module (`jobs.py`) so every future caller — the
background refresher included — goes through the same code and coalesces with user-triggered fetches.

## Considered options

- **Rely on idempotent writes only** (rejected): the headline upsert already is; that's why fetch mostly
  survives today. It does nothing about duplicate provider calls, the `companies` insert race, or sentiment's
  double-counting.
- **A per-ticker `asyncio.Lock`/`Semaphore` in the worker process** (rejected): only works inside one process,
  and ADR 0014's "one worker is enough" is explicitly a today-only conclusion. It also *serializes* rather than
  *shares* — the second caller waits, then repeats the whole fetch.
- **A Postgres advisory lock per ticker** (rejected): works across processes, but same serialize-not-share
  problem, and holds a database connection for the whole duration of a network-bound job.
- **A hand-rolled Redis lock (`SET NX PX`) inside the job** (rejected): guards every caller, but needs its own
  expiry/renewal handling, and the loser still has to poll or fail. ARQ already ships an atomic version of
  this at the enqueue step.
- **Deterministic ARQ job IDs, joining the in-flight job** (chosen): atomic in Redis (WATCH/MULTI), so it holds
  across any number of api and worker processes, and shares one result instead of repeating work.

## Consequences

- **Result retention is now load-bearing.** ARQ keeps results for an hour by default, and `enqueue_job`
  returns `None` while a result exists — so unconfigured, Refresh would silently return an hour-old result.
  The fetch job is registered with a short `keep_result` (5 seconds); `Job.result()` also raises
  `ResultNotFound` if a job finishes with no stored result, so it can't be 0. Sentiment uses `keep_result=0`,
  since nobody reads it.
- **The 5-second window is a deliberate cooldown:** a Refresh within 5 seconds of a fetch finishing gets that
  fetch's result instead of a fresh one. It doubles as a small guard against hammering the providers.
- **Only same-ticker requests coalesce.** Different tickers still run in parallel, capped by the worker's
  `max_jobs=10`. Under real multi-user load that cap, the 10-second `/api/search` await, and the providers'
  global rate limits (Finnhub's free tier, OpenAI) are separate concerns this ADR does not solve.
- **The fetch result is shared across users because it doesn't depend on who asks** — it's public provider
  data. If a fetch ever becomes user-scoped, the job ID must include that scope or users would share results
  they shouldn't.
- **Sentiment enqueues can be dropped:** headlines that arrive while a sentiment job is mid-run aren't in its
  already-read pending list and wait for the next search or background tick. Spec 0005's existing retry rule
  ("whatever a later request's own scope happens to include") already permits this.
- **No `_expires` on enqueue.** A short expiry would let a second sentiment job start mid-run (they take
  60-100+ seconds, plan 0030), reopening the overlap. A hung job is already bounded by ARQ's 300-second
  `job_timeout`; a worker crash leaves the job queued to be retried, and joiners simply time out as they do today.
- **This guards the enqueue path only.** Code that calls `fetch_and_persist_headlines` directly (tests,
  one-off scripts) bypasses it — ADR 0004 already makes the ARQ job the one supported entry point.
- **It closes `story.record_sentiment()`'s cross-job lost update only while Stories stay per-ticker** — a Story
  belongs to one ticker, and one ticker has one sentiment job at a time. A second writer to the same Story
  would need real row-level locking (`SELECT ... FOR UPDATE`).
