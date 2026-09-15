# News Search

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
- SEC filing results are limited to the filing types that actually read as news (10-K, 10-Q, 8-K, S-1,
  DEF 14A) — not flooded with routine Form 3/4/5 insider-ownership paperwork
- avoiding duplicate entries — dedup by source URL, upserted, so re-fetching something already seen updates it
  rather than duplicating it
- each individual list entry has a link to its source and shows its published date/time
- each entry also shows its **outlet** (the original publisher, e.g. "Yahoo" — distinct from which provider
  fetched it, see `CONTEXT.md`) when the provider reports one, and a short **summary** blurb under the headline
  when the provider gives us one for free
- gathering only information from a recent timeframe of the past week
- a manual **Refresh** button that re-triggers the live fetch for the current ticker on demand
- if one provider fails, still show results from the one that succeeded (partial results) — log the failure,
  don't stop the process, and surface a simple success/partial-failure/complete-failure status in the UI

## Non-goals

- no complete historical gathering of news or filings
- no gathering of news or filings older than a week
- no sentiment analysis of articles/filings — a separate concern, own spec once this ships. **Not spec 0002**:
  that slot went to near-duplicate/story grouping instead (`docs/specs/0002-daily-story-grouping.md`) — a
  later spec number, TBD.
- no embedding-based near-duplicate detection across sources — was deferred here; now underway, see
  `docs/specs/0002-daily-story-grouping.md`
- no ticker validation against a known list — an invalid/unknown ticker just yields an empty or error result,
  not a rejected search
- no Refresh button throttle/cooldown — personal-project scale doesn't warrant it yet; noted as a future idea
- no stale-then-fresh loading (showing cached results immediately while a live fetch runs in the background,
  then updating) — v1 is a single request/response; noted as a future idea
- no pruning/retention policy for persisted headlines — rows accumulate indefinitely at this scale
- no merging of ticker share classes — `GOOG`/`GOOGL` are fully independent tickers with independent results
- no scheduled/watchlist-based polling yet — that's a future feature this spec's fetch logic is deliberately
  written to support later (see Inputs), not something v1 builds
- no filtering of a provider's own *relevance* tagging — an aggregator occasionally tags an article as related
  to a ticker it isn't really about (verified live against Finnhub); accepted as noise inherent to using an
  aggregator, not something this pass tries to correct. (Distinct from the filing-*type* allowlist under
  Goals — that filters by what kind of document it is, not by whether it's genuinely about the ticker.)
- no fetching full article/filing bodies — `raw_content` exists on `Headline` but stays unpopulated in this
  pass; `summary` (a short blurb the provider gives us directly) covers the UI need for now

## Core entities & terminology

Canonical definitions live in `CONTEXT.md` — `Ticker`, `Company` (the persisted row a Ticker identifies: CIK +
name, both nullable), `Provider`, `Outlet`, and `Headline` (which absorbed what an earlier draft called
`Source`: a headline's title, URL, `summary`, raw content, `category`, `outlet`, published timestamp, and
eventually `sentiment`). Kept there rather than duplicated here to avoid drift as the model evolves.

## Inputs / data sources

User input: a ticker symbol typed into the search bar. No pre-validation — whatever's typed is passed straight
to the fetch.

Providers for v1:
- **SEC EDGAR** full-text search / filing feeds — official, free, no API key (a `User-Agent` header identifying
  the app is required by SEC's usage policy). Filings only.
- **Finnhub** company-news endpoint — free tier, ticker-native (no keyword-matching needed). News only.

Both are called concurrently per search/Refresh. Each returns a different shape (field names, date formats) —
normalizing both into one `Headline` shape (title, published timestamp, `category`, URL, provider, `outlet`,
`summary`, raw content) is real ingestion work. Verified live against Finnhub's real `company-news` endpoint:
its `source` field maps to `outlet` (e.g. `"Yahoo"`), its `summary` field maps directly.

**EDGAR filings require a ticker → CIK lookup first**, not full-text search as originally worded here — SEC's
own `company_tickers.json` maps a symbol to its permanent CIK (and the company's real name, for free in the
same lookup), which `data.sec.gov/submissions/CIK{cik}.json` then needs to list that company's actual filings.
Verified live: real filings have no natural title (constructed from `form` + `primaryDocDescription`), no
`outlet`/`summary` (EDGAR is the authoritative source, not an aggregator), and `published_at` must come from
`acceptanceDateTime` (a real timestamp), not `filingDate` (a bare date with no time). **The raw feed is
dominated by routine Form 3/4/5 ownership filings** — verified live against AAPL's real filings — so it's
filtered to an allowlist of the filing types that actually read as news: `10-K`, `10-Q`, `8-K`, `S-1`,
`DEF 14A`. This is unlike the Finnhub `related`-field noise (an occasional outlier, left unfiltered, see
Non-goals) — routine ownership filings are the *majority* of what this feed returns, not a rare miss.

The ticker → CIK/name lookup result is **cached in a new `companies` table** (`ticker` primary key, nullable
`cik`, nullable `company_name`) rather than re-fetched from SEC on every search — CIKs are permanent, so this
is stable reference data, not something that needs to be live per request. Sequencing: check `companies` first;
if missing, look up via `company_tickers.json`; if that finds a match, upsert `companies` with `cik` and
`company_name` both populated in one step (no null-then-backfill needed — the lookup gives both at once); if it
finds no match but Finnhub still returns real headlines for that ticker, upsert `companies` with `cik`/
`company_name` left null (a legitimate state — an EDGAR-uncovered but real, Finnhub-covered ticker — not a
placeholder to fix later); if *neither* provider returns anything, no `companies` row is created at all. This
sequencing is deliberate: it's what keeps `companies` free of rows for typos/nonexistent tickers without a
separate cleanup job — nothing is ever written speculatively, only once a provider has confirmed there's real
data that needs a home.

`Headline.ticker` is a real foreign key into `companies(ticker)`, not a bare denormalized string.

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

Both lists sorted newest-first. Each entry shows: title, a category badge (News or Filing), its outlet when the
provider reports one (e.g. "via Yahoo"), published date/time, a link to the source, and — when available — a
short summary blurb rendered under the headline.

If a provider call fails, the page still shows whatever succeeded, plus a simple status indicator: success,
partial failure (one provider down), or complete failure. The failure itself is logged server-side. A job that
never completes in time (worker down, or the fetch hangs past its timeout — see ADR 0004) is a complete failure
too, surfaced the same way, not a hung request.

Empty state: a ticker with no headlines in the past week at all says so plainly, not looking broken or stuck
loading.

No sentiment/analysis output in this feature — that's explicitly out of scope (see Non-goals above; not spec
0002, which is near-duplicate/story grouping instead — see `docs/specs/0002-daily-story-grouping.md`).

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
- Finnhub-sourced entries show a real outlet (e.g. "Yahoo") and a real summary blurb — not blank, not the
  literal string "finnhub" (which would mean provider and outlet got confused with each other).
- SEC filing results are limited to 10-K/10-Q/8-K/S-1/DEF 14A — a real company's routine Form 3/4/5 ownership
  filings don't flood the Filings list.
- Searching a nonexistent/typo'd ticker creates no `companies` row at all — verifiable by querying the table
  directly after such a search.
- Searching the same real ticker twice only looks up its CIK from SEC once — the second search reads the
  cached `companies` row, not `company_tickers.json` again.
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
