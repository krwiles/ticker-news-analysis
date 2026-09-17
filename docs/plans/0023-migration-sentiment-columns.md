# Lesson 23 plan — migration: sentiment columns

Scope per `NOTES.md`: nullable columns on `headlines` (score, gloss, rationale, status) and a running
average + member count on `stories` (spec 0005 / ADR 0014). Schema-only, no app logic wired yet — mirrors
lesson 6/17's shape.

## Decisions made during planning (grilled with the user before any code)

1. **No stored `positive`/`neutral`/`negative` enum column, on either table.** It's a pure function of
   `sentiment_score` via a fixed threshold rule — storing it too would recreate exactly the "two facts that
   must stay in sync" problem this project already deliberately avoided for Story's primary (ADR 0009). The
   enum gets derived at read time, in whichever later lesson serializes it into the API response.
2. **Column names**: `sentiment_score`, `sentiment_gloss`, `sentiment_rationale`, `sentiment_status` on
   `headlines`; `sentiment_average`, `sentiment_score_count` on `stories`.
3. **Plain `TEXT`, no `CHECK` constraints** — matches the existing `category` column's own precedent
   (Python-side `Literal` typing only, no DB-level enum enforcement).
4. **`stories` does not get its own `sentiment_status`.** `sentiment_score_count == 0` already
   unambiguously means "no real aggregate yet" — the *why* (pending/skipped/error) is a per-member fact that
   already lives on each Headline's own `sentiment_status`, and the page-level "is sentiment configured and
   working" signal (a new `SentimentStatus` component, spec 0005) covers the aggregate dependency-health
   question once, for the whole page. A Story-level copy of that signal would be redundant.

## What gets built

**Migration** (`db/migrations/20260917231214_add_sentiment_columns.sql`): four nullable columns on
`headlines` (`sentiment_score INTEGER`, `sentiment_gloss TEXT`, `sentiment_rationale TEXT`,
`sentiment_status TEXT`); two on `stories` (`sentiment_average DOUBLE PRECISION`, nullable — no average
until the first member reaches a real score, and `0` would be a real, wrong value; `sentiment_score_count
INTEGER NOT NULL DEFAULT 0` — a real count, starts at zero, not unknown).

**`models.py`**: matching `Mapped` columns on `Headline`/`Story`, plus removing `Headline`'s now-stale
"`sentiment` deliberately not here yet" docstring line.

**No new test file** — schema-only, no logic to exercise yet, same reasoning lesson 6 used. Verification is
the full existing suite passing unchanged, plus a live sanity check.

## Verified

- Live, inside a rolled-back transaction against the real dev database (headlines: ~2000+ rows, stories:
  ~800+ rows) before writing the migration for real: all three `ALTER TABLE` statements — including the
  `NOT NULL DEFAULT 0` one — completed in under 2ms each. Postgres's fast-path for a constant default
  applies; no table rewrite, no lock concern at this project's scale.
- Migration applied cleanly to both the dev and test databases (7ms, 12ms respectively).
- Full backend suite: 46/46, unchanged. Full frontend suite: 59/59, `tsc --noEmit` clean (neither should have
  been affected — confirmed, not assumed).
- Live sanity check against the real test database: inserted a real `Headline` and `Story` row, confirmed
  every new column reads back exactly as designed (`sentiment_score`/`gloss`/`rationale`/`status` all
  `None`; `sentiment_average` `None`; `sentiment_score_count` `0`) — then cleaned up, no leftover data.

## What actually happened during execution

Held to the plan exactly — no redesign this time, unlike lesson 17's circular-FK rewrite. The one thing not
in the plan until it was actually run: the live sanity check's first attempt hit the same real
`headlines_ticker_fkey` constraint spec 0001 already established (a `Headline` needs a real `Company` row
for its ticker to reference) — same shape of gotcha as lesson 21's `headlines_story_id_fkey` finding, not a
new kind of surprise, just the same "insert the real dependency first" discipline applying here too. Fixed
by inserting a `Company` row before the `Headline` in the sanity script; not a schema change.
