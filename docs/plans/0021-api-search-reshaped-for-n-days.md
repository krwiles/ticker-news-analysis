# Lesson 21 plan — `/api/search` reshaped for N days

Scope per `NOTES.md` and spec 0002: replace `today`/`recent` with `days`, one entry per calendar day holding
Stories. Two decisions made during planning, recorded in ADR 0013 before any code: the response shape is
replaced outright (not rolled out additively), and only Today is always emitted — earlier days appear only
when non-empty.

## Architectural approach

`/api/search` already fetches the full flat list of matching `Headline` rows from Postgres in one query; the
reshape happens entirely in Python, same pattern `split_today_recent` already used (a pure function, `now`
passed in explicitly, so DST/boundary behavior stays testable without waiting for real midnight).

1. **Group into Stories**: partition headlines by `story_id`. Within a group, sort by `published_at` ascending
   — the first is the primary (ADR 0009's derivation rule), the rest are `other_members`. A `story_id IS NULL`
   headline (grouping skipped or errored, ADR 0012) becomes its own singleton Story rather than merging with
   other null-story headlines or disappearing — the whole point of ADR 0012's graceful degradation.
2. **Bucket into days**: a Story's day is its primary's Eastern calendar date — safe, since matching is
   already day-scoped at write time (ADR 0006), so every member of a Story shares one Eastern day.
3. **Sort**: days newest-first (Today first); within a day, Stories newest-first by primary's `published_at`.

## Files and components changed

- `backend/src/ticker_backend/search.py` — `split_today_recent` replaced by the grouping/bucketing logic
  above; `/api/search`'s response gains `days`, loses `today`/`recent`.
- `backend/tests/test_search.py` — rewritten against the new pure function(s); all existing DST/Eastern-
  boundary cases ported, not dropped.
- `backend/tests/test_search_endpoint.py` — both existing integration tests' assertions updated; one new test
  seeding a mixed grouped/null-story/filing set to prove the full nested shape end to end.
- `docs/adr/0013-*.md` — written during planning, before any code.

## Database / data model changes

None. `stories(id, ticker)` and `headlines.story_id` already carry everything needed.

## API / interface changes

`/api/search`'s response drops `today`/`recent`, gains `days`:

```json
{
  "ticker": "AAPL",
  "status": "success",
  "providers": {...},
  "grouping": "ok",
  "days": [
    {
      "date": "2026-09-17",
      "is_today": true,
      "stories": [
        {
          "story_id": "uuid-or-null",
          "primary": { "title": "...", "url": "...", "category": "...", "provider": "...", "outlet": null, "summary": null, "published_at": "..." },
          "other_members": []
        }
      ]
    }
  ]
}
```

`grouping` untouched (ADR 0012). This is a breaking change to the existing frontend contract, accepted per
ADR 0013 — lesson 22 catches the frontend up.

## Backend / frontend changes

Backend only. The frontend visibly breaks against this response until lesson 22 rebuilds `search.ts`/
`SearchPage.tsx` — accepted, not a regression to guard against here.

## Existing tests / new tests required

**Existing**: `test_search.py`'s DST/boundary tests need to survive in the new shape (grouped by day, not
split into two fixed buckets). `test_search_endpoint.py`'s two integration tests need their body assertions
updated from `today`/`recent` to `days`.

**New**: grouping (shared `story_id` → one Story with correct primary/`other_members`), null-`story_id` →
singleton Story (not merged with other nulls, not dropped), day-bucketing correctness (including the DST
cases), sort order (days newest-first, Stories within a day newest-first), and one integration test proving
the full nested response shape with a realistic mixed set.

## Risks and assumptions

- Both open questions from planning are now resolved (ADR 0013) — no remaining ambiguity before implementation.
- The frontend break is accepted, not mitigated, per ADR 0013 Decision 1.

## Incremental steps

1. Write ADR 0013 (done).
2. Replace `split_today_recent` with the grouping/day-bucketing function(s) in `search.py`.
3. Wire the new function(s) into `/api/search`'s response.
4. Rewrite `test_search.py`; update and extend `test_search_endpoint.py`.
5. Live-verify against the running stack.
6. Update `NOTES.md`; write lesson content.

## What actually happened

Steps 1-6 all completed as planned, with two real findings along the way:

- **Null-`story_id` handling required real care, not just a note.** `_group_into_stories` buckets by
  `story_id`, falling back to the headline's own `id` as the group key when `story_id is None` — a naive
  `groupby(story_id)` would have silently merged every currently-ungrouped headline (grouping skipped/errored,
  ADR 0012) into one fake Story. Covered directly by
  `test_null_story_id_headlines_become_separate_singleton_stories`.
- **`headlines.story_id` has a live FK into `stories`** — not previously exercised by any test using a bare
  `uuid4()` as a `story_id`. The new integration test (`test_search_returns_grouped_daily_view`) hit this
  immediately as a real `ForeignKeyViolationError`; fixed by seeding real `Story` rows first, matching how
  production code always creates the Story row before ever assigning its id to a headline.

Design choice made during implementation, not anticipated in the plan doc's pseudocode: day-bucketing happens
*before* grouping into Stories (bucket every headline by its own Eastern day, then group each day's bucket
into Stories independently), not after (group into Stories first, then bucket by the primary's day). Both are
equivalent given ADR 0006's day-scoping invariant, but bucketing first doesn't rely on that invariant holding
— it reflects each headline's own real day regardless.

38/38 tests passing (5 new: 4 in `test_search.py` for grouping/day-bucketing behavior beyond the ported DST
cases, 1 new integration test). Live-verified against the real running stack (`api`/`worker` rebuilt): real
`/api/search?ticker=AAPL` returned 8 day-buckets — Today (empty, correctly still present) plus 7 populated
earlier days — including several genuinely multi-member Stories (one primary with 4 other members), zero
worker/api errors.
