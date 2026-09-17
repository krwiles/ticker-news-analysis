# `/api/search`'s response is replaced, not extended, with a per-day list of Stories

Spec 0002 wants one list per calendar day, each holding Stories, replacing spec 0001's `today`/`recent` split.
Two decisions, made during lesson 21's planning, before any code:

## Decision 1: replace the response shape now, not roll out additively

Every earlier lesson in this arc shipped non-breaking (nullable columns, an unused table, an additive
`grouping` field). This one is different: `today`/`recent` are dropped outright and replaced with `days` in
the same change, rather than adding `days` alongside the old fields and removing them only once the frontend
(lesson 22) catches up.

### Considered options

- **Additive rollout** (rejected): keep `today`/`recent` populated as today, add `days` alongside; frontend
  keeps working untouched until lesson 22 switches over and removes the old fields. Consistent with every
  prior lesson's precedent, but doubles the reshaping logic that has to be written and tested for one lesson,
  for a UI that's about to be rebuilt anyway.
- **Replace now** (chosen): simpler to implement and test — one response shape, not two live in parallel. The
  frontend visibly breaks (`SearchPage.tsx` reads `results.today`/`results.recent` directly) until lesson 22
  lands. Accepted explicitly: this is a personal project with no other users, and lessons 21/22 are built back
  to back.

### Consequences

- Between this lesson and lesson 22, the running frontend will throw at render time if `/api/search` is called
  through the UI. Not a regression to guard against — a known, accepted gap.

## Decision 2: only "Today" is always emitted; earlier days appear only if non-empty

Spec 0002's wording ("one list per calendar day in the past week") could mean either a fixed 7-day scaffold or
a variable-length list.

### Considered options

- **Fixed 7-day scaffold, always emitted**: mirrors spec 0001's "Today" section always rendering even when
  empty, extended literally to every day. Rejected: pads the response with up to 6 empty day-buckets on the
  common case (a ticker with sparse news), for no signal a viewer needs.
- **Only Today always emitted; earlier days included only when they have ≥1 Story** (chosen): mirrors how
  "Recent" was already one flexible bucket in spec 0001, not 6 rigid empty ones — "no headlines today" is a
  real, useful signal; "nothing happened on day 4" is not.

### Consequences

- `days` is variable-length: always has a first entry for Today (`stories: []` when empty), followed by zero
  or more earlier days, each guaranteed non-empty.
