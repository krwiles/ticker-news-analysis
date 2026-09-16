# Lesson 19 plan — the actual grouping logic

Scope per `NOTES.md`: combines lessons 16–18 inside the existing `fetch_and_persist_headlines` job --
oldest-to-newest processing of only new headlines, threshold search against Milvus, `story_id` assignment.
Biggest lesson in Arc 4, same weight lesson 7 carried in arc 2. No dedicated pytest suite in this lesson,
per lesson 7's own precedent — verified live against the real running stack; lesson 20 adds dedicated
mocked tests.

## Architectural approach

Two independently-gated paths inside a new `_assign_stories()`, called from `fetch_and_persist_headlines` only
for headlines this exact run inserted for the first time (see "New-vs-known detection" below):

- **Filings**: always their own Story of one (`CONTEXT.md`'s Story entry) — pure Postgres, no embedding spent,
  unconditional.
- **News**: batch-embedded in one request (lesson 18), then matched sequentially, oldest-published-first,
  against `story_primaries` (ADR 0011) — a match above `story_similarity_threshold` (0.75, empirically tuned,
  see ADR 0011) joins the existing Story; no match founds a new one and writes its vector to Milvus,
  permanently. Sequential, not parallel, because headline *N*'s candidate Stories include ones headline
  *N-1* in the same loop just created.

**News-matching gracefully no-ops (leaves `story_id` null) when `OPENAI_API_KEY` isn't configured** — same
graceful-degradation instinct as a down worker still showing existing data, and specifically what keeps this
project's test suite hermetic without needing lesson 20's mocking built early: filings still group correctly,
headlines still get fetched/deduped/persisted correctly, they're just left ungrouped until grouping
infrastructure is actually available.

**New-vs-known detection**: `INSERT ... ON CONFLICT DO UPDATE ... RETURNING (xmax = 0) AS was_inserted` on the
existing upsert statement — verified live against a real Postgres session (not assumed from memory) that this
correctly distinguishes a genuine insert from an ON CONFLICT update, in the same round trip, no separate
pre-query needed.

**`run_in_executor`**, closed for real this lesson: every blocking `pymilvus` call (collection creation,
search, insert) goes through one `_run_milvus()` helper wrapping `loop.run_in_executor`. The Milvus client
itself was also made lazy (connects on first real use, not at import time) — `MilvusClient.__init__` opens a
real connection, unlike `create_async_engine`'s genuinely lazy pool, and `providers.py` now imports it
unconditionally, which broke host-run tests (the `milvus` hostname only resolves inside the docker network)
until this was fixed.

## Files and components changed

- `backend/src/ticker_backend/milvus_client.py` — `get_milvus_client()` (lazy singleton, was eager),
  `ensure_story_primaries_collection()`, `STORY_PRIMARIES_COLLECTION`/`EMBEDDING_DIMENSIONS` constants.
- `backend/src/ticker_backend/providers.py` — `EASTERN` constant, `_run_milvus`, `_milvus_ticker_day_filter`,
  `_match_or_create_story`, `_assign_stories`, and the upsert loop's `RETURNING`-based new-headline detection,
  all wired into `fetch_and_persist_headlines`.
- `backend/src/ticker_backend/config.py` — `story_similarity_threshold: float = 0.75`.
- `docs/adr/0011-milvus-story-collection-design.md` — new.

**Untouched**: `models.py` (`Story`/`Headline.story_id` already existed, lesson 17), `search.py`, all frontend
code, `backend/tests/test_providers.py` (per the no-dedicated-tests scope above).

## Database / data model changes

None in Postgres schema — `story_id` stays nullable (tightening it to `NOT NULL` would need every insert path
to always set it; the graceful-degradation design above means that's not true when `OPENAI_API_KEY` is unset,
so this migration deliberately isn't part of this lesson). A new Milvus collection, `story_primaries`, gets
created on first use (see ADR 0011 for the full schema/metric/threshold design).

## API / interface changes

None — `/api/search`'s response shape is unchanged (lesson 21).

## Backend / frontend changes

Backend only, as listed above.

## Existing tests / new tests required

23/23 existing tests still pass, unchanged — verified after every fix in this lesson, not just once at the
end. No new tests added, per scope (lesson 20's job). The graceful-degradation design (news-matching skips
when `OPENAI_API_KEY` is unset) is specifically what kept the existing suite green without needing Milvus/
OpenAI mocking built early: `settings.openai_api_key` is empty in every local/CI test run already (no `.env`
picked up from `backend/`'s cwd, no secret configured in CI), so grouping's news path never actually runs
during `pytest` today.

## Risks and assumptions — confirmed or resolved during this lesson

- The ADR 0009/spec 0002 primary-permanence question from planning: **resolved, not just accepted** — see
  ADR 0011's "primary is two concepts" section, worked through in full there.
- `run_in_executor`: closed.
- The similarity threshold: empirically measured, not guessed — see ADR 0011.
- New-vs-known detection: decided (`RETURNING xmax = 0`), verified live against real Postgres before trusting
  it.
- **A new risk found live, not anticipated in planning**: wiring grouping directly into
  `fetch_and_persist_headlines` meant every existing test that persists a real "news" headline would try to
  call OpenAI/Milvus for real. Closed by the `openai_api_key`-gated graceful-degradation design above — this
  wasn't in the original plan, it was a genuine regression caught by actually running the suite, not predicted
  in advance.
- **A second new risk found live**: `MilvusClient`'s eager connection at import time broke host-run tests the
  moment `providers.py` started importing `milvus_client.py` unconditionally. Closed by making the client lazy.

## Incremental steps (as executed)

1. Verified the `xmax = 0` new-row-detection trick against a real Postgres session before trusting it.
2. Built `milvus_client.py`'s `ensure_story_primaries_collection()` (schema, cosine `AUTOINDEX`).
3. Built the matching/assignment logic in `providers.py`, wired into `fetch_and_persist_headlines`.
4. Ran the existing suite — found and fixed two regressions (real OpenAI/Milvus calls in existing tests;
   eager Milvus connection breaking test collection) before they'd have shipped silently broken.
5. Empirically tuned the similarity threshold against six real headline pairs (see ADR 0011's table).
6. Live-verified against the real running stack — found and fixed two real bugs (unflushed inserts invisible
   to the next search; wrong primary-key field name assumed from a generic doc example) via a deterministic
   controlled test before broader verification, then confirmed a naive `flush()`-per-insert fix was itself too
   slow at real scale (249 new headlines, MSFT) and replaced it with `consistency_level="Strong"` — cut a
   20s+ timeout down to 3.86s for the same real data.
7. Full containerized sanity check: real `/api/search?ticker=MSFT` end to end, 3.57s, 188/188 new news
   headlines correctly assigned a `story_id`, zero worker errors.
