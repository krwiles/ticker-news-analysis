# Lesson 17 plan — the `stories` table + migration

Scope per `NOTES.md`: `SQLAlchemy` model + `dbmate` migration for `stories` (`id`/`ticker`/`primary_headline_id`)
and `headlines.story_id`, mirroring lesson 6's shape — schema first, no matching logic yet.

## The central architectural question, and the decision made

Spec 0002 (pre-trim) and ADR 0009 both describe `headlines.story_id` as eventually `NOT NULL`. Making it
`NOT NULL` from the start would require `providers.py`'s existing insert path — and several existing tests —
to immediately supply a story for every headline, before any real matching logic (lesson 19) exists to decide
one correctly.

**Decision, confirmed with the user**: `story_id` nullable for now, tightened to `NOT NULL` once lesson 19's
real matching logic exists to populate it on every path. Same staged-rollout pattern `outlet`/`summary` already
used (added in a later migration, not day one) — a deliberate deviation from ADR 0009's eventual design, which
itself explicitly defers this exact sequencing question to this plan, not to the ADR.

`stories.primary_headline_id` is nullable **permanently**, not staged — a `stories` row is necessarily written
before the headline it will call primary exists (that headline needs a valid `story_id` to reference first),
so `primary_headline_id` starts null and gets backfilled in a second write. A structural consequence of the
circular FK, not a rollout choice.

## What gets built

**Migration** (`db/migrations/20260915180517_create_stories.sql`): `stories` table, `headlines.story_id`
(nullable), both FK constraints (circular — `headlines_story_id_fkey`, `stories_primary_headline_id_fkey`), a
`UNIQUE` constraint on `primary_headline_id` (a headline can be at most one story's primary), indexes on
`stories.ticker` and `headlines.story_id`.

**`models.py`**: new `Story` class, `Headline` gains `story_id` — both plain columns, no SQLAlchemy
`ForeignKey()` annotation, matching the existing `headlines.ticker` precedent (real constraints live in the
migration only).

**One new test** (`test_providers.py`): proves the circular-FK write sequence works end to end — create a
`Story` stub with `primary_headline_id=None`, insert a `Headline` with that `story_id`, backfill the story's
`primary_headline_id`, read both back and confirm the relationship holds.

## Verified

- `uv run pytest`: 18/18 (17 existing + 1 new), zero regressions.
- Full stack sanity check (`docker compose up --build`): `/api/health` and a real `/api/search` both still work
  against the migrated dev database.

## What actually happened during execution (found live, not anticipated in the plan)

**The nullable-column decision didn't fully deliver "zero existing test changes" as claimed.** All 18 tests
failed on the first real run — not from the column itself, but from `conftest.py`'s `_clean_tables` fixture:
`TRUNCATE TABLE headlines, companies` now fails, because `stories` has a FK into `headlines` and Postgres
refuses to truncate a referenced table without the referencing table in the same statement
(`FeatureNotSupportedError: cannot truncate a table referenced in a foreign key constraint`). Fixed by adding
`stories` to the same `TRUNCATE` statement. Worth being honest about: the earlier claim that nullable
`story_id` meant *zero* blast radius on existing tests was half right — no test needed new logic to satisfy a
constraint, but shared test *infrastructure* still needed updating the moment a new table entered the FK graph.
A real, minor correction to the plan's own reasoning, not a failure of the nullable choice itself.

## Revised after initial build: the circular FK itself was unnecessary

The design above shipped `stories.primary_headline_id` as a circular-FK back-pointer, reasoned through
carefully (nullable permanently, backfilled in a second write) and proven correct by the original version of
the new test. Under review, a simpler alternative surfaced: a Story's primary is always its earliest-published
member — a pure function of `story_id` + `published_at`, data `Headline` already has. Storing that fact a
second time (whether as a back-pointer or, the next idea considered, a `headlines.is_primary` flag) is
redundant state with nothing to keep it synchronized, for no real benefit — see ADR 0009's revised Considered
options for the full comparison, including why the flag didn't turn out to be the better middle ground either.

**Final shape**: `stories(id, ticker)` only — no primary reference at all. `headlines.story_id` unchanged.
Primary is found via `ORDER BY published_at ASC LIMIT 1`, backed by a `(story_id, published_at)` index (a
window function for bulk fetches across many stories at once). The migration was rewritten in place — rolled
back and reapplied on both databases — rather than shipping the circular-FK version and correcting it with a
second migration, since nothing had been merged or pushed yet. The test was rewritten too: it now proves the
derivation is correct by inserting two headlines *out of chronological order* and confirming the query still
finds the earlier-published one, not just that insertion order happens to match.

Re-verified after the rewrite: 18/18 tests, full stack sanity check clean.
