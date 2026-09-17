# Milvus Vector Store Status

This is the spec for surfacing the health of the Milvus vector store — introduced in spec 0002 for Story
grouping — on the existing status page, alongside the existing api/db/redis/worker checks. Builds on spec
0001's original status page (`/api/health`, `StatusPage`) and spec 0002's Milvus deployment (see
`docs/adr/0008-standalone-milvus-over-milvus-lite.md` and `0011-milvus-story-collection-design.md`). No new
entities are introduced.

## One-line summary

The status page gains a new tile for Milvus, reporting whether the vector store is reachable and — when it
is — how many Story primaries are actually indexed in it, using the same aggregate `/api/health` check the
existing db/redis/worker tiles already rely on.

## Problem / motivation

Spec 0002 added a whole new infrastructure dependency (standalone Milvus) that the grouping pipeline silently
depends on, but the status page — the one place this project surfaces "is everything actually working" — has
no idea it exists. If Milvus goes down, or the `story_primaries` collection is missing, grouping fails silently
(headlines still show, just never grouped) with nothing on the status page pointing at the real cause.

## Goals

- Add a Milvus check to the existing aggregate `/api/health` endpoint, alongside the existing db/redis/worker
  checks.
- The check reports whether the vector store is reachable (ok/error), and separately — when reachable —
  whether the `story_primaries` collection actually exists.
- When reachable and the collection exists, the check also reports how many vectors (Stories) are currently
  indexed — a concrete signal that grouping is actually persisting data, not just "the connection works."
- The status page gains a new tile, `Milvus`, rendered the same way as the existing tiles (dot + label +
  optional detail line), in the same list, using the existing `StatusTile` component.
- Follows the same polling/refresh behavior already on the status page — no separate poll loop just for this
  tile.

## Non-goals

- No breakdown per-ticker or per-day of what's indexed — a single aggregate count is enough.
- No historical/trend view (e.g. a graph of vector count over time) — current snapshot only.
- No alerting/notifications on Milvus going down — the status page is something a human checks, not something
  that pages anyone.
- No new page or route — this extends the existing status page, doesn't add another one.
- No change to how grouping itself behaves when Milvus is down — that failure mode is already handled (see ADR
  0011); this spec is purely about making that state visible, not changing it.

## Core entities & terminology

No new entities. Uses `story_primaries`, the existing Milvus collection defined in
`docs/adr/0011-milvus-story-collection-design.md`.

## Outputs / user-facing behavior

The existing `/api/health` response gains one new key, `milvus`, alongside `api`/`db`/`redis`/`worker`,
following the same `{"status": ..., "detail": ...}` shape the other checks already use.

The status page shows a new tile, positioned after the existing `Worker` tile: `Milvus`. Its states:

- **Connected** — Milvus is reachable and `story_primaries` exists; detail line shows the current vector count
  (e.g. "142 stories indexed").
- **Error** — Milvus is unreachable, or reachable but the collection doesn't exist yet; the detail line says
  which.
- **Unknown** — the same fallback the other tiles already show before the first successful poll resolves.

## Success criteria

- With Milvus and the collection both healthy, the tile shows Connected and a vector count that matches
  `story_primaries`'s real row count, verifiable by querying Milvus directly.
- Stopping the Milvus container causes the tile to flip to Error within one polling interval, without the rest
  of the status page (or `/api/health`) breaking or hanging.
- A fresh environment where the collection hasn't been created yet shows a distinct Error detail from "Milvus
  unreachable" — an operator can tell the two failure modes apart.
- The existing api/db/redis/worker tiles are unaffected — this is a strict addition, not a reshape of the
  existing health check.

## Technical approach

Left to an implementation plan/lesson, following this project's usual `/teach` sequencing. No new ADR is
expected — this is a status-visibility addition on top of infrastructure Milvus already has ADRs for (`0008`,
`0011`), not a new design decision.
