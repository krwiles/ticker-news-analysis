# Daily Story Grouping

This is the spec for grouping near-duplicate headlines into Stories and reshaping the results page around
per-day lists, building on top of spec 0001's shipped News Search feature. It claims the `0002-` slot spec
0001's own Non-goals originally earmarked for sentiment analysis — sentiment moves to a later, not-yet-numbered
spec; spec 0001's two references to that have been corrected accordingly. Finalized via a grilling round;
entity definitions live in `CONTEXT.md` (see its new `Story` entry), not duplicated here.

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
- Same-day, same-ticker `news`-category headlines whose `title`+`summary` embeddings (OpenAI) are similar
  enough become one **Story**. Matching is threshold-based against each existing Story's **primary**
  headline — its earliest-published member, fixed once set — never against every member of every Story.
- A Story displays its primary headline in full, per spec 0001's existing single-Headline rules. Other members
  (if any) sit behind an expandable list with a coverage count; a Story of one shows neither.
- **Filings never participate in grouping** — always a Story of one. EDGAR is the sole authoritative source per
  filing, so the real near-duplicate problem is a `news`/multi-outlet one specifically.
- Within one fetch, only headlines not already persisted are embedded and matched, processed oldest-to-newest
  by `published_at` — so the first one processed for an eventual Story is genuinely the one that broke it, not
  whichever a provider's API happened to return first. Already-persisted headlines are never re-embedded or
  re-matched.

## Non-goals

- No cross-day or cross-ticker grouping.
- No user-facing manual editing of a Story (splitting, merging).
- No re-evaluation of already-persisted headlines — a Story assignment is permanent once made.
- **No backfill of existing headlines' Story assignment.** Postgres is just a cache of EDGAR/Finnhub, never the
  source of truth — existing `headlines`/`companies` rows can be wiped and re-collected fresh once this ships,
  no information lost, rather than migrated in place.
- **No Milvus partitioning in v1** — plain scalar-field filtering (ticker + day) instead. Named explicitly
  because standalone Milvus (not the simpler Milvus Lite) was chosen for hands-on scalability exposure, not
  because this project's data volume will ever need it.
- No sentiment analysis — separate concern, later spec (see header).
- Everything spec 0001 already ruled out stays ruled out.

## Core entities & terminology

Canonical definitions live in `CONTEXT.md`. This spec adds one entry, `Story` — see that file for the full
definition. `Ticker`, `Company`, `Provider`, `Outlet`, `Headline`, `Today` are all unchanged.

## Inputs / data sources

**Embedding**: `title` + `summary` when present, `title` alone otherwise (not every headline has a summary).
OpenAI's embeddings API — same integration shape as the existing EDGAR/Finnhub calls in `providers.py`,
computed once inside `fetch_and_persist_headlines`, only for headlines not already persisted. Also sets up
shared infrastructure a future sentiment spec will likely reuse.

**Milvus**: standalone, new service(s) in `docker-compose.yml`. Only a Story's primary headline's embedding
ever gets inserted — a joining headline never gets its own vector, since only primaries are ever compared
against and a primary never changes. One vector per Story, not per Headline.

**Matching flow**: for each new headline, in oldest-to-newest order, embed it and search Milvus for the
nearest same-ticker, same-day primary above a threshold. Matched → reuse that Story's `id`. Unmatched → new
`stories` row, this headline becomes its primary, its embedding gets inserted. The threshold itself has no
value yet — deferred to implementation, tuned against real headline pairs, same discipline as spec 0001's own
concrete numbers (the 7-day window, the 10-second job timeout).

**Data model**: a new `stories` table — `id`, `ticker`, `primary_headline_id` (a real FK into `headlines.id`).
Deliberately minimal, no `sentiment` column pre-built for a spec that doesn't exist yet. `headlines.story_id`
becomes a real, `NOT NULL` FK into `stories.id`, same discipline `headlines.ticker` already uses for
`companies` — every headline gets one, even a Story of one. A `stories` row is written before the headline
that references it, when no match is found (an FK consequence, not just convention).

## Outputs / user-facing behavior

One list per calendar day, Today first and specially labeled, each sorted newest-first — replacing spec 0001's
Today/Recent lists. Within a day, each entry is a Story: primary headline rendered per spec 0001's existing
rules, other members (if any) behind an expandable list with a coverage count. Refresh, the status indicator,
and the job/enqueue mechanics are otherwise unchanged from spec 0001.

## Open questions / assumptions

Every domain-level question from this spec's grilling round is resolved above. What's left is
implementation-level, not a domain question:

- The exact `/api/search` response shape for N-day grouping (replacing `today`/`recent` with something that
  represents an arbitrary number of days, each holding Stories) — not yet designed.
- Exact `docker-compose.yml` wiring for standalone Milvus (service names, healthchecks, arm64 image specifics).
- The similarity threshold value (see Inputs above).

## Success criteria

- Two same-day headlines from different providers, genuinely about the same event, render as one Story.
- Two same-day, textually-similar-but-genuinely-different headlines never incorrectly group.
- Two headlines about a recurring-report topic (e.g. sequential quarterly earnings) from *different* days never
  group — enforced structurally, since matching never crosses a day boundary.
- A Story's primary is always its earliest-published member, never reassigned once set.
- A Story's shown coverage count matches its actual member count.
- Every source within a Story stays independently clickable to its own real URL.
- Filings never group with anything, including each other.
- One list per day in the past week, Today first and specially labeled, each sorted newest-first.
- Grouping never spans two tickers.
- Re-searching or refreshing doesn't reshuffle or duplicate existing Stories — only genuinely new headlines are
  ever evaluated for matching.
