# Plan 0035 — headline dedup by (ticker, url), not url alone

Not a lesson, no spec/ADR — confirmed in lesson 34's grilling round that spec 0001's existing
"dedup by URL" wording is already scoped to one ticker's own page/re-fetches ("no two entries on
**the page** share the same source URL"), which still holds true under this fix. This is a
contained implementation fix, not a behavior change spec 0001 promised anything different about.

## The bug, confirmed

`headlines.url` is globally unique; `fetch_and_persist_headlines`'s `ON CONFLICT (url) DO UPDATE`
doesn't touch `ticker`. Confirmed live (lesson 34): a real Finnhub article already stored under
`AAPL` also appears in `AMZN`'s own feed, identical URL — it can never show up in an `AMZN` search,
since the row already belongs to `AAPL` and `_load_search_results` filters on `Headline.ticker`.

## Decision

Change uniqueness to `(ticker, url)`. A shared article now gets one row per ticker that fetches
it — each independently embedded, grouped, and sentiment-scored. Accepted tradeoff (the user's own
call): some duplicated rows and duplicated OpenAI calls for a shared article, in exchange for never
silently hiding a real headline from a ticker's search results.

## What gets built

- **Migration** (`db/migrations/`): drop `headlines_url_idx` (unique on `url` alone), add a new
  unique index on `(ticker, url)`.
- **`models.py`**: `Headline.url` loses its column-level `unique=True`; a table-level
  `UniqueConstraint("ticker", "url")` replaces it.
- **`providers.py`**: `on_conflict_do_update(index_elements=["url"], ...)` becomes
  `index_elements=["ticker", "url"]` — the conflict target must match the real constraint.

## Deliberately unaffected

- `xmax = 0` new-row detection: unaffected, works identically against any real unique constraint.
- Grouping (`_assign_stories`): already scoped per-ticker+day (ADR 0006), never looked across
  tickers.
- `test_dedup_by_url_on_second_fetch`: fetches the *same* ticker twice — still dedupes to one row
  under the new composite key, no change needed.

## Tests

- New: fetching the same URL under two different tickers produces two rows, one per ticker (the
  actual regression test for the bug) — same `respx` mocking shape as the existing dedup test.
- Existing `test_dedup_by_url_on_second_fetch` re-run unchanged to confirm same-ticker dedup still
  holds.

## Verification

1. Backend test suite green.
2. Migration dry-run in a rolled-back transaction against the real dev database (same discipline as
   lesson 23), confirming it applies cleanly against real existing data (no duplicate `(ticker,
   url)` pairs already exist to violate the new constraint — guaranteed, since the old constraint
   was strictly stricter).

## What actually happened

Built as planned. One thing found that the plan hadn't anticipated: `test_grouping.py` had its own
test-local seeding helper (`_insert_new`) that independently duplicated `providers.py`'s
`on_conflict_do_update(index_elements=["url"], ...)` upsert rather than importing the real one —
it needed the same `index_elements` change, or every grouping test broke (9 failures) once the
real constraint changed underneath it.

`db/schema.sql` regeneration was attempted (`dbmate up` ran the migration but silently skipped the
dump since `pg_dump` isn't installed on this host; `libpq`'s `pg_dump` was found and used directly)
but reverted before committing: the resulting diff caught up ~80 lines of unrelated historical
drift (missing `companies` table, sentiment columns, etc.) that every prior migration here left
uncaptured by deliberately using `--no-dump-schema` (README's own documented convention, precisely
to avoid needing `pg_dump`). Regenerating it now would be unrelated scope creep, not part of this
fix — left stale, consistent with how every migration before this one was actually applied.

92/92 backend tests (1 new), zero regressions. Migration dry-run verified in a rolled-back
transaction against the real dev database, then applied for real via `dbmate up`.
