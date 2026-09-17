# The `story_primaries` Milvus collection: one vector per Story, cosine metric, empirically-tuned threshold

ADR 0006 decided matching is threshold-based, scoped to one ticker + one calendar day, comparing a new headline
only against each existing Story's primary. ADR 0009 decided Postgres never stores a primary reference — it's
derived via `ORDER BY published_at ASC LIMIT 1`. Neither ADR specified what Milvus should actually hold, what
metric to search with, or what threshold counts as a match. Lesson 19 is where those got decided, researched
and verified live rather than assumed.

Decision: one Milvus row per **Story**, not per Headline — the founding member's embedding only, permanent
once written, searched with the **cosine** metric, matched above a threshold of **0.75**.

## Considered options — collection shape

- **One row per Headline** (considered, rejected): would require a stored "is this the primary" marker to know
  which rows are even eligible comparison targets — exactly the redundant state ADR 0009 already rejected for
  Postgres. Filtering to primaries-only at search time would need that same marker duplicated into Milvus.
- **One row per Story, holding the founding member's vector** (chosen): matches ADR 0006's own rule directly —
  "compared only against the primary headline of each existing same-day Story." Collection size scales with
  Story count, not Headline count.

## "Primary" is two concepts, not one — and that's fine

Milvus's stored vector is a **matching-representative**: fixed the moment a Story is created (whichever
headline founds it, because nothing matched it at the time), never touched again. Postgres's derived primary
(ADR 0009) is a **display-primary**: live-computed as `ORDER BY published_at ASC LIMIT 1` over a Story's
*current* members, every time it's read.

These almost always name the same headline. They aren't guaranteed to. A headline arriving in a later run with
an earlier `published_at` than the Story's founding member would shift the *display*-primary without touching
the *matching*-representative — accepted as a rare, tolerable edge case, not solved here. This doesn't break
matching: every member of a Story matched into it *because* it was a near-duplicate of what was already there,
so the founding vector stays a valid semantic stand-in for the Story's topic regardless of which member
Postgres currently reports as earliest-published. The two systems never need to agree with each other.

## Metric: cosine, confirmed not assumed

Direct research (not memory): OpenAI's `text-embedding-3-small`/`-large` vectors are L2-normalized, so cosine
similarity and dot product rank identically for them. Cosine chosen over dot product for readability — the
score is directly interpretable as similarity, which matters more than the negligible compute difference at
this project's scale.

## Threshold: 0.75, empirically measured against real headline pairs

Not guessed. Real `text-embedding-3-small` embeddings measured for six pairs spanning what spec 0002's success
criteria care about:

| pair | should match? | cosine similarity |
|---|---|---|
| same event, different providers | yes | 0.882 |
| same event, very different wording | yes | 0.772 |
| different topics, same company | no | 0.433 |
| related but distinct events (borderline) | no | 0.679 |
| recurring-report language, different quarters | no (day-scoping handles this structurally) | 0.943 |
| completely unrelated | no | 0.484 |

The tightest real gap is 0.679 (should-not-match) to 0.772 (should-match). 0.75 sits inside that gap, biased
toward the "should match" side deliberately — spec 0002's own success criteria state a false merge
("textually-similar-but-genuinely-different headlines never incorrectly group") as the failure mode to avoid,
more explicitly than a missed grouping.

The **recurring-report pair scored highest of all (0.943)**, purely from structural phrasing similarity across
different quarters — this is direct empirical confirmation that ADR 0006's day-scoping requirement is
load-bearing, not theoretical: without it, no threshold could distinguish that pair from a genuine duplicate.

## Threshold re-examined against a larger, independent sample (post-lesson-22)

A real production split surfaced the question of whether 0.75 was still right: five headlines about Microsoft's
8% dividend increase (Sept 16) split into two Stories, because the two founding headlines scored 0.7247 —
just under the cutoff. Rather than tune against that one pair, a new, larger, independent experiment was run:
33 real headlines across four tickers (NVDA, AMZN, AAPL, GOOGL), forming 31 same-event pairs (verified by
reading title+summary, blind to any similarity score) across seven distinct real events, and 6 deliberately
*hard* different-event pairs — same company/topic, verifiably different specific news (e.g. "Micron stock
sank on sector pressure" vs "Micron rated Strong Buy on DRAM scarcity"; "Google Cloud x Deutsche Bank" vs
"Google x Accenture" — two distinct partnership announcements). The 0.75 value and every prior finding above
were deliberately not consulted while building the sample or assigning labels.

Sorted same-event scores: `0.563, 0.572, 0.606, 0.645, 0.651, 0.673, 0.701, 0.717, 0.720, 0.725, 0.731, 0.774,
0.776, 0.785, 0.786, 0.799, 0.803, 0.804, 0.813, 0.829, 0.830, 0.832, 0.840, 0.851, 0.857, 0.872, 0.873, 0.874,
0.887, 0.892, 0.907`. Sorted different-event scores: `0.405, 0.537, 0.599, 0.604, 0.716, 0.746`.

**Finding: the two distributions genuinely overlap.** 11 of 31 same-event pairs (35%) score below the highest
different-event pair (0.746) — no single global threshold can catch all 31 without also crossing into
different-event territory. This is a real property of comparing two headlines' embeddings at this granularity,
not a symptom of an uncalibrated number.

**Finding: 0.75 already sits in the best available zero-false-positive position.** There is a genuine gap in
this sample between 0.731 (the highest same-event score below the overlap) and 0.774 (the next one up) — and
the highest different-event score, 0.746, falls inside that exact gap. Any threshold in `(0.746, 0.774]`
produces the identical outcome: the same 20/31 same-event pairs correctly matched, 0/6 false positives. 0.75
is already inside that range.

**Finding: the MSFT split specifically cannot be fixed without a demonstrated new false positive.** Catching
the 0.7247 pair would require a threshold ≤ 0.7247, which also crosses 0.716 — pulling in the Google
Cloud/Deutsche Bank vs. Google/Accenture pair (0.746) as a real false merge of two different announcements.

Decision: **0.75 stands, re-confirmed rather than left untouched.** The MSFT split (and the other ~10 same-
event pairs in this sample scoring below the gap) is accepted as a real, now-quantified limitation of
comparing only against a Story's primary with one global threshold — not a miscalibration. A different fix
(comparing against more than a Story's primary) is the same formal-clustering option ADR 0006 already
considered and rejected for complexity; this finding doesn't reopen that trade-off, it just confirms the
current threshold is a reasonable point on it.

## Two real bugs found live, not caught until real data forced them

- **`insert()` isn't searchable until made visible, and `flush()` is the wrong fix for a sequential loop.** A
  synthetic two-headline test (same real event, different wording) failed to group on the first live run — the
  second headline's search ran before the first's insert was visible. The first fix, an explicit `flush()`
  after every insert, was *correct* but expensive: verified live against a 249-headline real fetch (MSFT), it
  took long enough to blow past `job_timeout_seconds`'s 10s budget. Replaced with `consistency_level="Strong"`
  on the search call instead — verified live to give the same read-your-own-writes guarantee (a same-process
  insert visible to the very next search, no explicit flush) in ~5ms instead of a full segment seal. The same
  249-headline fetch that previously didn't finish in 20s+ completed end-to-end in 3.86s after this fix.
- **The search result's primary-key field is named after the schema, not always `"id"`.** Assumed `hits[0][0]["id"]`
  based on a generic pymilvus doc example whose schema happened to use `"id"` as the primary key field name.
  This collection's primary key is `story_id` — verified live (a direct insert-then-search round trip, printing
  the raw result) that the field comes back as `story_id`, not `id`. Fixed before it shipped.

## Consequences

- `providers.py`'s `_match_or_create_story`/`_assign_stories` depend on this collection's exact field names
  (`story_id`, `ticker`, `day`, `embedding`) and the `consistency_level="Strong"` search parameter — both real,
  load-bearing details now, not just documentation here.
- `story_similarity_threshold` lives in `config.py`, not hardcoded, specifically so it can be revisited without
  a code change if real production data ever shows it's miscalibrated.
- The two-primary-concepts framing means a future reader must not assume Milvus's stored vector and Postgres's
  displayed primary are the same headline — they usually are, they aren't guaranteed to be, and matching
  correctness doesn't depend on them being so.
