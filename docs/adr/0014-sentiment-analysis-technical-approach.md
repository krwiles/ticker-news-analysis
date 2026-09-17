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

## Filing content extraction: a three-tier strategy, evidence-backed across three real filers

The original plan (blind head-truncation with a size cap) was reconsidered after checking whether SEC filing
HTML has enough real structure to extract just the relevant section (Item 7, Management's Discussion and
Analysis — the most genuinely sentiment-bearing part of a 10-K/10-Q, as opposed to Item 1A's largely
boilerplate Risk Factors). Checked live against three real, distinct filers:

| filer | anchor-based TOC? | Item 7 (MD&A) extractable via anchor? | real size |
|---|---|---|---|
| Apple (10-K) | Yes | Yes | ~4,500 tokens |
| Microsoft (10-K) | Yes (initially missed — see below) | Yes | ~12,000 tokens |
| Friedman Industries (10-K, small-cap) | No anchors at all | No — MD&A is "incorporated by reference" from a separate exhibit, not present in this document | whole document only ~7,750 tokens |

**A real methodology bug, corrected mid-investigation and worth recording**: the first Microsoft check
concluded "no anchor structure" by matching the TOC link's exact visible label text (`"Item 7."`). That
matched Apple's TOC (which uses the short label as link text) but missed Microsoft's (whose TOC link text is
the full section title, "Management's Discussion and Analysis..."). The anchor `id` itself
(`item_7_managements_discussion_analysis_f`) reliably encoded which item it was even when the visible label
didn't match a fixed string. **Any real implementation must match on the anchor id, not the visible label
text.**

**Friedman Industries revealed a third real failure mode** beyond "has anchors" / "no anchors": a filing can
have the `Item 7.` heading present in plain text, with the actual content **not in the document at all** —
smaller reporting companies commonly file a short 10-K wrapper that legally incorporates their real annual
report by reference from a separate exhibit in the same submission. Neither anchor-following nor a
heading-based text search would find real content here. The graceful part: because that primary document is
short precisely because the real content lives elsewhere, a blind-truncation fallback still produces a
reasonable (if less substantive) result rather than an error.

Decision: a three-tier fallback, each tier attempted only if the previous one fails to find anything:
1. **Structural extraction** — find the Item 7 anchor by matching the anchor `id` (not the link's visible
   label text), extract through the next item's anchor.
2. **Plain-text heading search** — if no matching anchor exists, search for the "Item 7"/"Item 7." heading
   directly and take content following it, up to the content cap.
3. **Blind head-truncation** — if neither finds real content (Friedman's case), truncate the whole document
   from the start, up to the content cap.

## Content-size limits — two different numbers, both working values pending broader validation

A single uniform cap doesn't fit both content types: news headline+summary content is normally tens to ~100
tokens, so a cap sized for filings would never actually trigger for news at all. Two separate limits:

- **Filings: ~20,000 tokens** — comfortably above every real MD&A section measured (Apple ~4,500, Microsoft
  ~12,000), so tier 1's typical output is never at risk of hitting it; still meaningfully bounds tier 2/3's
  worst case far below a full 100k-token 10-K.
- **News: ~500 tokens** — real headline+summary content runs roughly 55-135 tokens; 500 is generous enough to
  never clip anything real, while still functioning as an actual safety net (not a decoration) against a
  genuine anomaly like a malformed provider field.

Whatever content is selected (regardless of tier) is subject to its category's cap. Truncation, and any input
notably larger than typical even short of the cap, gets logged — evidence for recalibrating these numbers
later, the same empirical-recalibration discipline ADR 0011's similarity threshold already established. Both
numbers here are explicitly working values from a small real sample (one filing size distribution, one
headline/summary estimate) — re-confirm against a larger sample before treating either as final.

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
