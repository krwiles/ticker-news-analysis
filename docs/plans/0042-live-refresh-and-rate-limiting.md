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

(Filled in after building.)
