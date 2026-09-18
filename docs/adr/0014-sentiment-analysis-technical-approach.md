# Sentiment analysis: mechanism, job architecture, storage shape, and filing extraction strategy

Spec 0005's own grilling round covered a lot of technical ground before any code exists. This ADR is where
that reasoning and evidence live, so it isn't lost the way a conversation transcript eventually is — spec
0005 itself stays behavior-only by design. Several numbers here are explicitly working values, not final;
each is marked as such.

## Mechanism: an LLM call, not a dedicated sentiment API or a local lexicon

Considered three real options: a dedicated sentiment-analysis service (AWS Comprehend-style), a local
lexicon/rule-based classifier (VADER-style), or an LLM prompt via the OpenAI dependency this project already
has for embeddings. Chosen: the LLM. It's the only option that naturally produces the one-sentence rationale
`CONTEXT.md` already commits to — a plain classifier returns a label and a confidence score, not prose. A
lexicon-based classifier is also known to do badly on financial headlines specifically ("shares plunge on
strong demand" reads as negative to a generic lexicon, positive in financial context), and can't generate
coherent rationale either. Reusing OpenAI also means sentiment inherits the exact `ok`/`skipped`/`error`
degradation shape grouping already has, which `NOTES.md` had already flagged as reusable.

## Model and cost — verified live, expect this to drift

Checked directly against OpenAI's real pricing page (not memory) on the day of this discussion:

| model | input / 1M tokens | output / 1M tokens |
|---|---|---|
| **gpt-5-nano** | $0.05 | $0.40 |
| gpt-5.6-luna | $0.20 | $1.20 |
| gpt-5.6-terra | $2.00 | $12.00 |
| gpt-5.6-sol | $4.00 | $20.00 |

`gpt-5-nano` was the cheapest of everything checked, despite `gpt-5.6-luna` being marketed as its
generation's "most cost-efficient" tier — a genuinely counter-intuitive result that only turned up because it
was checked directly rather than assumed. **Re-verify this again immediately before implementation** — it
visibly moved even within this one conversation (a first, more generic pricing-page fetch missed the whole
5.6 family entirely).

At `gpt-5-nano` pricing, a headline+summary sentiment call costs roughly **$0.0000285**, unbatched — about
**$0.29 per 10,000 headlines**. A capped filing (see below) costs roughly 4-5x that per item, still trivial in
absolute terms. Cost is not the constraint this feature needs to optimize for at this project's real scale.

## Standard (synchronous) API, fired concurrently — not the Batch API

Considered OpenAI's Batch API (submit up to 50,000 requests in one file, 50% discount, its own higher
rate-limit pool) against the standard API called concurrently (the same `asyncio.gather` pattern spec 0001
already uses for provider fetches). Batch API's only guarantee is **completion within 24 hours** — often
faster in practice, never guaranteed. That's incompatible with wanting sentiment results within roughly a
minute. Verified live against the real OpenAI API: a single call took 1.8-3.4s; 20 concurrent calls completed
in **6.64s wall-clock**, not 20x a single call's time. Given cost is already negligible without the Batch
discount, there's no reason to trade away a latency guarantee for a savings that doesn't matter here.

### Revised during lesson 26's own live verification: unbounded concurrency isn't the same as 20 concurrent calls

The 20-concurrent-call test above was a small, deliberately safe sample — it was never actually the same
shape as real production volume, and that gap surfaced for real once lesson 26 ran against a real ticker.
A real MSFT search's 7-day window held **239 headlines**. Firing all 239 through one unbounded
`asyncio.gather` (no concurrency limit at all) made every single one time out together — not a clean
"first 100 succeed, the rest queue," a genuine cascade: httpx's default client caps at 100 connections, and
that much real simultaneous load against OpenAI's own rate limiting backed up the connection pool faster
than requests could drain, pushing the queued remainder past the 10s per-request timeout as a group.

**Fixed with `asyncio.Semaphore(20)`**, bounding true concurrency to the exact figure already verified safe,
regardless of total batch size. Re-verified against the same real 239-headline batch: 238/239 succeeded on
the first pass, 1 genuine transient failure — and the already-designed retry path (a second `/api/search`
call) resolved it, 239/239 on the next attempt. The lesson here isn't "concurrency doesn't work" — it's that
a small-scale test validates the *pattern*, not the *scale*, and real volume needs to be checked directly,
not assumed to extrapolate linearly from a sample an order of magnitude smaller.

## Job architecture: a separate background job, full-response polling — not WebSockets, not a status-then-fetch split

Sentiment runs as its own job, decoupled from the synchronous fetch/grouping job — a search's results render
immediately, sentiment fills in after. Three ways the frontend could learn sentiment is ready were considered:

- **WebSockets** — rejected. The real complexity isn't the websocket route itself (FastAPI supports that
  natively) — it's that sentiment finishes inside `worker`, but the open connection would live on `api`, two
  separate processes with nothing bridging them today. Making this work needs a new route, a Redis Pub/Sub
  bridge (a new pattern, even though Redis itself is already shared infra), matching an incoming message to
  the right open connection, frontend reconnect/merge logic, and a new testing category this suite has never
  exercised. Roughly 4-5 genuinely new pieces, not a small delta.
- **A lightweight "is it done" status endpoint, then a separate full-data fetch** — rejected. Cheaper per poll
  tick, but introduces two sources of truth that have to agree with each other — the same *class* of problem
  this project already hit for real with Milvus (an insert not immediately visible to the very next search,
  fixed in ADR 0011 via `consistency_level="Strong"`). Also not obviously worth it: a typical search returns
  tens to a couple hundred headlines, for one person running this locally — the "wasted" cost of a full
  re-fetch is the same kind of real-scale non-issue `COUNT(*)` and even full-article LLM cost turned out to be
  once actually measured.
- **Poll the existing full `/api/search`-shaped response repeatedly** (chosen) — reuses what already exists
  and is already tested (the same thing the manual Refresh button already calls). Every poll is one
  consistent, complete snapshot; the frontend renders per-headline conditionally and stops polling once
  nothing's pending (or a max-time cutoff, so a silently-failed job doesn't poll forever).

### Revised during lesson 26's own planning: polling needs its own endpoint, not literally the same one

"Poll the existing full `/api/search`-shaped response" turned out to gloss over something real: `/api/search`
unconditionally enqueues *and awaits* `fetch_headlines_job` on every call, with no way to skip it. Taken
literally, polling the same endpoint would re-trigger a full EDGAR/Finnhub/embeddings/grouping pass on every
poll tick — not just re-check sentiment. Found only once lesson 26 had to actually implement the trigger, not
during the original design discussion.

**Decision: `GET /api/search/status?ticker=X`, a new, read-only endpoint** — no `fetch_headlines_job`
enqueue at all, just current Postgres state. Shares the query + `build_daily_view` logic `/api/search` already
has via an extracted helper, not a duplicated implementation.

A second real consequence, also found at the same time: `/api/search`'s `status`/`providers`/`grouping`
fields all come from the fetch job's own return value — never persisted anywhere, only returned once per job
run. The new endpoint has nothing to report for those three fields, so its response is a genuinely smaller
shape: `{"sentiment": ..., "days": [...]}`. The frontend's poll loop therefore has to **merge** — update
`sentiment` and `days` from each poll response, leave `status`/`providers`/`grouping` exactly as they were
from the last real `/api/search` call (the initial load or a manual Refresh) — not replace its whole state
with each poll. This is a real behavior difference from "poll the same response shape," worth carrying into
lesson 29's own frontend planning, not assumed to be a drop-in.

### The page-level sentiment status has a real fourth state: `processing`

`grouping`'s status is `ok`/`skipped`/`error` (plus frontend-only `unknown`) because it's computed and
returned within the same request that ran it — there's no "still working on it" state to represent, it's
always already finished by the time anything reads it. Sentiment is different: since the job is fire-and-
forget from `/api/search`'s perspective, there's a real, observable window where work is genuinely still in
progress. Derived fresh on every request (both `/api/search` and the new status endpoint) from the same
headline rows already being queried for the response body — no new persisted state:

1. **`skipped`** — `not settings.openai_api_key` (nothing will ever run).
2. **`error`** — else, if any Headline in this response currently has `sentiment_status == "error"`.
3. **`processing`** — else, if any Headline currently has `sentiment_status IS NULL` (still pending).
4. **`ok`** — else (every Headline has resolved to a real score).

Checked in this priority order — an error surfaces even while other Headlines are still pending, rather than
being masked by `processing`.

## Storage: nullable columns on `headlines`, not a new table

`Story` got its own table (ADR 0009) specifically because it's a genuine 1-to-many grouping concept — many
Headlines can share one Story. Sentiment is 1-to-1 per Headline: every Headline has at most one sentiment
result, never shared. That's a much weaker case for a separate table, and `CONTEXT.md` already frames
sentiment as part of the `Headline` entity itself, the same way `outlet`/`summary`/`raw_content` already live
directly on `headlines` as nullable, filled-in-later fields. Decision: new nullable columns on `headlines`
(score, derived enum, gloss, rationale, status) rather than a `headline_sentiments` table.

Note directly relevant to ADR 0009: that ADR explicitly speculated `stories` might eventually need "a likely
future sentiment-analysis spec's need to store an aggregate sentiment score per Story" — see the Story
aggregate section below, where that speculation turns out to be exactly right, just via a different mechanism
(a derived, incrementally-updated average) than ADR 0009 could have anticipated.

### Why a `sentiment_status` column, specifically

`grouping`'s own `ok`/`skipped`/`error` status (spec 0002/ADR 0012) is never persisted — it's computed fresh
and returned within the same request that ran grouping, then discarded, because grouping is synchronous with
the fetch job. Sentiment can't do that: it runs in a background job, and whatever eventually reads the result
(a browser poll) is a *different, later* request than whatever triggered the job. A bare `NULL` can't
distinguish "still pending" from "skipped, not resolving this run" from "errored, not resolving this run" —
without a persisted status, the frontend either polls forever for headlines that won't resolve this run, or
needs an arbitrary timeout as a substitute for actually knowing what happened. The column is what lets the
frontend *know* when to stop polling instead of guessing — and it does double duty as the signal the job
itself uses to know which headlines are still worth retrying (see Retry eligibility, below).

### Retry eligibility: only a real score is terminal, not `skipped` or `error`

Originally modeled `skipped`/`error` the same way `check_milvus`'s `not_initialized`/`error` states work —
a settled outcome for that attempt. Reconsidered: unlike a Milvus health check (which just reports the
current instant's state, nothing to retry), a Headline's sentiment is worth actually getting right
eventually. A `skipped` Headline (no `OPENAI_API_KEY` configured at the time) should get a real score once
the key *is* configured; an `error`ed one (a transient API failure) should get a real score if a later
attempt just succeeds. Generalization: **only `ok` (a real score) is permanent.** `skipped` and `error` are
both eligible for a future retry — the same reasoning applies to both, not just literal failures.

This changes the job's own selection query from "headlines with `sentiment_status IS NULL`" to "headlines
without a real score yet" (`sentiment_status IS NULL OR sentiment_status IN ('skipped', 'error')`) — but
scoped to whatever headlines one backend request's own results already include, never a dedicated sweep of
the whole table (see the Non-goal in spec 0005: no backfill job). A previously skipped/errored Headline only
actually gets retried if a later request happens to pull it up again (e.g. a Refresh, or re-searching the
same ticker) — which is also exactly why the Story aggregate has to exclude non-`ok` members rather than
treat them as zero: a phantom value would need "correcting" later when a retry succeeds, which is exactly
the kind of redundant, drift-prone state this project avoids elsewhere (ADR 0009).

## Filing content extraction: revised in place — a two-tier strategy, not three (lesson 25)

**This section originally proposed a three-tier strategy, including structural (anchor-based) extraction as
tier 1. That tier was dropped during lesson 25's own planning, before ever being built, once a broader
sample showed it unreliable. This section is revised in place — same precedent as ADR 0009/0011's own
revisions — rather than left describing a design that was never actually shipped.**

### What the original three-filer sample found, and why it wasn't enough

The original plan (blind head-truncation with a size cap) was first reconsidered after checking whether SEC
filing HTML has enough real structure to extract just the relevant section (Item 7, Management's Discussion
and Analysis — the most genuinely sentiment-bearing part of a 10-K/10-Q, as opposed to Item 1A's largely
boilerplate Risk Factors). Checked live against three real, distinct filers:

| filer | anchor-based TOC? | Item 7 (MD&A) extractable via anchor? | real size |
|---|---|---|---|
| Apple (10-K) | Yes, opaque anchor ids | Yes, by matching the TOC's visible label text | ~4,500 tokens |
| Microsoft (10-K) | Yes, human-readable anchor ids | Yes, by matching a substring of the anchor id | ~12,000 tokens |
| Friedman Industries (10-K, small-cap) | No anchors at all | No — MD&A is "incorporated by reference" from a separate exhibit, not present in this document | whole document only ~7,750 tokens |

The conclusion drawn at the time — "match on the anchor id, not the visible label text" — was a real
methodology bug in its own right, caught too late: it was generalized from fixing *only* the Microsoft case,
without rechecking it against Apple. Apple's anchor ids are opaque (`i719388195b384d85a4e238ad88eba90a_94`,
no "item_7" substring anywhere) — an id-only matching strategy would have silently broken the very first
filer this whole investigation started with. **Neither heuristic alone is universal; Apple needs label-text
matching, Microsoft needs id-substring matching.**

### The broader sample that killed tier 1

Combining both heuristics and testing against five more real filers (spanning micro-cap to mega-cap:
Western Digital, Richardson Electronics, George Risk Industries, Standex International, Applied Industrial
Technologies) found a *third*, more serious failure mode: **Western Digital's TOC links wrap only the page
number** ("4", "10", "24"), not the item label at all — the label and the link aren't co-located in the
markup, at any level a regex can reasonably reach. This isn't a matching-heuristic gap, it's a structural
one; fixing it would need a real DOM-aware parser (`lxml`/`BeautifulSoup`) walking parent/sibling table
relationships — a genuine new dependency, not a small tweak.

Only 2 of the 5 broader-sample filers matched via either combined heuristic. **Decision: drop structural
(anchor-based) extraction entirely.** Not reliable enough to build on, and the DOM-parser fix is out of
scope for what this lesson needs.

### What replaced it: plain-text heading search, validated across 12 real filers

A pure text-search approach — no anchors, no TOC navigation at all — turned out to work far better once the
matching pattern was made specific enough. The first attempt (a bare `"Item 7."` heading search, taking the
*last* match) produced garbage on two filers (Microsoft, Richardson Electronics) — both came back as ~24
tokens, because the pattern matched a stray, unrelated mention of "Item 7" rather than the real heading. Same
root cause the anchor-label matching had: not specific enough. Fixed by requiring the heading's real title to
follow ("Item 7." must be followed by "Management"), which is effectively standardized by the SEC's own form
requirements across every filer.

**A second instance of the identical bug, caught during actual implementation (lesson 25), not planning**:
the same problem recurred one level over. The *next*-heading search (used to find where the MD&A section
ends) used a bare `"Item 7A"` / `"Item 8"` pattern — and Apple's own real MD&A opening sentence contains an
inline cross-reference ("...accompanying notes included in Part II, **Item 8** of this Form 10-K...") that
matched as if it were the real section boundary, cutting the extracted section to 236 characters instead of
~18,000. Fixed the same way: require Item 7A's/8's own real, SEC-standardized titles ("Quantitative"/
"Financial") to follow, not just the bare item number.

Final design, validated end-to-end against 12 real, diverse filers (the original 3, plus Western Digital,
Richardson Electronics, George Risk Industries, Standex International, Applied Industrial Technologies,
Chase General, US Global Investors, and Biomerica) — a two-step process, no special-casing needed per filing
type:

1. **Heading search** — find `Item\s*7\.?\s*(?:Management|MANAGEMENT)` (period optional; George Risk
   Industries omits it). Take the *last* match, skipping the table of contents' own earlier listing. Extract
   through the next real heading (`Item\s*7A\.?\s*Quantitative` or `Item\s*8\.?\s*Financial`), or to the
   content cap if no next heading is found.
2. **Reference-check, then blind truncation** — if the extracted section's first ~400 characters contain
   `incorporated (herein )?by reference` (Friedman Industries' real case), or if no Item 7 heading was found
   at all (the common case for 8-K/S-1/DEF 14A, which don't use this numbering scheme), fall back to
   truncating the whole document from the start, up to the content cap.

Validated in both directions, not just on the case it was built for: of the 12 real filers, only Friedman
Industries triggers the reference-check (a true positive), and it correctly stays silent on the other 11,
all of whom have real, substantive MD&A content directly in the document (a check that only gets tested
against its target case, never against real negatives, hasn't actually been shown safe to rely on).

## Content-size limits — character-based, not a real tokenizer

A single uniform cap doesn't fit both content types: news headline+summary content is normally tens to ~100
tokens, so a cap sized for filings would never actually trigger for news at all. Two separate limits,
expressed as **character counts** (chars/4 ≈ tokens, the same rough approximation used throughout this
document's own token estimates) rather than pulling in a real tokenizer library just for an approximate
safety net:

- **Filings: `FILING_CONTENT_CAP_CHARS = 80,000`** (≈20,000 tokens) — comfortably above every real MD&A
  section measured across 12 real filers (~4,500-12,000 tokens), so the common case is never at risk of
  hitting it; still meaningfully bounds the fallback-truncation worst case far below a full 100k-token 10-K.
- **News: ≈2,000 characters** (≈500 tokens) — real headline+summary content runs roughly 55-135 tokens; this
  is generous enough to never clip anything real, while still functioning as an actual safety net (not a
  decoration) against a genuine anomaly like a malformed provider field. Not yet implemented anywhere
  (lesson 25 only builds the filing-content path) — lesson 26's job wiring is where this gets applied to
  news input.

Whatever content is selected is subject to its category's cap; truncation gets logged (`get_filing_content`,
lesson 25) — evidence for recalibrating these numbers later, the same empirical-recalibration discipline ADR
0011's similarity threshold already established. Both numbers are explicitly working values — re-confirm
against a larger sample before treating either as final.

## Score → enum derivation, and the Story aggregate

The model's real output is a 0-100 score (0 = most negative, 100 = most positive). The
`positive`/`neutral`/`negative` enum `CONTEXT.md` fixes is *derived* from the score by one consistent
threshold rule — never asked of the model independently — so the enum and score can never disagree with each
other. (Exact threshold cutoffs are not yet chosen — analogous to `story_similarity_threshold`, this is a
value to tune empirically later, not to guess now.)

A Story with more than one member gets an aggregate score: the average of its members' own scores, with its
own enum derived by the identical threshold rule. This aggregate is never independently computed by the
model — purely a function of already-computed member scores, and per spec 0005's own Non-goals, never
recomputed as a separate model call.

**Computation: an incrementally-updated running average, stored on `stories`** — not a live `AVG(...)` query
recomputed on every read (which is what ADR 0009's own precedent, deriving Story's primary via query rather
than storing it, would suggest by analogy). Chosen instead because it's the option requiring the least new
code: the standard cumulative-moving-average update,

```
new_average = old_average + (new_score - old_average) / new_count
```

is O(1) per new member rather than re-scanning every member on every read. This requires storing both the
running average and a member count on `stories` — two new columns, and exactly the thing ADR 0009 speculated
`stories` might eventually need ("a likely future sentiment-analysis spec's need to store an aggregate
sentiment score per Story") when it kept that table deliberately minimal. Real edge case: the *first* member
to actually reach `ok` has no prior average to update from — that update has to set `average = score,
count = 1` directly rather than applying the general formula.

Only a member reaching `ok` ever folds into this running average — `skipped`/`error` members are never
counted, not even as a placeholder value, since (per Retry eligibility, above) they might still succeed on
a later run, and a stored average can't "un-count" a phantom contribution once a real value needs to replace
it. If a Story's members are all still `skipped`/`error`, the count stays 0 and there's no real average to
show yet.

**The aggregate is allowed to visibly update more than once** as different members' sentiment resolves at
different times — a deliberate, explicit exception to individual Headlines' "sentiment is permanent, set
once" rule. This was the natural, no-extra-code consequence of the incremental-update approach (each member's
resolution just folds into the running average whenever it happens) rather than a separately engineered
"wait for all members" behavior, which would have required tracking readiness across all of a Story's members
before showing anything.

## UI shape

- Sentiment pill beneath the existing category pill on `HeadlineCard`, colored by the enum, showing gloss and
  score together ("bullish · 82"). Rationale as small text beneath the pill. Greyed-out/empty while pending.
- A Story with more than one member (the same condition already gating the "+N more sources" disclosure)
  nests its existing display — primary card plus disclosure, unchanged — inside a visually distinct, larger
  outer card carrying its own "Story" pill and its own aggregate pill (same color/score convention). A Story
  of one shows none of this.
- The primary Headline inside that outer card gets zero special treatment — same component, same pill, same
  pending behavior as a standalone Headline. The outer card's aggregate pill is additional, not a replacement.

## Worker concurrency: one worker process is enough

Considered whether creating both the fetch job and a new sentiment job means needing more than one worker
container. Checked directly: ARQ's default `max_jobs` is **10**, and this project's `WorkerSettings`
(`worker.py`) doesn't override it — a single worker process already runs up to 10 jobs *concurrently*,
interleaved on the event loop, which is exactly what async/await is for. Every job this system runs is
I/O-bound (HTTP calls to OpenAI/SEC/Finnhub/Milvus), not CPU-bound — multiple processes mainly help with
CPU-bound work or true horizontal scaling across machines, neither of which applies yet. No second worker is
needed for this reason; a different justification (physical isolation, real multi-user scaling) could revisit
this later, but "jobs are being created concurrently" alone doesn't require it.
