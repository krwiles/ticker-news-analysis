# Lesson 20 plan — backend tests for grouping

Scope per `NOTES.md`: mocking OpenAI and Milvus at their boundaries, same `respx`-style discipline as
`test_providers.py`. Mirrors lesson 10's shape. Two decisions made during planning, both recorded in
ADR 0012 before any test code was written: the Milvus client becomes an injectable parameter (built and
live-verified first, in isolation, before anything else here), and grouping failures now degrade gracefully
and are surfaced through a new `grouping` field on `/api/search`'s response, not just logged.

## Architectural approach

**Step 0, done first and separately**: `_match_or_create_story`, `_assign_stories`, `ensure_story_primaries_collection`,
and (found needed only once test-writing began) `fetch_and_persist_headlines` itself all gained an optional
`milvus=None` parameter, mirroring `session_factory`'s existing shape exactly. Re-verified against the full
existing suite and all three of lesson 19's own live-verification scripts (the deterministic 4-scenario test,
the 20-iteration late-match test, and the 250-headline MSFT scale test) before any lesson 20 code was written,
confirming byte-for-byte identical behavior.

**Step 1**: implement ADR 0012's failure-signaling decision. `_assign_stories` now returns `"ok"` / `"skipped"`
/ `"error"` instead of nothing. Filings commit in their own transaction, independent of news-matching, so a
later Milvus/OpenAI failure never undoes already-successful filing work. News-matching wraps the whole
setup-embed-match-commit sequence in one `try/except (ProviderFetchError, MilvusException)` — on failure,
nothing from that attempt commits (the session simply never reaches `commit()`), and `"error"` is returned.
`fetch_and_persist_headlines` propagates this into its result dict as `grouping`; `search.py` propagates it
into `/api/search`'s JSON response, defaulting to `"unknown"` specifically when the job itself never returned
(distinct from the three real "it ran" outcomes).

**Step 2**: `_FakeMilvusClient` — a hand-rolled in-memory fake (`tests/test_grouping.py`), not a dumb stub:
real cosine-similarity `search()`, an `insert()` that appends, `has_collection()` hardcoded `True` (schema/index
creation is Milvus's own concern, not what's under test). Its result shape (`story_id`/`distance`/`entity`)
matches real Milvus exactly — confirmed live in lesson 19 — which makes every successful-match test in this
suite also a live regression test for the "id" vs "story_id" key-naming bug found there.

## Files and components changed

- `backend/src/ticker_backend/providers.py` — `milvus` parameter added to four functions; `_assign_stories`
  restructured (filings in their own committed transaction, news-matching wrapped in try/except, returns a
  status string); `fetch_and_persist_headlines`'s result dict gains `grouping`.
- `backend/src/ticker_backend/milvus_client.py` — `ensure_story_primaries_collection(client=None)`.
- `backend/src/ticker_backend/search.py` — `/api/search` response gains `grouping`, defaulting to `"unknown"`
  on a job timeout/failure.
- `backend/tests/test_grouping.py` — new, 10 tests.
- `backend/tests/test_search_endpoint.py` — existing fake job-result fixtures updated to include `grouping`
  (a real regression these tests caught immediately: `KeyError: 'grouping'`, fixed by updating the fixtures to
  match the new real contract, not by loosening `search.py`'s own strict `result["grouping"]` read).
- `docs/adr/0012-*.md`, `docs/adr/0007-*.md` — written during planning, before any code.

## Database / data model changes

None.

## API / interface changes

`/api/search`'s JSON response gains one field, `grouping`, additive and backward-compatible. Lesson 21's own
planned reshaping must preserve it (already flagged in `NOTES.md`'s lesson 21 sketch).

## Backend / frontend changes

Backend only. `grouping` is available in the API response now; displaying it is lesson 22's job, per the
existing arc sequencing — not addressed here.

## Existing tests / new tests required

**Existing**: all 23 pre-lesson-20 tests still pass. Two needed real fixing, not just re-running: the two
`test_search_endpoint.py` job-result fixtures lacked the new `grouping` key, which `search.py` now reads
strictly — confirmed the exact `KeyError: 'grouping'` failure before fixing it, per this project's usual
"prove the regression, then fix it" discipline.

**New** (`test_grouping.py`, 10 tests): matching (same-event grouping, genuinely-different separation),
ticker-scoping, day-scoping, filing isolation, the late-match regression (per `NOTES.md`'s explicit note,
honestly scoped to what a fake can and can't prove — see the module's own docstring), permanence (proven at
the `fetch_and_persist_headlines` level, asserting OpenAI's mocked endpoint is called exactly once across two
runs, not just that the outcome looks the same), and the three `grouping` states (`"skipped"`, and `"error"`
for both an OpenAI failure and a Milvus failure, each verified live against the real stack first before being
committed as a mocked test).

**Verification, per lesson 10's own precedent**: deliberately commented out the threshold comparison
(`if False and hits and ...`) and reran — exactly the two match-dependent tests failed
(`test_matching_groups_same_event_different_wording`, `test_late_match_finds_story_many_iterations_later`),
every non-matching test stayed green. Reverted; full suite (33/33) confirmed clean again.

## Risks and assumptions — resolved during this lesson, not left open

- The OpenAI-down-mid-run inconsistency flagged during planning: resolved (ADR 0012), and live-verified against
  a real 401 from OpenAI before being turned into a mocked test — the real failure was caught, logged, returned
  `"error"`, and the headline still persisted, exactly as designed.
- The fake's honest limitation (can't regression-test real Milvus consistency behavior) is stated once in the
  test file's own module docstring, not re-litigated per test.
- A late gap found only once test-writing began, not anticipated in the original plan: `fetch_and_persist_headlines`
  itself needed the same `milvus` parameter `_assign_stories` already had, or the permanence test (which calls
  the real orchestrator, not `_assign_stories` directly) had no way to avoid a real Milvus connection attempt.
  Added, consistent with the same `session_factory` precedent already used everywhere else.

## Incremental steps (as executed)

1. Refactored the Milvus client to be injectable (isolated first step, per your instruction) — re-verified
   against the full test suite and all three of lesson 19's live-verification scripts.
2. Implemented ADR 0012's failure-signaling decision in `providers.py` and `search.py`.
3. Live-verified all three `grouping` outcomes (`"ok"`, `"skipped"`, `"error"` against a real 401) directly
   against the running stack before writing any mocked test for them.
4. Fixed the real regression in `test_search_endpoint.py`'s fixtures (confirmed the failure first).
5. Built `_FakeMilvusClient` and the 10 tests in `test_grouping.py` — found and fixed two real bugs in the
   tests themselves along the way (filler vectors too similar to each other in the late-match test, mirroring
   the exact mistake made in lesson 19's own throwaway script; `fetch_and_persist_headlines` missing the
   `milvus` injection point the permanence test needed).
6. Deliberately broke the threshold check, confirmed exactly the right tests failed, reverted.
7. Full containerized sanity check: real `/api/search?ticker=AAPL`, `grouping: "ok"` in the real response, zero
   worker errors.
