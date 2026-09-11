# Lesson 10 plan — testing the search feature

Scope: `NOTES.md`'s lesson 10, per ADR 0005 (targeted tests, not full coverage, not zero). Tests real code that
now exists: `providers.py`'s four functions and `search.py`'s endpoint + `split_today_recent`. Explicitly not
in scope: retrofitting tests onto the plumbing-arc code (`health.py`, `worker.py`'s heartbeat, `main.py`'s mode
switch) — already verified thoroughly by hand across lessons 1–5, per ADR 0005's own boundary.

## What gets built

**1. New dev dependencies** (`backend/pyproject.toml`, a `[dependency-groups]` `dev` group, not the main
`dependencies` list — these never ship in the running containers): `pytest`, `pytest-asyncio`, `respx`.

**2. Test config**: `pyproject.toml`'s `[tool.pytest.ini_options]`, `asyncio_mode = "auto"` — lets test
functions just be `async def` without a `@pytest.mark.asyncio` decorator on every single one.

**3. A dedicated `ticker_test` database** — per ADR 0005, migrated by the *same* `dbmate` migration files as
dev, not a hand-maintained schema copy that could drift. A session-scoped `conftest.py` fixture:
- Runs `dbmate --url <ticker_test URL> up` once per test session (creates the DB if missing, applies every
  migration) — reusing the exact same migration history dev/lesson 6/7 already produced.
- A function-scoped fixture truncates `headlines` and `companies` before each test — simpler and more reliable
  with async SQLAlchemy than fighting nested-SAVEPOINT rollback patterns, at the (acceptable, at this scale)
  cost of tests not running inside a single rolled-back transaction each.
- A `test_session_factory` fixture: a real `async_sessionmaker` pointed at `ticker_test`, built the same way
  `db.py`'s does for dev — this is the direct payoff of `providers.py`/`search.py` taking `session_factory` as
  an injectable parameter: tests pass this in, zero production code changes needed to make it testable.

**4. Unit tests for `split_today_recent`** (`tests/test_search.py`) — no DB, no network, no mocking at all;
just construct `Headline` objects in memory (never persisted) and call the pure function directly:
- A headline at 11:30pm Eastern the same day as a fixed fake `now` → lands in `today`.
- A headline that's `published_at` just after Eastern midnight relative to `now` (a UTC timestamp that's still
  "yesterday" in Eastern, and one that's already "today" in Eastern) → the exact boundary spec 0001's own
  Success Criteria names, tested for real instead of asserted by inspection.
- A case spanning a DST transition (e.g. around Nov 1st, when Eastern shifts EST↔EDT) — confirms `ZoneInfo`
  handles the offset change automatically, not a hardcoded UTC-4/-5 assumption.
- Empty list, all-today, all-recent, and newest-first ordering preserved within each bucket.

**5. Provider tests with `respx`-mocked HTTP** (`tests/test_providers.py`) — using the *real* response shapes
already captured live in lessons 7/8 (Finnhub's actual fields, EDGAR's actual parallel-array shape), not
invented fixtures:
- **A regression test for the exact date-filter bug found in lesson 7**: mock an EDGAR submissions response
  with filings both inside and outside the 7-day window (and some non-allowlisted form types mixed in), assert
  only the correct ones survive. This is the one test in this whole lesson with a direct, named bug it exists
  to prevent from silently coming back.
- Finnhub field mapping: mock a `company-news` response, assert `outlet`/`summary`/`published_at` map exactly
  as lesson 7 verified live.
- Failure paths: mock a Finnhub 403 and an EDGAR 500, assert `ProviderFetchError` and that
  `fetch_and_persist_headlines`'s overall `status` correctly becomes `partial_failure`/`complete_failure`.
- Dedup: call `fetch_and_persist_headlines` twice against the test DB with the same mocked responses, assert
  the row count doesn't grow the second time — the same thing verified manually in lesson 7, now automated.
- The `category` `CHECK` constraint: attempt an invalid category directly against `ticker_test`, assert
  `IntegrityError`/`CheckViolationError` — lesson 6's manual check, automated.
- The `companies` no-garbage-row sequencing: (a) both providers mocked empty → assert no `companies` row;
  (b) only Finnhub mocked with real data, EDGAR lookup mocked to find no CIK match → assert a `companies` row
  with `cik`/`company_name` null.

**6. An integration test for `/api/search`** (`tests/test_search_endpoint.py`), using `httpx`'s
`ASGITransport` against the real FastAPI app — no running server needed:
- `app.dependency_overrides[get_session_factory]` → the test session factory.
- `app.dependency_overrides[get_arq_redis]` → a fake object (`unittest.mock.AsyncMock`) standing in for the
  real ARQ pool, so this test never touches real Redis or triggers a real job — it's testing the endpoint's own
  logic (the two-step design, the response shape), not lesson 7's job again.
- Pre-seed `ticker_test` with known `Headline` rows, call `/api/search`, assert the JSON response's `today`/
  `recent` split and `status` are correct.
- Job-timeout path: make the mocked job's `.result()` raise `asyncio.TimeoutError`, assert `complete_failure`
  plus the pre-seeded data still comes back — the same worker-down behavior verified manually in lesson 9,
  now automated and repeatable without needing to actually stop a container.

## Verification

The lesson's own point, per `NOTES.md`: prove these tests are meaningful, not just green by accident.

1. Run the full suite once — everything passes against the real, already-correct code.
2. **Deliberately reintroduce the lesson 7 date-filter bug** (comment out the cutoff check in
   `fetch_edgar_filings`) — confirm the regression test in step 5 actually fails. Revert, confirm it passes
   again.
3. Do the same for one other test (e.g., temporarily break `split_today_recent`'s Eastern-time conversion) —
   confirm that test alone fails while the rest of the suite stays green, proving tests are actually isolated
   and specific, not all failing together from an unrelated break.

## Open items

**Resolved**: `ticker_test` persists between runs, truncated per-test — small dataset, no reason to pay
drop/recreate cost every session.

- No frontend test tooling decision here — still deferred to the React lessons (11–13), per ADR 0005.
