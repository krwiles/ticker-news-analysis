# News Search

*Rename this file once the name settles — keep the `0001-` prefix, next spec is `0002-`.*

This is the spec for the first real feature built on top of the walking skeleton. It gives lessons 6–8
(FastAPI+SQLAlchemy, React, React Router) a real entity to teach against instead of an invented placeholder —
see `NOTES.md`'s arc-2 hinge. Finalized via a grilling + domain-modeling round; entity definitions live in
`CONTEXT.md`, not duplicated here.

## One-line summary

This feature lets a user search for a ticker symbol and see the most recent news and SEC filings about that
company, fetched live from multiple providers and shown as two recency-based lists — Today and Recent — with a
category badge distinguishing news from filings.

## Problem / motivation

A user needs to see the most recent headlines, SEC filings, and news about a specific stock ticker (company) —
e.g. AAPL, MSFT — without having to search online manually.

## Goals

- a search bar to input a ticker symbol for searching
- a results page with two lists by recency: **Today** and **Recent** (the rest of the past week) — mutually
  exclusive, no headline appears in both
- each entry shows a **category badge** (News or Filing) rather than the page being split into separate
  category lists
- automatically and concurrently searching multiple trustworthy providers for this information (SEC EDGAR for
  filings, Finnhub for news — fetched with `asyncio.gather`, not sequentially, since a real user is waiting on
  this request)
- avoiding duplicate entries — dedup by source URL, upserted, so re-fetching something already seen updates it
  rather than duplicating it
- each individual list entry has a link to its source and shows its published date/time
- gathering only information from a recent timeframe of the past week
- a manual **Refresh** button that re-triggers the live fetch for the current ticker on demand
- if one provider fails, still show results from the one that succeeded (partial results) — log the failure,
  don't stop the process, and surface a simple success/partial-failure/complete-failure status in the UI

## Non-goals

- no complete historical gathering of news or filings
- no gathering of news or filings older than a week
- no sentiment analysis of articles/filings — a separate concern, own spec (0002) once this ships
- no embedding-based near-duplicate detection across sources — Milvus is deferred; this pass's dedup is
  link-based only
- no ticker validation against a known list — an invalid/unknown ticker just yields an empty or error result,
  not a rejected search
- no Refresh button throttle/cooldown — personal-project scale doesn't warrant it yet; noted as a future idea
- no stale-then-fresh loading (showing cached results immediately while a live fetch runs in the background,
  then updating) — v1 is a single request/response; noted as a future idea
- no pruning/retention policy for persisted headlines — rows accumulate indefinitely at this scale
- no merging of ticker share classes — `GOOG`/`GOOGL` are fully independent tickers with independent results
- no scheduled/watchlist-based polling yet — that's a future feature this spec's fetch logic is deliberately
  written to support later (see Inputs), not something v1 builds

## Core entities & terminology

Canonical definitions live in `CONTEXT.md` — `Ticker`, `Provider`, and `Headline` (which absorbed what an
earlier draft called `Source`: a headline's title, URL, raw content, `category`, published timestamp, and
eventually `sentiment`). Kept there rather than duplicated here to avoid drift as the model evolves.

## Inputs / data sources

User input: a ticker symbol typed into the search bar. No pre-validation — whatever's typed is passed straight
to the fetch.

Providers for v1:
- **SEC EDGAR** full-text search / filing feeds — official, free, no API key (a `User-Agent` header identifying
  the app is required by SEC's usage policy). Filings only.
- **Finnhub** company-news endpoint — free tier, ticker-native (no keyword-matching needed). News only.

Both are called concurrently per search/Refresh. Each returns a different shape (field names, date formats) —
normalizing both into one `Headline` shape (title, published timestamp, `category`, URL, provider, raw content)
is real ingestion work.

The fetch/normalize/persist logic runs as an **ARQ job** (registered in `worker`'s `WorkerSettings.functions`),
not a function called directly from the HTTP handler — see `docs/adr/0004-fetch-runs-as-an-arq-job.md`.
`/search` and Refresh both trigger it by enqueueing the job and awaiting its result (with a timeout); a future
scheduled watchlist feature will trigger the identical job via `cron_jobs` instead. The fetch always executes
inside `worker`, never inside `api` — chosen deliberately for hands-on practice with ARQ's job-enqueue pattern,
which nothing else in this project's lessons currently exercises (only the heartbeat *cron* does, a different,
narrower pattern).

## Outputs / user-facing behavior

**Endpoint**: `GET /api/search?ticker=AAPL`. All routes are `/api/`-prefixed (`/health` becomes `/api/health`
too) — cheap to do now, and sets up cleanly for a future real deployment putting `ui` and `api` behind one
domain with path-based routing instead of separate ports. There's no separate Refresh endpoint: the **Refresh**
button just calls the exact same `GET /api/search` again for the currently-shown ticker.

User types a ticker into the search bar and gets a results page with two lists:
- **Today** — headlines published today. Empty is a valid, meaningful state (no news today), not an error.
- **Recent** — headlines published in the rest of the past week (excluding today). Never overlaps with Today.

"Today" means **the current calendar day in US Eastern time (`America/New_York`), not UTC and not the viewer's
local timezone** — this is a stock-news tool, so "today" tracks the US market's trading day, deliberately
independent of where the viewer happens to be. Must use a real IANA timezone (not a fixed UTC offset), since
Eastern time shifts between EST/EDT twice a year. The split is **computed fresh on every request** from
`published_at` — never stored as a column on `Headline` (an `is_today` flag would silently go stale the moment
the calendar day rolls over without a request happening to trigger a recompute).

Both lists sorted newest-first. Each entry shows: title, a category badge (News or Filing), provider, published
date/time, and a link to the source.

If a provider call fails, the page still shows whatever succeeded, plus a simple status indicator: success,
partial failure (one provider down), or complete failure. The failure itself is logged server-side. A job that
never completes in time (worker down, or the fetch hangs past its timeout — see ADR 0004) is a complete failure
too, surfaced the same way, not a hung request.

Empty state: a ticker with no headlines in the past week at all says so plainly, not looking broken or stuck
loading.

No sentiment/analysis output in this feature — that's explicitly out of scope (see Non-goals, spec 0002).

## Open questions / assumptions

None outstanding. Resolved via a grilling + domain-modeling round, plus a follow-up architecture/exploration
review: ADR 0004 (fetch runs as an ARQ job), the `/api/`-prefix decision and the ET-market-time Today/Recent
boundary (both above), and the job-await timeout — **10 seconds**, generous enough for two concurrent provider
calls plus ARQ's dispatch delay, short enough that a stuck worker doesn't leave a human staring at a spinner
indefinitely. `CONTEXT.md` carries the entity model; Non-goals above carries what was deliberately deferred.

## Success criteria

- Searching a real, actively-traded ticker returns real headlines from both EDGAR and Finnhub, dated within the
  past week.
- No two entries on the page share the same source URL — dedup-by-URL holds even across repeated
  searches/refreshes of the same ticker.
- Today and Recent never both contain the same headline.
- A headline published just before/after US Eastern midnight lands in the correct list — not off by hours due
  to a UTC-vs-Eastern or DST mistake.
- Every entry's category badge correctly matches its actual kind (news vs. filing).
- Every entry's link opens the real source page, not a 404 or an unrelated redirect.
- A ticker with genuinely no recent news shows the plain empty state — an empty Today list specifically is
  treated as normal, not a bug.
- If one provider fails, the other's results still render, with a status message reflecting
  success/partial/complete failure; the failure is logged, not silently swallowed or shown as a raw error.
- If the ARQ job never completes in time, `/search` resolves to the complete-failure status — not a hung
  request with no response at all.
- Pressing Refresh re-fetches and updates the page correctly.
- Fetched headlines are actually persisted in Postgres — verifiable with a direct query, not just held in
  memory for the one request.
- Search/Refresh feels reasonably quick to a human waiting on it — concurrent (not sequential) provider calls
  within the job help with this, though some added latency from ARQ's job-pickup dispatch is an accepted,
  deliberate trade-off (see ADR 0004), not something to eliminate.
