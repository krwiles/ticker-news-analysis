# A real `stories` table, not a bare `story_id` column — and no stored "primary headline" reference

ADR 0006's grouping mechanism needs some way to represent "these headlines belong to the same Story." The
minimal representation would be a `story_id` column on `headlines` alone — a shared UUID value with no
accompanying row anywhere. Nothing about the matching mechanism itself strictly requires a separate table to
exist.

Decision: a real `stories` table (`id`, `ticker`), with `headlines.story_id` a real FK into it — the same
"real FK, not a bare denormalized column" discipline spec 0001 already established for `headlines.ticker` into
`companies`. `stories` deliberately carries **no reference to its primary headline** — see Considered options.

## Considered options

- **A bare `story_id` column, no accompanying table**: simplest possible representation. Every Story-level fact
  would need deriving via a query against `headlines` every time, with nowhere to hang anything that isn't
  strictly derivable from its member headlines.
- **A real `stories` table** (chosen for the table itself): one extra table and migration, in exchange for a
  real place to hang future Story-level data — specifically, a likely future sentiment-analysis spec's need to
  store an aggregate sentiment score *per Story*, not just per Headline. Deliberately minimal itself: no
  `sentiment` column pre-built now for a spec that doesn't exist yet — the same discipline `Headline`'s own
  model already applies to its own still-absent `sentiment` field.
- **Store the primary headline explicitly** — first as `stories.primary_headline_id` (a back-pointer, creating
  a circular FK with `headlines.story_id`), then as `headlines.is_primary` (a boolean flag instead, avoiding
  the circular reference but not the redundancy). Both considered and both rejected on the same grounds: a
  Story's primary is always its earliest-published member — a pure function of `story_id` + `published_at`,
  data `Headline` already has. Storing that fact a second time, in either shape, is redundant state with
  nothing to keep it synchronized, for no real benefit — a window function (`ROW_NUMBER() OVER (PARTITION BY
  story_id ORDER BY published_at)`) serves bulk "give me every story's primary" lookups exactly as well with
  either approach, so the flag/back-pointer bought nothing even at the query-ergonomics level it was meant to
  simplify. The circular-FK version was actually built first (lesson 17), then replaced before ever shipping,
  once this reasoning surfaced under review.
- **Derive the primary via query, store nothing** (chosen): `ORDER BY published_at ASC LIMIT 1`, backed by a
  `(story_id, published_at)` index. No redundant state, no circular FK, no write-time bookkeeping for
  primariness at all.

## Consequences

- One additional table and SQLAlchemy model to maintain going forward — otherwise minimal: just `id`, `ticker`.
- No circular FK anywhere in this schema — `headlines.story_id → stories.id` is the only cross-reference,
  one direction only.
- Every call site that needs "this Story's primary headline" has to use the derivation query (or the
  window-function form for bulk fetches) rather than following a stored pointer — a real, accepted trade-off
  for having zero state that could ever drift out of sync with `published_at`.
- If a future feature ever needs primary-ness to be something *other* than a pure function of
  `published_at` (e.g., a user manually picking a different representative headline — currently out of scope,
  see spec 0002's Non-goals), a stored reference would become genuinely necessary at that point, not before.
- Whether `headlines.story_id` itself is `NOT NULL` from the start, or nullable now and tightened once real
  matching logic exists to populate it, is a separate, lesson-sequencing decision — not settled by this ADR,
  see `docs/plans/0017-*.md`.
