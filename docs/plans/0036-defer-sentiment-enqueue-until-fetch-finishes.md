# Plan 0036 — defer sentiment-enqueue until the fetch job actually finishes

Not a lesson, no spec/ADR — extends ADR 0015's single-flight signal and ADR 0012/0014's status
semantics, doesn't add new architecture. Confirmed in lesson 34's grilling round.

## The bug, confirmed and worse than suspected

`search()` calls `enqueue_sentiment` unconditionally, right after its own `await job.result(timeout=
...)` — whether that succeeded, failed, or timed out. On a timeout, the *real* fetch job (including
grouping) is often still running in the background. Reproduced live (lesson 34, `JOB_TIMEOUT_SECONDS=
1`, fresh ticker `PLTR`): `sentiment:PLTR` started 2 full seconds before `fetch_headlines:PLTR`
finished. Every headline got sentiment-scored with `story_id = NULL`, and since an `ok` headline is
never re-scored, **every one of PLTR's ~85 Stories ended up with `sentiment_score_count = 0`,
permanently** — a complete loss for the ticker, not a partial undercount.

## The fix

Sentiment starts only once a ticker's fetch job (fetch + grouping, the same job) has genuinely
finished — triggered from that job's own completion, not from the HTTP request that started or
joined it. `search()` can return long before the job it's waiting on actually finishes (that's the
whole point of its timeout); it structurally cannot know when a background-run job completes.

- **`worker.py`'s `fetch_headlines_job`** — the ARQ wrapper that already runs inside the same
  process as the fetch, after `fetch_and_persist_headlines` (which includes grouping) returns —
  calls a new `enqueue_sentiment_after_fetch(ctx["redis"], ticker)` right after. `fetch_and_persist_
  headlines` itself stays framework-agnostic (no ARQ dependency added), per its own docstring.
- **New `jobs.py`: `enqueue_sentiment_after_fetch`** — wraps `enqueue_sentiment` plus plan 0032's
  reset-stale-status logic (`_reset_stale_sentiment_status`, relocated here from `search.py`), and
  swallows its own exceptions (logged, not raised) so a hiccup here can never turn an otherwise-
  successful fetch job's reported result into a failure.
- **`search.py`** loses its direct `enqueue_sentiment` call, the reset logic, and the now-unused
  `update` import — it only enqueues-or-joins the fetch and reads current Postgres state. Simpler,
  not just fixed: the endpoint no longer needs to know anything about sentiment's own lifecycle.

**Side effect, not incidental**: plan 0032's reset also inherits the fix. It used to be able to fire
in `search()` before grouping finished (in the timeout case) — cosmetically harmless on its own, but
now it's structurally guaranteed to fire only after grouping, every time.

**Accepted edge case** (confirmed with the user): ADR 0015's 5-second fetch-result cooldown means a
Refresh that joins a just-finished fetch won't independently trigger its own sentiment attempt —
only the *original* run's completion does. In practice this is a no-op difference: a sentiment job
for that ticker is almost always still running from the original request (60-100+s per lesson
30/31), so today's "extra" call would itself already return `None` from single-flight.

## Test migration (not new work invented, existing coverage relocated)

- `test_search_endpoint.py`: plan 0032's four reset tests move to `test_jobs.py`, now targeting
  `enqueue_sentiment_after_fetch` directly instead of the `/api/search` endpoint.
  `test_search_enqueues_sentiment_job_fire_and_forget` rewritten — `/api/search` now only enqueues
  `fetch_headlines_job`; sentiment enqueue is `worker.py`'s responsibility, covered below.
- `test_jobs.py`: the four relocated reset tests, plus one new one — a failure inside
  `enqueue_sentiment_after_fetch` (e.g. the reset raising) is logged and swallowed, never raised.
- New `test_worker.py`: `fetch_headlines_job` calls `enqueue_sentiment_after_fetch` with `ctx["redis"]`
  and the ticker, after awaiting `fetch_and_persist_headlines` — worker.py's thin wrappers have had
  no dedicated tests until now.

## Verification

1. Backend test suite green.
2. Live re-run of lesson 34's exact reproduction (`JOB_TIMEOUT_SECONDS=1`, fresh ticker), confirming
   `sentiment_job` no longer starts before `fetch_headlines_job` finishes, and the ticker's Story
   aggregates come out correct this time.

## What actually happened

Built as planned. `jobs.py` gained `_reset_stale_sentiment_status` (relocated from `search.py`
unchanged) and the new `enqueue_sentiment_after_fetch`; `worker.py`'s `fetch_headlines_job` calls it
after `fetch_and_persist_headlines` returns; `search.py` lost the direct `enqueue_sentiment` call,
the reset logic, and the now-unused `update` import. 94/94 backend tests (5 relocated + rewritten
in `test_jobs.py`, 1 new in a new `test_worker.py`, one endpoint test rewritten to reflect `/api/
search` only enqueuing the fetch job), zero regressions.

**Live re-verification (lesson 34's exact repro, `JOB_TIMEOUT_SECONDS=1`, ticker `PLTR`) confirmed
the fix**: `sentiment:PLTR` now starts strictly after `fetch_headlines:PLTR` finishes (previously 2s
before). Every headline scored `ok` with `story_id IS NULL`: **zero**, down from every one of ~85
Stories being permanently zeroed. Multi-member Stories' aggregates now match their real members
exactly (e.g. scores `{22,32,32,28}` → average `28.5`, verified against `(22+32+32+28)/4`).

**A real test-environment mistake found and fixed along the way, not a bug in the fix**: the first
re-verification attempt failed with a `headlines_story_id_fkey` violation — grouping matched a new
headline against a Milvus `story_primaries` vector left over from lesson 34's own earlier PLTR test,
whose corresponding Postgres `Story` row had already been deleted during that test's cleanup.
Postgres and Milvus were cleaned up separately back then; deleting from one without the other left
them out of sync. Fixed by also deleting the leftover Milvus vectors
(`client.delete(collection_name="story_primaries", filter='ticker == "PLTR"')`) before retrying.
Not itself a product bug — a reminder that this project's own dual-store design needs both sides
kept in sync during manual cleanup, same as a future automated backfill/deletion feature would.

**A second real, unrelated finding, deliberately out of scope**: 12 of 114 Stories still showed a
zero aggregate after the fix — traced to a pre-existing boundary mismatch, not the race this plan
targets. Finnhub's fetch range (`from`/`to`) is day-granularity, so a headline published early on
the oldest included day can still get fetched and grouped, while `RECENT_HEADLINES_WINDOW`'s cutoff
is an exact timestamp (`now - 7 days`) that excludes it from `_fetch_pending_headlines`'s "still
needs sentiment" query. Confirmed unrelated to this fix: zero headlines anywhere had
`sentiment_status = 'ok'` with `story_id IS NULL` (the actual invariant this plan restores). Noted
in `NOTES.md` as its own idea, not chased here.

Test/synthetic PLTR data (Postgres and Milvus both) removed after verification.
