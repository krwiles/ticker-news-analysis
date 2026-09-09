# Live fetch on search, persisted into the schema a future scheduled worker will share

Status: **partially superseded by `0004-fetch-runs-as-an-arq-job.md`** — the decisions below (live fetch over
worker-pre-fetch-only, persisting into a schema the future watchlist feature will share) still stand as
written. What changed in 0004 is narrower: *how* `/search` invokes the fetch — an ARQ job it enqueues and
awaits, not a function it calls directly in-process, chosen for hands-on ARQ practice. Read this ADR for the
live-fetch/persistence decision, 0004 for the job-vs-direct-call mechanism.

News Search (`docs/specs/0001-first-feature.md`) needs live, up-to-date results the moment a user searches a
ticker, but a future feature will also want a background-polled watchlist keeping tickers fresh on a schedule.
Rather than choosing one now and reworking it later, both get built on the same foundation: a plain, reusable
fetch-and-normalize function (call providers, produce `Headline` rows, upsert by URL) that v1's `/search` and
Refresh call synchronously today, and that a future ARQ cron job (same mechanism as the worker's heartbeat) will
call on a schedule later — writing into the exact same Postgres table.

## Considered options

- **Live fetch only, no persistence**: simplest possible v1 — fetch, return, discard. Rejected because it
  leaves lessons 6–8 with no real Postgres table to teach against, and throws away work a future watchlist
  feature would need to redo from scratch.
- **Worker pre-fetch only** (search just queries whatever the worker last polled): keeps `/search` fast and
  simple, but means a searched ticker that isn't already being tracked returns nothing until an operator adds
  it to some tracked list — a worse experience for a tool meant for ad-hoc lookups of small-cap tickers a
  watchlist wouldn't already cover.
- **Live fetch + persistence, fetch logic shared with a future scheduled job** (chosen): search stays
  immediate and works for any ticker, not just tracked ones. Persisting as a side effect of every live fetch
  gives lesson 6 real data flowing through Postgres now, and means the future watchlist feature is additive —
  a new caller of the same fetch function — rather than a redesign of how fetching and storage work.

## Consequences

- `/search` and the future scheduled poll both depend on one shared fetch function; a bug or provider-shape
  change fixed in one place fixes both, but also means that function's interface needs to stay stable as both
  callers evolve.
- No caching/staleness-check logic exists in v1 — every search and every Refresh press does a full live fetch,
  accepted because rate limits aren't a real concern at personal-project scale (see spec 0001's Non-goals).
- Persisted `Headline` rows accumulate indefinitely with no pruning; acceptable now, a real constraint if this
  ever runs at higher volume or for longer than a personal project's timeframe.
