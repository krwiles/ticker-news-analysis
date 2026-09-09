# A targeted test suite for this feature — not full coverage, not zero

No tests exist anywhere in the repo. The project's established habit has been manual/live verification against
the running stack (`curl`, direct Postgres queries, the multi-worker heartbeat experiment), which has worked
well pedagogically — but this feature introduces logic that habit can't reliably cover: the US-Eastern/DST
today-vs-recent boundary (can't practically wait for midnight to test it live), partial/complete provider
failure and the ARQ job-timeout case (can't reliably trigger a real provider outage on demand), and dedup/upsert
regressions (wouldn't surface until someone noticed duplicate rows by eye). Separately, the learner wants to
actually learn testing as a discipline — unlike ARQ, no testing framework was ever part of the original
insider stack list this project is learning, so this is a freestanding goal, not a stack-completion one.

Decision: introduce `pytest` + `pytest-asyncio`, `httpx`'s `ASGITransport` test client, `respx` for mocking the
EDGAR/Finnhub calls, and a dedicated `ticker_test` Postgres database (migrated by the same `dbmate` migrations
as dev) — scoped to this feature only. Covers: unit tests for the today/recent split against a fixed fake "now"
and the `category` CHECK/dedup-upsert behavior at the DB layer; an integration test for `/api/search` end to
end with mocked provider responses; failure-path tests for partial failure, complete failure, and the ARQ
job-timeout case. This also settles which HTTP client the project uses for external calls — `httpx`, partly
*because* it's what FastAPI's own test client is built on, so one library serves both jobs.

## Considered options

- **No tests, continue manual/live verification only**: keeps the project's established rhythm, but leaves
  time-dependent and failure-path logic — the parts most likely to silently regress — with no way to reliably
  re-check them on demand.
- **Full test suite, including retrofitting the existing plumbing-arc code** (`health.py`, `worker.py`'s
  heartbeat, `main.py`'s mode switch): rejected — that code has already been thoroughly verified by hand across
  lessons 1–5; retrofitting tests onto it is a separate undertaking unrelated to learning this feature, and
  would dilute focus from what's actually new.
- **Targeted backend tests for this feature, frontend testing tooling decision deferred** (chosen): gives real,
  properly-scoped practice with pytest/mocking/test-DB conventions without either under- or over-building for a
  personal project.

## Consequences

- A second Postgres database (`ticker_test`) needs to exist locally, migrated the same way as dev — a small
  new piece of setup, not just application code.
- Frontend testing tooling (Jest/Vitest, Testing Library) remains an open decision, to be made when the React
  lessons actually begin, not decided in the abstract now.
- The existing plumbing-arc code stays untested by deliberate choice, not oversight — its verification story is
  the manual/live checks already done in lessons 1–5, and that stands as sufficient.
