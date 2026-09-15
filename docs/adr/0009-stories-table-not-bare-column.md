# A real `stories` table, not a bare `story_id` column

ADR 0006's grouping mechanism needs some way to represent "these headlines belong to the same Story." The
minimal representation would be a `story_id` column on `headlines` alone — a shared UUID value with no
accompanying row anywhere. Nothing about the matching mechanism itself strictly requires a separate table to
exist.

Decision: a real `stories` table (`id`, `ticker`, `primary_headline_id`), with `headlines.story_id` a real FK
into it — the same "real FK, not a bare denormalized column" discipline spec 0001 already established for
`headlines.ticker` into `companies`.

## Considered options

- **A bare `story_id` column, no accompanying table**: simplest possible representation. Every Story-level fact
  (its primary headline, its ticker) would need deriving via a query against `headlines` every time, with
  nowhere to hang anything that isn't strictly derivable from its member headlines.
- **A real `stories` table** (chosen): one extra table and migration now, in exchange for a real place to hang
  future Story-level data — specifically, a likely future sentiment-analysis spec's need to store an aggregate
  sentiment score *per Story*, not just per Headline, which a bare column could never represent on its own.
  Deliberately minimal itself: no `sentiment` column pre-built now for a spec that doesn't exist yet — the same
  discipline `Headline`'s own model already applies to its own still-absent `sentiment` field.

## Consequences

- One additional table and SQLAlchemy model to maintain going forward.
- A real circular FK relationship: `stories.primary_headline_id` → `headlines.id`, and `headlines.story_id` →
  `stories.id`. `primary_headline_id` must be nullable — not a rollout placeholder, a permanent structural
  consequence — because a `stories` row is necessarily written before the headline it will call primary exists
  (spec 0002's own write ordering: a new Story's row has to exist first so the headline can reference it).
- Whether `headlines.story_id` itself is `NOT NULL` from the start, or nullable now and tightened once real
  matching logic exists to populate it, is a separate, lesson-sequencing decision — not settled by this ADR,
  see `docs/plans/0017-*.md`.
