# Plan 0032 — reset stale "error" sentiment status when a retry actually starts

Not a planned lesson — a live bug-fix, same shape as plan 0030. Two bugs from `NOTES.md`'s "Known
issues & ideas" (2026-09-18 and 2026-09-21) turn out to share one root cause and one fix.

## Diagnosis

`compute_and_persist_sentiment`'s own query (`sentiment.py:_fetch_pending_headlines`) already
retries any headline whose `sentiment_status` is `NULL`, `'skipped'`, or `'error'` on every request
that triggers a new sentiment job — that part already works. The bug is what the *response* says
while that retry is running:

- **Frontend never notices a retry started.** `hasPendingSentiment` (`search.ts`) only treats
  `sentiment_status === null` as "still coming." A headline sitting at `'error'` from a previous
  run reads as permanently done, so a revisit that silently kicks off a real retry never resumes
  polling — its result lands in Postgres with nothing watching.
- **The UI shows "failed" for a headline that's actually mid-retry**, including right after a page
  refresh, for the same reason: nothing ever moves that row off `'error'` until the retry's own
  outcome overwrites it.

Both are the same symptom: `'error'` is used for two different things — "this run's automatic
retry (`sentiment.py`'s own `_fetch_with_retry`, one immediate retry) is exhausted" and "no retry
is even in flight right now" — and the response can't tell them apart. Resetting `'error'` back to
`NULL` at the moment a *new* sentiment job actually starts collapses that back to one state the
system already knows how to display: pending. No frontend change needed — `hasPendingSentiment`
and the existing pill/status components already treat `NULL` correctly.

**`'skipped'` isn't symmetric with `'error'` on its own.** `_mark_skipped` (`sentiment.py`) writes
`'skipped'` to *every* pending headline in one synchronous batch, before any network call, only
when `OPENAI_API_KEY` isn't configured — unlike `'error'`, which is set per-headline only after a
real, individually-timed OpenAI attempt fails. Whether the same staleness bug applies to
`'skipped'` depends on whether the key is configured *right now*:

- **Still not configured**: a new job run just re-confirms `'skipped'` on everything almost
  instantly, no real per-headline work happens in between. Nothing is genuinely "pending" to
  announce — resetting to `NULL` here would flash a misleading "pending" state for work that isn't
  actually happening.
- **Just became configured**: a `'skipped'` headline now gets a real attempt, spread out the same
  way `'error'`'s retries are — the identical staleness bug applies, and `hasPendingSentiment`
  doesn't treat `'skipped'` as pending either, so polling wouldn't resume.

So the reset is keyed on `settings.openai_api_key` at the moment a new job starts, not on status
value alone: when configured, both `'error'` and `'skipped'` rows reset to `NULL` (both are about
to get a real attempt); when not configured, neither resets (the impending job just re-batches
`'skipped'` near-instantly, with no real work to be "pending" about).

**Safety property**: the reset's `WHERE` only ever matches rows currently at `'error'`/`'skipped'`,
so it can never race against and overwrite a row the job just wrote `'ok'` to — `'ok'` isn't in its
target set, by construction, regardless of how the reset and the job's own writes interleave in time.

## Where the reset has to happen

`jobs.py:enqueue_sentiment` already knows the one fact that matters — ARQ's `enqueue_job` returns
`None` when a `sentiment:{TICKER}` job is already queued or running (ADR 0015), a real `Job`
otherwise. It's called today but its return value is discarded. That return value is exactly the
signal needed: reset only when a *new* job is actually about to run.

- **Timing**: `search()` enqueues sentiment, then immediately calls `_load_search_results` to build
  the response. The reset must happen in between — after confirming a new job started, before that
  query runs — or the response still shows the stale `'error'` row.
- **Overlap (ADR 0015)**: if `enqueue_sentiment` returns `None` (single-flight join, i.e. a job for
  this ticker is already running), skip the reset entirely. Resetting anyway would mark rows
  pending that nothing is about to retry — the already-running job already read its pending list
  before this request arrived.
- **`skipped` resets only when `OPENAI_API_KEY` is currently configured** (see the diagnosis above)
  — the same real-attempt-is-about-to-happen condition that governs `'error'`, checked once via
  `settings.openai_api_key` rather than inferred from status value alone.

## What's going to get built

- **`jobs.py`**: `enqueue_sentiment` returns `await arq_redis.enqueue_job(...)` directly instead of
  discarding it — type becomes `Job | None`. Docstring updated: callers now care whether a *new*
  job started (truthy) or one was already in flight (`None`), not just that a duplicate is
  tolerated.
- **`search.py`**: new `_reset_stale_sentiment_status(ticker, session_factory)` — a plain `UPDATE`
  scoped to this ticker and `RECENT_HEADLINES_WINDOW`, setting `sentiment_status` back to `NULL`
  for rows currently `'error'` or `'skipped'`. Gated entirely on `settings.openai_api_key`: does
  nothing (no query at all) when it's falsy, since an impending job with no key just re-batches
  everything to `'skipped'` almost instantly, with no real per-headline work in between to call
  "pending." Written inline here rather than imported from `sentiment.py`, matching lesson 28's
  own precedent: `search.py` (api mode) must not import `sentiment.py`, which pulls in
  `providers.py` and, transitively, `pymilvus`. `search()` captures `enqueue_sentiment`'s return
  value and calls the new helper only when it's not `None`, before `_load_search_results`.

No new ADR — this extends already-decided semantics (ADR 0012's status field, ADR 0015's
single-flight signal), it doesn't add a new architectural decision.

## Tests

- `test_jobs.py`: new test that `enqueue_sentiment` returns a truthy `Job` when nothing is already
  running (existing `test_sentiment_enqueue_uses_deterministic_id_and_tolerates_a_duplicate`
  already covers the `None` case).
- `test_search_endpoint.py`: extend `_FakeArqRedis` with a `sentiment_already_running: bool` flag
  so a test can make `enqueue_job("sentiment_job", ...)` return `None` specifically. New tests:
  an `'error'` headline resets to pending (`sentiment_status`/`sentiment_enum` both `None`) when a
  fresh sentiment job starts and the key is configured; it's left untouched when `enqueue_sentiment`
  reports one's already running; a `'skipped'` headline resets too when the key is configured;
  neither `'error'` nor `'skipped'` resets when the key is *not* configured, even though a fresh
  job is starting.

## What actually happened

Built as planned, plus one confirmed-during-planning refinement: the reset is gated on
`settings.openai_api_key` being currently truthy, not on status value alone — `error` and `skipped`
both reset when configured, neither resets when not (see spec 0005's amended Goals/Success-criteria
bullets and learning record 0018 for the reasoning that led there).

`docs/specs/0005-headline-sentiment-analysis.md` amended in place (one Goals bullet extended, one new
Success-criteria bullet) — no new spec, no new ADR.

Tests: `test_jobs.py` gained one test (`enqueue_sentiment` returns a truthy `Job` when nothing's
running); `test_search_endpoint.py`'s `_FakeArqRedis` gained a `sentiment_already_running` flag and
four new tests (`error` resets when a fresh job starts and the key is configured; left untouched when
one's already running; `skipped` resets too when configured; neither resets when the key isn't). 91/91
backend tests (5 new), zero regressions. No frontend change needed, as anticipated — `hasPendingSentiment`
already treats `NULL` as pending.

Live-verified against the real running stack (rebuilt `api`/`worker`): inserted a synthetic `error`
headline for `AAPL`, called `/api/search` while a large real sentiment job for that ticker was still
running — correctly left untouched (ADR 0015 join, `enqueue_sentiment` returned `None`). Waited for that
job to finish, called `/api/search` again: the synthetic headline reset to `NULL` in both the response
and Postgres immediately, page-level `sentiment` read `processing` (not `error`) in that same response,
and a real OpenAI call resolved it to `ok`/score 20/gloss "concerning" moments later. Synthetic row
removed after verification.
