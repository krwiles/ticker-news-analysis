# Live-refreshing ticker search results, with a shared Finnhub rate limit

Implements `docs/specs/0007-live-refresh.md`, technical design in `docs/adr/0018-live-refresh-and-rate-limiting.md`.
Both finalized via grilling. No new entity, no schema migration — this is behavior on top of existing endpoints
and the existing fetch job.

## What changes

| File | Change |
| --- | --- |
| `backend/src/ticker_backend/rate_limit.py` (new) | Shared Finnhub-call counter (fixed 60s window) and a per-ticker cooldown check; one function deciding "defer, and by how many seconds" or "run now." |
| `backend/src/ticker_backend/jobs.py` | New background-trigger enqueue path (checks `rate_limit.py`, passes `_defer_by` when over budget) — separate from `enqueue_or_join_fetch`, which stays untouched and always-immediate. |
| `backend/src/ticker_backend/providers.py` | Increments the shared Finnhub counter around the real HTTP call. |
| `backend/src/ticker_backend/search.py` | `/api/search`: checks `await job.status()` before awaiting `.result()`, skips the await on `deferred`. `/api/search/status`: fires the new background-trigger check as a side effect (not awaited by the response); docstring updated — it's no longer purely enqueue-free. |
| `frontend/src/pages/SearchPage.tsx` | Removes the "Refresh" button and `handleRefresh`; broadens the existing sentiment-poll effect to run whenever results exist (not only while sentiment is pending); adds Page Visibility handling (pause when hidden, immediate check on refocus) and a `lastRefreshAt`-driven "last refresh Ns ago" display. |

## Order of work (TDD at each seam)

1. `rate_limit.py` — tests first: counter increments and caps at 60 per window; a fresh window resets it; per-ticker cooldown blocks a second check within its TTL; the decision function returns the right `(defer, seconds)` in each case.
2. `jobs.py`'s new background-trigger function — tests first: enqueues immediately when under budget; enqueues with `_defer_by` when over budget or on cooldown; uses the same deterministic job ID either way, so a concurrent call still joins rather than double-enqueuing (ADR 0015).
3. `providers.py` — test that a real Finnhub call increments the shared counter (respx-mocked HTTP call, real test Redis for the counter).
4. `search.py`:
   - `/api/search` — test that joining a `deferred` job skips the await and returns current Postgres state immediately, with the existing `providers_status={}`/`grouping_status="unknown"` fallback shape, not a `complete_failure`.
   - `/api/search/status` — test that it still returns its existing read-only shape unchanged, and that calling it triggers the new background-check path as an unawaited side effect (verified via a fake/spy, not by slowing the response down).
5. Frontend — tests first:
   - The Refresh button and its handler are gone.
   - The poll effect runs whenever `results` exist, not only while `hasPendingSentiment`.
   - `document.visibilityState`/`visibilitychange` pauses polling when hidden and triggers one immediate check on becoming visible.
   - `lastRefreshAt` resets on every successful poll (including the initial load) and the displayed "last refresh Ns ago" counts up from it once a second; a failed poll leaves both the displayed results and the counter's basis unchanged.

## Tests

- `test_rate_limit.py` (new): window cap behavior, window reset, per-ticker cooldown, the combined decision function.
- `test_jobs.py`: new tests for the background-trigger enqueue path alongside the existing `enqueue_or_join_fetch`/`enqueue_sentiment` tests.
- `test_providers.py`: Finnhub call increments the counter.
- `test_search_endpoint.py`: `/api/search` on a deferred job; `/api/search/status` triggers the background check.
- Frontend `SearchPage.test.tsx`: button removal, broadened polling, visibility pause/resume, the refresh counter's reset-on-success/hold-on-failure behavior.
- Deliberate-break checks on: the rate-limit decision function, the `job.status()` branch in `/api/search`, and the frontend visibility-pause logic — this project's usual discipline (a test that can't fail for the right reason proves nothing, per lesson 39's own finding during the secrets-management work).

## Verification

1. Full backend and frontend suites green.
2. Live, against the real stack: temporarily lower the rate-limit cap in a local run, confirm a fetch actually defers (visible in worker logs / Redis) and later runs on its own rather than being dropped.
3. While the budget is deliberately exhausted, confirm a real `/api/search` call for an existing ticker still returns instantly with current data (no hang, no misleading `complete_failure`).
4. In a real browser: confirm the Refresh button is gone, the "last refresh Ns ago" counter ticks up and resets on each successful background check, backgrounding the tab stops it, and refocusing triggers an immediate check.
5. Update `/api/search/status`'s docstring per ADR 0018's own "Consequences" note before calling this done.

## What actually happened during execution

Built as scoped, with two deviations found only by testing/verifying for real, not by re-reading the design:

- **A real bug, caught only by live verification: `redis.get()` returns `bytes`, not `str`.** Every fake
  Redis in this codebase's own tests (including the new ones written for this plan) stored and returned
  plain Python strings, so `rate_limit.py`'s `datetime.fromisoformat(last_fetch_raw)` passed every unit test
  cleanly -- then threw `TypeError: fromisoformat: argument must be str` on the very first real request in
  the browser, a 503 every time. This is the exact "redis-py hands back bytes unless decode_responses is set"
  fact `auth.py`'s `_resolve_session` already had to account for (ADR 0016) -- missed here because nothing in
  the design or the ADR's own grilling surfaced it, and no fake modeled it. Fixed by decoding bytes the same
  way `auth.py` does, then updated *every* fake Redis across `test_rate_limit.py`, `test_jobs.py`,
  `test_search_endpoint.py`, and `test_providers.py` to return `bytes` from `get()`, so this exact class of
  bug is caught by the unit suite from now on, not just by re-discovering it live each time.
- **`test_search_status_endpoint_never_touches_arq`'s own premise became false and had to be replaced, not
  patched.** That test existed specifically to prove `/api/search/status` was structurally incapable of
  enqueueing a job (ADR 0014) -- exactly the invariant ADR 0018 deliberately breaks. Rewrote it as
  `test_search_status_triggers_a_background_check_but_never_awaits_its_result`, proving the *new* invariant
  (a background check does fire, but its result is never awaited) with the same rigor the old one had for the
  opposite claim.
- The frontend's old "only poll while sentiment is pending" gate (`hasPendingSentiment`) became entirely
  unused once live-refresh polls unconditionally whenever results exist -- deleted rather than left as dead
  code, along with the four `sentiment polling` tests whose premise (starts/stops based on pending sentiment)
  no longer holds; replaced with a `live refresh` describe block covering the new unconditional/pause/resume/
  counter behavior.

Live-verified against the real running stack, including the deferred-job path specifically, not just success
cases: forced the shared Finnhub window to look fully exhausted via a real Redis connection inside the worker
container, confirmed `enqueue_background_fetch` returned a job in `JobStatus.deferred`, confirmed a real
`/api/search` call for that ticker returned in 56ms with existing data (`complete_failure`/empty providers,
never a hang), and then polled the same job's status for real until it actually transitioned to
`in_progress` → `complete` roughly a minute later with a genuine successful fetch -- proving the "guaranteed to
actually run later" claim in ADR 0018, not just asserting it. Confirmed live in a real browser (after finding
and fixing the bytes bug): the manual Refresh button is gone, "last refresh Ns ago" ticks up and resets to 0 on
each real successful poll, and pausing while the tab is genuinely backgrounded (confirmed via
`document.visibilityState`/`hasFocus()`, not assumed) stops polling until it's brought back into focus.

136/136 backend tests (13 new: 6 rate_limit, 3 jobs, 2 providers, 1 replaced + 1 net-new in search_endpoint),
102/102 frontend tests, zero regressions. Deliberate-break checks passed on: both `should_defer_fetch` gates,
`enqueue_background_fetch`'s `_defer_by` wiring, the Finnhub-call recording, the `job.status()` branch in
`/api/search`, `/api/search/status`'s background trigger, the frontend visibility-pause logic, and the
refresh-counter reset logic.

### Code review fixes

A background review of the diff found five real issues, all fixed, TDD'd, and deliberate-break checked where
correctness was at stake:

- **`search_status()`'s background trigger had no exception handling.** A Redis blip during the rate-limit
  check would have turned a healthy poll into a 500 -- exactly the "never causes visible errors" promise spec
  0007 makes. Wrapped in the same swallow-and-log pattern `jobs.py`'s own `enqueue_sentiment_after_fetch`
  already established, with a new regression test (`test_search_status_survives_a_background_check_that_blows_up`).
- **A real frontend race: an overlapping refocus check could apply a stale response.** `stopPolling()` only
  clears the timer, never an already-in-flight fetch, so backgrounding then quickly refocusing could let an
  older poll's response resolve *after* a newer one and silently overwrite it. Fixed with a `latestRequestId`
  guard (discard any response that isn't from the most recently started call), proven with a new test that
  resolves two controlled promises out of order.
- **`enqueue_background_fetch` had no inline step comments**, unlike its near-identical sibling
  `enqueue_or_join_fetch` two lines above it. Added, matching the existing convention.
- **The "last refresh" ticker re-rendered the whole results tree every second** for a one-line string. Extracted
  into its own `RefreshIndicator` component (with its own small test file) so only that line re-renders.
- **Four test files each reimplemented the same fake-Redis bytes-encoding logic.** Extracted into a shared
  `tests/fakes.py::FakeRedisKV`, with the ARQ-flavored fakes in `test_jobs.py`/`test_search_endpoint.py`
  inheriting from it instead of duplicating it.

137/137 backend tests, 106/106 frontend tests after these fixes.
