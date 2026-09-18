# Lesson 26 plan — the actual sentiment job

Scope per `NOTES.md`: wires lessons 23-25 together inside a new background job, separate from
`fetch_and_persist_headlines`, plus the score-to-enum threshold tuning deferred here from lesson 24.

## Two real architectural gaps found during planning, resolved before any code

1. **Naive polling would re-trigger the full fetch job.** ADR 0014's original "poll the existing
   `/api/search`-shaped response" glossed over the fact that `/api/search` unconditionally enqueues *and
   awaits* `fetch_headlines_job` on every call. **Resolved**: a new, read-only `GET /api/search/status`
   endpoint, sharing the query/response logic with `/api/search` via an extracted helper, with no job
   enqueue at all.
2. **No clean source for the page-level sentiment status**, since the sentiment job is fire-and-forget.
   **Resolved**: a real fourth state, `processing`, derived fresh from already-queried headline rows on every
   request (`skipped` → `error` → `processing` → `ok`, checked in that priority order). Both changes folded
   into spec 0005 and ADR 0014 before implementation started.

## What gets built

- **`config.py`**: `RECENT_HEADLINES_WINDOW = timedelta(days=7)`, a bare constant (not a Settings field — a
  fixed business rule, not env-configurable), replacing the same literal that was inline in `search.py` and
  newly needed by `providers.py` too. Deliberately placed in `config.py`, not `search.py` or `providers.py`
  directly — either direction of cross-import would pull a heavy, unrelated dependency chain (FastAPI, or
  `pymilvus`) into a container mode that doesn't otherwise need it, the same class of risk already fixed
  twice for the `pymilvus`/`dotenv` landmine.
- **`providers.py`**: `NEWS_CONTENT_CAP_CHARS`, `_derive_sentiment_enum` (score → enum, empirically tuned),
  `compute_and_persist_sentiment` (the real orchestration — query, concurrent fetch, sequential persist,
  Story aggregate update).
- **`worker.py`**: `sentiment_job`, registered alongside `fetch_headlines_job`.
- **`search.py`**: `_compute_sentiment_status`, `_load_search_results` (shared helper), the new
  `/api/search/status` route, and a fire-and-forget `sentiment_job` enqueue added to `/api/search`.

## Threshold tuning — the light pass, as agreed

15 real headlines (5 clearly positive, 5 clearly negative, 5 routine/neutral) scored via `get_sentiment`.
Real scores clustered cleanly: negative 15-34, neutral 50-68, positive 75-90 — genuine gaps at [34, 50] and
[68, 75]. Cutoffs: **≤40 negative, ≥70 positive, else neutral** — round numbers sitting inside both real
gaps with margin.

## Existing tests / new tests required

`test_providers.py`: `_derive_sentiment_enum` boundaries; `compute_and_persist_sentiment` persisting a real
score, updating a Story's aggregate (including the first-member case), skipping when unconfigured (no
respx mock registered — a real HTTP attempt would fail the test), writing `error` on failure, retrying a
previously-errored headline, and excluding an errored member from a Story's aggregate.

`test_search_endpoint.py`: `_compute_sentiment_status` across all four states and their priority order;
`/api/search` enqueues both jobs (`fetch_headlines_job`, then fire-and-forget `sentiment_job`); the new
status endpoint takes no `arq_redis` dependency at all (structurally cannot enqueue a job) and returns the
smaller `{"sentiment", "days"}` shape.

## What actually happened during execution

Everything above built and tested cleanly — 69/69 (13 new), zero regressions. Live verification against the
real stack is where the real finding showed up.

**A real, previously unverified failure mode: 239 real MSFT headlines, fired at once via unbounded
`asyncio.gather`, all timed out together.** ADR 0014's own concurrency research verified 20 concurrent calls
succeed cleanly (6.64s wall-clock) — but a real ticker's 7-day window turned out to hold 239 headlines, an
order of magnitude more. httpx's default client caps at 100 connections; with that much real simultaneous
load, OpenAI's own rate limiting plus the connection-pool bottleneck cascaded into every request — not just
the ones past connection #100 — backing up past the 10s per-request timeout together. The small-scale test
that validated the pattern was never actually the same shape as real production volume.

**Fixed with an `asyncio.Semaphore(20)`** bounding true concurrency to the exact figure already verified
safe, regardless of total batch size. Re-verified live against the same real 239-headline MSFT batch:
238/239 succeeded on the first pass, 1 genuine transient failure (a real, if isolated, error — not a
symptom of the concurrency fix itself). The page-level status correctly showed `error` for that one real
failure (masking nothing, by design), and a second `/api/search` call — the retry path, working exactly as
designed — resolved it: **239/239 headlines with real scores** on the next attempt.

Spot-verified the Story aggregate against real data, not just the mocked tests: one real 3-member MSFT
dividend Story showed `sentiment_average = 64`, `sentiment_score_count = 3`; its three members' actual
stored scores (82, 75, 35) average to exactly 64.0. The incremental formula holds against real,
independently-computed data, not just the synthetic fixtures.

ADR 0014 updated in place with the concurrency finding, same precedent as its other revisions this arc.
