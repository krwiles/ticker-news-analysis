# Headline Sentiment Analysis

This is the spec for computing and showing sentiment on Headlines — a feature spec 0001 explicitly deferred
("no sentiment analysis... a separate concern, own spec once this ships") and spec 0002 deliberately did not
claim the `0002` slot for. `CONTEXT.md`'s `Headline` entry already anticipates the shape of this data (a
`positive`/`neutral`/`negative` enum, plus a one-word gloss and a one-sentence rationale — extended during
this spec's own discussion to be derived from an underlying 0-100 score, and to give Stories their own
derived aggregate) — this spec decides the feature's behavior, not how it's built; how it's computed is a
plan/ADR concern, not described here. This is a first draft; one open question below is marked for the next
grilling round, not yet decided.

## One-line summary

Each Headline gets a computed sentiment (a 0-100 score, a `positive`/`neutral`/`negative` enum derived from
it, a one-word gloss, a one-sentence rationale), shown in the UI; a Story with more than one member also
shows an aggregate sentiment, averaged from its members' own scores. Both degrade gracefully the same way
story grouping already does when its dependency isn't configured or is temporarily failing.

## Problem / motivation

Scanning a day's headlines today means reading each one in full to judge whether it's good or bad news for the
ticker. A per-headline sentiment signal lets a user triage at a glance — which headlines are worth reading
closely, without reading everything closely first.

## Goals

- Every Headline gets a computed sentiment **score**: a number from 0 (most negative) to 100 (most positive).
  The `positive`/`neutral`/`negative` enum `CONTEXT.md` already fixed is *derived* from this score by a single
  consistent rule, not computed independently — so the enum and the score can never disagree with each other.
- Alongside the score: a one-word gloss (what *kind* of positive/neutral/negative this is — see `CONTEXT.md`)
  and a one-sentence rationale for *why* — both already anticipated by `CONTEXT.md`'s `Headline` entry.
- A Story with more than one member also shows an aggregate sentiment: the average of its members' own
  scores, with its enum derived from that average using the exact same rule a Headline's enum uses. This
  aggregate is never independently computed by the model — it's purely a function of already-computed member
  scores. A Story with only one member shows no such aggregate.
- Sentiment computation reports its own `ok`/`skipped`/`error` status, the same pattern grouping already uses
  (spec 0002/ADR 0012) — `NOTES.md` already flags this as a signal to reuse, not re-derive.
- A search's results aren't blocked waiting on sentiment — headlines can appear before their sentiment is
  ready, and the page automatically catches up once it's computed, without the user having to take any
  action (no manual refresh needed, though one still works). Catch-up is incremental, not all-or-nothing:
  each Headline's sentiment appears as soon as it's individually computed, not held back until every
  Headline in the batch has one — a page with 200 pending Headlines should visibly fill in throughout, not
  sit unchanged until the 200th finishes.
- That catch-up is visually invisible except for the sentiment itself: nothing else on the page flashes,
  reflows, or reorders while it happens (see Outputs below for the exact visible shape).
- Headlines are computed newest-published first. A user checking in on a search cares most about the most
  recent news; resolving it first means the most relevant sentiment appears soonest, not last.
- A single failed attempt gets one automatic retry within the same job run before being marked `error` —
  real evidence (live worker logs) shows most failures are transient (a timeout under concurrent load, not
  a permanent rejection), so a lone failure isn't yet reason to give up. This is separate from, and in
  addition to, the existing retry-on-a-later-request behavior below.
- Once a Headline actually receives a real score, it's permanent — never re-evaluated later, mirroring
  Story's own once-set-never-touched rule. A skipped or errored attempt is different: it isn't a dead end —
  a later request that happens to touch the same Headline again is allowed to retry it. Only a real score,
  once it exists, is untouchable.
- A Story's *aggregate*, unlike an individual Headline's sentiment, is allowed to visibly update more than
  once — it naturally reflects however many members currently have a real score, and updates again as more
  do (including a member that only succeeds on a later retry), rather than waiting for every member to
  finish before showing anything. A member that's skipped or errored is excluded from the aggregate entirely
  until it actually has a real score — it never pulls the average toward a phantom value in the meantime.

## Inputs / data sources

- **News** headlines use their title and existing `summary` (already free from the provider, per spec 0001).
- **Filings** use the actual filed document's content, not just its title — a filing's title is constructed
  from its form type and description (per spec 0001), which carries no real signal on its own for judging
  sentiment.
- Whatever content is considered for a given Headline is subject to a size limit, so an unusually large
  input can't dominate processing. This limit is scaled to what's normal for that kind of content, not one
  uniform number: a news headline's title + `summary` is normally tiny, so its limit should be tight enough
  to actually catch a genuine anomaly (e.g. a malformed field); a filing's limit needs to be much larger,
  since real filings vary enormously in length on their own (confirmed live: a typical 8-K is small, a 10-K
  can be roughly 50-100x larger). Neither exact number is decided here (see Open questions).

## Open questions for the next grilling round

- **What are the actual content-size limits** mentioned above — one for news, a much larger one for filings?
  Their existence, and that they differ by content type, is decided; the exact numbers aren't.

## Non-goals

- No sentiment *independently computed* at the Story level — a Story's aggregate is always a derived average
  of its own members' already-computed scores, never a separate model call of its own.
- No fetching a news headline's full source article — title + `summary` is the input; considered and
  rejected as unnecessary for what this project needs.
- No re-evaluation of a Headline that already has a real score.
- No manual override or correction of a computed sentiment by a user.
- No sentiment trend or aggregate view (e.g. "AAPL sentiment over the past week").
- No dedicated backfill/reprocessing job that sweeps the whole history looking for missed or failed
  sentiment — the sentiment job only ever runs scoped to one backend request's own results, the same way the
  existing fetch job does. A previously skipped or errored Headline can still end up with a real sentiment
  later, but only as a side effect of a later request happening to include it again — never a deliberate bulk
  pass.

## Core entities & terminology

No new entity. `CONTEXT.md`'s existing `Headline` and `Story` entries already define the sentiment values,
score, gloss, rationale, and Story-level aggregate; this spec doesn't redefine them.

## Outputs / user-facing behavior

`HeadlineCard` splits into two even columns, each roughly half the card's width. The left column stacks the
category pill (left-aligned, above the title — no longer beside the sentiment card), the title, and its
outlet/date line. The right column is a single, visually distinct sentiment sub-card, holding the pill —
colored by the sentiment enum value, showing the one-word gloss and the numeric score together (e.g.
"bullish · 82" — not just the raw enum value, "positive") — and, once available, the one-sentence rationale
as small text beneath it inside the same sub-card. `summary`, when present, still spans the full card width,
below both columns.

The sub-card itself is always present, even while pending — only its contents change once resolved. While
pending, the pill inside it shows as an empty, greyed-out placeholder with no gloss or score yet, and no
rationale line is shown. Once computed, the pill updates in place to its real color, gloss, and score, and
the rationale text appears beneath it inside the same sub-card — no other part of the page flashes,
reflows, or reorders when this happens.

A page-level sentiment status sits alongside it, mirroring `GroupingStatus`'s existing dot+message shape —
grouping and sentiment are independent dependencies that can succeed or fail on their own, so they get their
own separate status lines rather than one merged signal. Sentiment's own status has one more real state than
grouping's: `skipped` (the dependency isn't configured, nothing will ever run), `error` (something has
failed), `processing` (still actively computing — at least one Headline is still pending), or `ok` (every
Headline currently in view has a real score, nothing left pending). `processing` reflects the fact that
sentiment, unlike grouping, doesn't finish within the same request that triggered it — there's a real,
observable "still working on it" state grouping never has.

**A Story with more than one member** — the same condition that already shows the "+N more sources"
disclosure (spec 0002) — nests its existing display (the primary Headline's card, plus that disclosure,
unchanged) inside a visually distinct, slightly larger outer card. That outer card shows its own "Story"
pill, plus its own aggregate-sentiment pill (colored and showing a score, same convention as an individual
pill), representing the Story as a whole. A Story with only one member shows none of this — it renders
exactly as a single Headline does today.

The primary Headline inside that outer card is not treated specially in any way — it's the same
`HeadlineCard`, with the same individual sentiment pill, same pending/resolved behavior, as any other
Headline. The outer card's aggregate pill is a separate, additional thing sitting above it, not a replacement
for the primary's own pill.

## Success criteria

- A genuinely positive headline (e.g. strong earnings beat) is classified `positive`; a genuinely negative one
  (e.g. a lawsuit, a miss) is classified `negative`; routine/administrative news is `neutral` — verified
  against real headlines, not assumed.
- The one-word gloss and one-sentence rationale are both visibly specific to the headline's actual content,
  not generic/interchangeable text — and the gloss is never just a restatement of the enum value itself
  (e.g. gloss = "positive" would fail this).
- A filing's computed sentiment reflects the substance of the actual filed document — not a generic result
  based only on its filing type.
- If the sentiment dependency isn't configured, or is configured but failing, headlines still display
  normally with sentiment absent/unknown — never a broken page.
- The page-level sentiment status accurately reflects reality at all times: `processing` while any Headline
  is still pending, `ok` once none are, `error` if any Headline has actually failed (even while others are
  still pending), `skipped` if the dependency was never configured at all.
- While sentiment is pending and the page is automatically catching up, nothing already on screen flashes,
  shifts position, or disappears — the only visible change, for any given headline, is its own greyed-out
  placeholder becoming its real sentiment.
- An unusually large filing doesn't cause a failure or stall processing — it's still analyzed.
- Once a Headline has a real score, it never changes, even if the same headline is somehow re-processed. A
  Headline that was only ever skipped or errored is not held to this — it can still receive a real score
  later, if a later request happens to include it again.
- Two headlines about the same real-world event (already grouped into one Story, per spec 0002) don't need to
  agree on sentiment — each Headline's sentiment is independent.
- A Headline's enum and score are always consistent with each other, and a Story's enum and aggregate score
  are always consistent with each other — both derived by the identical rule.
- A Story's displayed aggregate score always equals the true average of whichever members currently have a
  real score, verifiable against those members' own individual scores directly — a skipped or errored member
  never pulls that average toward a phantom value in the meantime.
- The primary Headline inside a Story's outer card renders identically — same pill, same pending behavior —
  to how it would render as a standalone Headline; being inside a Story changes nothing about it.
- A Story with only one member never shows the outer Story card, the "Story" pill, or an aggregate pill.

## Technical approach

See `docs/adr/0014-sentiment-analysis-technical-approach.md` — the mechanism, job architecture, storage
shape, and filing-extraction strategy, all decided during this spec's own grilling round, following this
project's usual pattern (see ADR 0006/0007 for the equivalent decisions grouping made). The exact
content-size limits and score-to-enum thresholds remain open numbers even there — flagged as working values,
not final.
