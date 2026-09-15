# Near-duplicate headlines are grouped into a Story, matched by embedding similarity scoped to one day

Spec 0001's dedup is exact-URL-only — two providers covering the same real event under different URLs show up
as separate, redundant entries (verified live against Finnhub's aggregator feed). Coverage volume is also a
real signal a flat list can't represent: a story covered by three independent outlets likely matters more than
one covered by none, and there's no way to read a second source's take on the same story without it appearing
as a separate, unconnected entry.

Decision: near-duplicate headlines are **grouped** into a **Story** (see `CONTEXT.md`), not omitted — the
attention/coverage signal and the ability to read multiple sources were both explicit requirements, not just
"fewer duplicates." Matching is embedding-similarity-based (Milvus; see ADR 0007/0008 for the specific
technology), **scoped to the same calendar day and the same ticker only**, and **threshold-based**: a new
headline is compared only against the primary headline of each existing same-day Story, never against every
member of every Story.

## Considered options

- **Omit near-duplicates entirely** (keep one, drop the rest): simplest, but throws away the coverage-count
  and multi-source-reading value that was the actual reason to build this at all.
- **Group with no day-scoping**: catches more real near-duplicates, but risks a real false-positive class —
  recurring, structurally similar report language (e.g. sequential quarterly earnings headlines) would be
  textually very similar across different reporting periods months apart, and could incorrectly merge into one
  Story without a day boundary preventing the comparison from ever happening.
- **Group, day-scoped, formal clustering** (e.g. agglomerative clustering over all of a day's headlines
  whenever anything changes): more "globally correct" in theory, but a real algorithmic lift, and awkward to
  run incrementally — headlines arrive one search/Refresh at a time throughout a trading day, not as one batch.
- **Group, day-scoped, threshold-matching against each existing Story's primary** (chosen): simplest of the
  grouping options, naturally incremental, matches how headlines actually arrive.

## Consequences

- A story spanning multiple days (breaking news developing over 48 hours) renders as separate per-day Stories,
  not one continuous thread — a deliberate simplification, not an oversight.
- Two headlines about the same recurring-report topic from *different* days never group, specifically because
  matching never crosses a day boundary — enforced structurally, not by a smarter similarity check.
- Matching only ever compares a new headline against a Story's primary, never every member of every existing
  Story — bounds the comparison cost, though it doesn't fully eliminate clustering-correctness subtlety within
  a single day (several genuinely similar headlines on the same day still need real matching logic, not just a
  pairwise check).
- Grouping never spans two different tickers, even for a genuinely related cross-company event — matching is
  scoped per-ticker the same way search itself already is.
