# Lesson 28 plan — `/api/search` reshaped again for sentiment

Scope per `NOTES.md`: response gains per-Headline sentiment fields and each Story's own aggregate. The
page-level `sentiment` status and `/api/search/status` already exist as of lesson 26 — this lesson is
specifically about exposing the individual data.

## Two decisions made during planning, confirmed before writing code

1. **`derive_sentiment_enum` (+ its two threshold constants) moved from `providers.py` to `config.py`.**
   `search.py` needs it too, and letting it import from `providers.py` would pull `pymilvus`'s whole import
   chain into `api` mode for the first time — the same class of risk `RECENT_HEADLINES_WINDOW` was moved to
   `config.py` to avoid last lesson. Renamed from `_derive_sentiment_enum` (module-private) to
   `derive_sentiment_enum` (public), since it's now a genuinely shared utility.
2. **The new per-item field is named `sentiment_enum`, not `sentiment`.** The response already has a
   top-level `sentiment` key — a status (`ok`/`skipped`/`error`/`processing`), a completely different value
   domain from the classification enum (`positive`/`neutral`/`negative`). Reusing the bare name at a nested
   level would mean the same key holds two unrelated kinds of values depending on nesting depth — exactly the
   kind of collision `CONTEXT.md`'s own `_Avoid_` discipline exists to prevent.

## What gets built

- **`config.py`**: `derive_sentiment_enum` + `SENTIMENT_NEGATIVE_MAX`/`SENTIMENT_POSITIVE_MIN`, moved here.
  Signature widened to `int | float` — a Story's own aggregate is an average, not necessarily an integer.
- **`providers.py`**: the old definition removed; nothing in this module actually called it (kept for a
  future external consumer and its own test coverage only), so no internal usage needed updating.
- **`search.py`**:
  - `_headline_to_dict` gains `sentiment_score`, `sentiment_gloss`, `sentiment_rationale`,
    `sentiment_status`, and computed `sentiment_enum` (`None` until a real score exists).
  - `_group_into_stories` gains a second parameter, `stories_by_id: dict` — a real `Story` row lookup, since
    the function only ever had `Headline` rows in scope before. Each Story dict gains `sentiment_average`
    and computed `sentiment_enum`, both `None` when `sentiment_score_count == 0` — always present as nullable
    fields, not conditionally omitted; the frontend's own member-count check (already speced) decides
    whether to render them, not the backend.
  - `build_daily_view` threads `stories_by_id` through (optional, defaults to `{}` — existing callers that
    don't care about sentiment don't need to change).
  - `_load_search_results` gains a second query: every `Story` referenced by this ticker's headlines, built
    into a plain `{story_id: Story}` dict — a second query, not an ORM `relationship()`/join, matching this
    codebase's existing "no SQLAlchemy relationship annotations" convention.

## Existing tests / new tests required

`test_search.py`: `_headline` extended to optionally set sentiment fields; a new `_story` helper; new tests
for resolved vs. pending headline fields, a Story's aggregate when present, when not yet resolved
(`sentiment_score_count == 0` despite a real Story row existing), and when `stories_by_id` isn't passed at
all (existing callers stay valid).

`test_search_endpoint.py`: `_seed_headline` extended the same way; a new integration test seeding a real
2-member Story with known scores, confirming both the primary headline's own fields and the Story's
aggregate appear correctly in a real HTTP response.

## What actually happened during execution

Built exactly as planned, no further redesign needed this time. 75/75 tests (6 new), zero regressions.
Live-verified against the real running stack, not just the mocked tests:

- A real single-member MSFT Story: `sentiment_average: 60.0`, `sentiment_enum: "neutral"`, matching its one
  member's own `sentiment_score: 60` exactly — confirms a Story of one still gets a real (if trivial)
  aggregate at the data level, with the frontend's own member-count check (lesson 29) responsible for
  deciding whether to render it, exactly as designed.
- A real 3-member MSFT Story: `sentiment_average: 80.67`, matching `(85 + 82 + 75) / 3` exactly, computed
  independently from the same real, live-scored data lesson 26 already produced.
