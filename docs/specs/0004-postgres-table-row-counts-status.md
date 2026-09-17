# Postgres Table Row Count Status

This is the spec for showing per-table row counts on the status page's existing Database tile, extending the
same "is data actually flowing, not just is the connection up" idea spec 0003 introduced for Milvus. Builds on
spec 0001's original status page and spec 0003's Milvus tile — no new entities are introduced.

## One-line summary

The status page's Database tile shows a row count for each of the app's three tables (`companies`,
`headlines`, `stories`) alongside its existing connected/error state.

## Problem / motivation

The Database tile today only proves Postgres is reachable — a connected-but-empty database and a
connected-and-populated one look identical. Spec 0003 already gives the Milvus tile this kind of concrete
"data is really there" signal; the Database tile has no equivalent, even though it's arguably the more central
data store in this project.

## Goals

- The Database tile shows a row count for each of `companies`, `headlines`, and `stories`, one per line — not
  one combined line, which wraps awkwardly at the tile's width.
- Counts cover exactly these three tables, named explicitly — not every table the database happens to contain
  (`dbmate`'s own migration-bookkeeping table is never included).
- A failure that happens while counting is reported the same way a connection failure already is — no new
  status is introduced beyond the Database tile's existing connected/error states. A table is never in a
  legitimate "not yet initialized" state the way Milvus's on-demand collection was (spec 0003); an empty table
  just reports a real `0`.
- Counts are always phrased in the plural, regardless of the actual number (e.g. "1 companies"). The existing
  Milvus tile's own count is updated to this same convention, so both tiles read consistently.

## Non-goals

- No separate tiles or sub-list per table — the three counts still live on the one existing Database tile,
  just as separate lines within it, not as their own tiles.
- No historical/trend view of row counts over time.
- No automatic coverage of a future new table — the three tables are named explicitly; adding a fourth table
  to the schema later doesn't automatically appear here.
- No alerting on row counts — the status page is something a human checks, not something that pages anyone.
- No change to how a connection failure itself is detected or reported.

## Core entities & terminology

No new entities. `Company`, `Headline`, `Story` — unchanged, as already defined in `CONTEXT.md`.

## Outputs / user-facing behavior

The Database tile, when connected, shows all three counts stacked as separate lines, each always phrased in
the plural — e.g. "3 companies" / "428 headlines" / "210 stories" on their own lines, or "1 companies" for a
count of exactly one. A disconnected database still shows Error exactly as it does today, with no counts
shown. The existing Milvus tile's own count adopts this same always-plural phrasing, for consistency between
the two tiles.

## Success criteria

- With Postgres reachable, the Database tile shows all three real counts, matching a direct query of each
  table.
- A new row in any of the three tables is reflected on the next refresh — not stale or cached.
- An empty table shows a real `0`, not an error and not a missing/blank field.
- Stopping Postgres still shows Error, exactly as it does today — no regression to existing connection-failure
  behavior.
- The migration-bookkeeping table never appears in the reported counts.
- The Database and Milvus tiles both use the same always-plural phrasing for their counts.

## Technical approach

Left to an implementation plan, following this project's usual `/teach` sequencing. No new ADR is expected —
this is a status-visibility addition, not a new design decision, the same reasoning spec 0003 used.
