# Lesson 30 plan — sentiment retry, processing order, and incremental writes

Not a planned lesson — a live bug-fix session, triggered by three real user reports after using the
rebuilt Arc 5 UI: (1) Refresh didn't seem to redo a failed sentiment analysis, (2) the UI only ever seemed
to update once *everything* finished, never partially, and (3) sentiment analysis "fails quite often." All
three traced back to real, evidence-backed root causes in the live worker logs and the poll-effect's own
dependency logic — not new feature requests, three real bugs.

## Diagnosis, from the actual worker logs

Every sentiment failure in the last 6 hours (54/54) carried the exact same message:
`"OpenAI sentiment fetch failed: "` — an empty string, the fingerprint of a bare `httpx` timeout exception
(`str()` on a timeout with no args is empty; a real HTTP error response carries real text). Failures
clustered in tight ~200ms windows at the ~10s client-timeout mark, even at concurrency well under the
`Semaphore(20)` cap already fixed in lesson 26 — a different, still-unexplained-in-detail failure shape from
the 239-headline pool-exhaustion cascade that fix targeted. Most likely real OpenAI-side rate limiting or
load under this account's tier; the code itself gave no way to tell, since it logged `str(exc)` (empty) with
no exception type.

Two more bugs surfaced from reading `SearchPage`'s own poll effect and `providers.py`'s write pattern:

- `compute_and_persist_sentiment` gathered every concurrent OpenAI call via `asyncio.gather`, then wrote
  **all** results inside one session with a single `session.commit()` at the very end. Nothing was visible
  to a poll until the entire batch (60-100+ seconds for a real batch) finished.
- The frontend's poll guard only started polling when the coarse page-level `sentiment` field read
  `"processing"`. That field reads `"error"` the moment *any* headline in the batch has permanently failed
  — by design (lesson 26), so a real error is never masked by other headlines still pending. But combined
  with the poll guard, this meant: the instant one headline failed, polling for the *rest* of a still-in-
  flight batch silently stopped, even though real progress was still happening in the database.

## Decisions

1. **One automatic retry per headline, within the same job run.** Confirmed with the user: most failures
   are transient (timeout under load), so a lone failure isn't yet reason to give up. Separate from, and in
   addition to, spec 0005's existing "a later request can retry" behavior — this is a same-run retry.
2. **Newest-published headlines processed first.** A user checking sentiment cares most about the most
   recent news; resolving it first gets the most relevant information on screen soonest.
3. **`ok` stays untouchable.** Already true both in spec 0005 and in the existing query's WHERE clause
   (`sentiment_status IS NULL OR IN ('skipped','error')`) — reconfirmed as an explicit requirement to
   preserve through the rewrite below, not a new decision.
4. **Incremental commits, not one batch commit.** `asyncio.as_completed` (not `gather`) plus a
   `session.commit()` per headline, right after each one's own attempt resolves.
5. **The frontend polls off real per-headline pending state, not the coarse status field.** A new
   `hasPendingSentiment(days)` helper (search.ts) checks whether any Headline in the current data still has
   `sentiment_status === null` — this is what actually answers "is there more still coming," independent of
   whether the coarse status happens to read `"error"`.
6. **The poll effect depends on the whole `results` object, not narrowed fields.** This fixes a second,
   related bug for free: a manual Refresh that lands back on the same overall status (`"error"` both before
   and after) still produces a *new* `results` object each time, so the effect re-evaluates from scratch —
   no separate "search generation" counter needed.

## What got built

- **`providers.py`**: `compute_and_persist_sentiment`'s query gained `.order_by(Headline.published_at.desc())`.
  `_get_one` became `_fetch_with_retry` (one retry, delay outside the semaphore so a waiting retry doesn't
  hold a concurrency slot) wrapping a new `_fetch_one`. The write loop switched from `gather`-then-write to
  `asyncio.as_completed`, with `await session.commit()` inside the loop, once per headline. Failure logging
  gained `error_type=type(error.__cause__ or error).__name__` — `ProviderFetchError` wraps the real
  exception via `raise ... from exc`, so `__cause__` recovers it.
- **`search.ts`**: new `hasPendingSentiment(days: DayGroup[]): boolean`.
- **`SearchPage.tsx`**: poll guard now calls `hasPendingSentiment(results.days)`; effect dependency array is
  `[results]` (the whole object) instead of `[results?.ticker, results?.sentiment]`.
- **`docs/specs/0005-*.md`**: tightened the existing "catch-up is incremental" language to say so
  explicitly, and added the two genuinely new decisions (newest-first order, one same-run retry).

## Tests

- `test_providers.py`: new `no_retry_delay` autouse fixture (monkeypatches the retry delay to 0 for test
  speed); `_seed_headline_for_sentiment` extended with `title`/`published_at` params; three new tests
  (retry-recovers, retry-exhausted-after-one, newest-first-processing-order via request-body inspection);
  the existing mixed-outcome Story-aggregate test switched from a sequential `side_effect` list to a
  request-content-keyed callable, since two headlines racing concurrently (one now retried) no longer
  guarantees the old assumed call order.
- `SearchPage.test.tsx`: `vi.mock("../search", ...)` switched to `importOriginal` so the real
  `hasPendingSentiment` runs under test rather than being auto-mocked to `undefined`; existing poll tests
  updated to build real headline-level pending/resolved data instead of relying on the coarse `sentiment`
  field alone; two new tests for the actual bugs found — polling continues while the page reads `"error"`
  as long as another headline is still pending, and a manual Refresh restarts polling even when the overall
  status is identical before and after.

## What actually happened during execution

Built as planned. One test fix needed along the way: the existing
`test_compute_and_persist_sentiment_excludes_errored_member_from_story_aggregate` assumed a fixed
call-order `side_effect` list (`[success, failure]`); with the two headlines' calls now genuinely racing
concurrently (and the failing one retried, consuming a third response the old list didn't have), that
assumption broke. Fixed by giving the two headlines distinct titles and keying the mock response off
request content instead of call order — a test bug uncovered directly by the retry logic actually working
as intended, not a bug in the retry logic itself.

78/78 backend tests (3 new), 83/83 frontend tests (2 new), both suites clean. `tsc --noEmit` clean.

Live-verified against the real running stack, watching a real `SPCX` search with genuine prior failures:

- Polled `/api/search/status` repeatedly during a fresh run: the pending-headline count dropped
  13 → 12 → 8 → 4 → 0 across successive ticks — real incremental progress, not one final jump.
- The worker logs now show `error_type: "ReadTimeout"` on every failure — confirmed the actual mechanism,
  not a guess.
- Two fresh `/api/search` calls on a ticker with 3 lingering `error` headlines recovered 2 of them
  (298 → 300 `ok`); the `ok` count only ever grew across every refresh watched, never dropped or got
  re-attempted — confirming the "once ok, never touched again" invariant held under real concurrent retry
  activity, not just in the unit tests.

## Follow-up: the per-call timeout, bumped after a second real failure sample

A later real run (`AVGO`, 113 pending headlines) resolved 107/113 on the first pass plus retry — 6
permanent failures, every one of them `error_type: "ReadTimeout"` again, now scattered across ~9 seconds of
the batch rather than one simultaneous wave (confirming the semaphore fix still holds; this is a different,
smaller-scale symptom). Consistent, repeated evidence across two independent real batches that these are
genuine timeouts, not rejections — `httpx.AsyncClient(timeout=...)` doubled from 10s to 20s
(`SENTIMENT_HTTP_TIMEOUT_SECONDS`), giving a slow-but-otherwise-successful OpenAI response more room before
being cut off. Not yet re-measured against a fresh failure sample the same way the retry delay still isn't
— a reasonable next check once more real volume has gone through it.
