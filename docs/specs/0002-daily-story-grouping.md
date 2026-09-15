# Daily Story Grouping

This is the spec for grouping near-duplicate headlines into Stories and reshaping the results page around
per-day lists, building on top of spec 0001's shipped News Search feature. It claims the `0002-` slot spec
0001's own Non-goals originally earmarked for sentiment analysis — sentiment moves to a later, not-yet-numbered
spec; spec 0001's two references to that have been corrected accordingly. Finalized via a grilling round;
entity definitions live in `CONTEXT.md` (see its `Story` entry). The technical approach lives in ADRs
0006–0009, not here — this document describes desired behavior only.

## One-line summary

Headlines about the same real-world event, published by different providers on the same calendar day for the
same ticker, are grouped into a single **Story** showing every source and a coverage count, and the results
page shows one list per calendar day in the past week instead of spec 0001's Today/Recent split.

## Problem / motivation

Two problems spec 0001 explicitly deferred, both real:

1. **Near-duplicate coverage isn't caught by link-based dedup.** Spec 0001's dedup is exact-URL-only; two
   providers covering the same real event under different URLs — verified as a real pattern live against
   Finnhub's aggregator feed — show up as separate, redundant entries today.
2. **Coverage volume is itself a signal, currently invisible.** A story covered by three independent outlets
   likely matters more than one covered by none, and there's no way to read a second source's take without it
   appearing as a separate, unconnected entry.

Grouping (not omitting) near-duplicates solves both: it declutters *and* surfaces attention.

## Goals

- The results page shows **one list per calendar day** in the past week, not spec 0001's Today/Recent split —
  Today first, specially labeled (day-trading tool, "today" stays primary), every earlier day by its date, each
  sorted newest-first.
- Same-day, same-ticker `news`-category headlines that are genuinely about the same real-world event are
  grouped into one **Story**.
- A Story displays one headline — its **primary** — in full, per spec 0001's existing single-Headline rules.
  Which member is primary is chosen consistently and never changes once set. Other members (if any) sit behind
  an expandable list with a coverage count; a Story of one shows neither.
- **Filings never participate in grouping** — always a Story of one.
- A Story's assignment, once made, is permanent — it is never re-evaluated later.

## Non-goals

- No cross-day or cross-ticker grouping.
- No user-facing manual editing of a Story (splitting, merging).
- No re-evaluation of an already-assigned Story.
- No sentiment analysis — separate concern, later spec (see header).
- Everything spec 0001 already ruled out stays ruled out.

## Core entities & terminology

Canonical definitions live in `CONTEXT.md`. This spec adds one entry, `Story` — see that file for the full
definition. `Ticker`, `Company`, `Provider`, `Outlet`, `Headline`, `Today` are all unchanged.

## Outputs / user-facing behavior

One list per calendar day, Today first and specially labeled, each sorted newest-first — replacing spec 0001's
Today/Recent lists. Within a day, each entry is a Story: primary headline rendered per spec 0001's existing
rules, other members (if any) behind an expandable list with a coverage count. Refresh, the status indicator,
and the search/fetch mechanics are otherwise unchanged from spec 0001.

## Success criteria

- Two same-day headlines from different providers, genuinely about the same event, render as one Story.
- Two same-day, textually-similar-but-genuinely-different headlines never incorrectly group.
- Two headlines about a recurring-report topic (e.g. sequential quarterly earnings) from *different* days never
  group.
- A Story's primary is always its earliest-published member, never reassigned once set.
- A Story's shown coverage count matches its actual member count.
- Every source within a Story stays independently clickable to its own real URL.
- Filings never group with anything, including each other.
- One list per day in the past week, Today first and specially labeled, each sorted newest-first.
- Grouping never spans two tickers.
- Re-searching or refreshing doesn't reshuffle or duplicate existing Stories.

## Technical approach

See `docs/adr/0006-story-grouping-via-embedding-similarity.md` (the matching mechanism), `0007-openai-embeddings-for-story-matching.md`
(embedding technology), `0008-standalone-milvus-over-milvus-lite.md` (vector database deployment), and
`0009-stories-table-not-bare-column.md` (data model shape). Lesson-by-lesson implementation sequencing lives in
`docs/plans/`, not here.
