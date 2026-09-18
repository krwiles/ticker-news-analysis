# Lesson 29 plan — Frontend: sentiment UI + polling

Scope per `NOTES.md`: `SearchPage` gains a poll loop (mirrors `StatusPage`'s existing pattern);
`HeadlineCard` gains the sentiment pill (gloss + score together, colored by enum, greyed-out while pending,
rationale as small text beneath); `Story` gains the nested outer card (its own "Story" pill + aggregate
pill) for multi-member Stories only. Capstone of Arc 5, same role lesson 22 played for Arc 4.

## Architectural decisions made during planning

1. **Merge, not replace, on every poll tick.** `/api/search/status` returns only `{sentiment, days}` — the
   poll must merge those two keys into existing `results` state via a functional `setResults`, never
   overwrite the whole object. The consequence ADR 0014 flagged during lesson 26's own planning, finally
   landing here.
2. **The poll effect is keyed on `[results?.ticker, results?.sentiment]`, not `[]`.** Unlike `StatusPage`
   (polls forever from mount), this effect should stop once sentiment resolves. Re-running the effect
   whenever `sentiment` changes gives that for free: the guard (`if (!results || results.sentiment !==
   "processing") return;`) only ever creates the interval while still processing, and cleanup tears down
   the old one on every status or ticker change — no manual stop flag needed.
3. **No immediate first tick, unlike `StatusPage`.** `results` here is always already fresh (it just came
   from `/api/search` or a prior poll), so firing again at t=0 would just re-fetch identical data.
4. **Reuse `POLL_INTERVAL_MS = 5000` from `StatusPage`'s precedent** — no evidence sentiment resolves
   meaningfully faster or slower than a health check.
5. **A new page-level `SentimentStatus` component**, same shape as `GroupingStatus` (ok/skipped/error, plus
   a new `processing` message — one dot, one line). Explains *why* sentiment is unresolved once, for the
   whole page, so per-item pills don't have to.
6. **`SentimentPill` collapses to two visual buckets, not four.** Resolved (`sentiment_enum` present) →
   gloss + score, colored positive/neutral/negative. Unresolved (enum null, whether that's not-yet-attempted,
   skipped, or error) → one grey "Pending" pill, shared by both the per-headline and per-Story call sites so
   their visual language can't drift apart.
7. **Rationale renders as small text beneath the card, only when present** — same conditional-render
   precedent `summary` already uses in `HeadlineCard`.
8. **Story-level chrome is gated on `other_members.length`, not on whether `sentiment_average` is
   present.** A single-member Story gets zero wrapping, even though the backend returns a real (if trivial)
   aggregate for it (lesson 28's own live verification) — matches `CONTEXT.md`'s "more than one member"
   definition of the aggregate.

## What gets built

- `search.ts`: `Headline`/`Story` gain their new sentiment fields; `SearchResponse` gains `sentiment`; new
  `SearchStatusResponse` type + `fetchSearchStatus()` for `GET /api/search/status`.
- New `SentimentPill.tsx` — shared component, resolved vs. pending rendering.
- New `SentimentStatus.tsx` — page-level status line, mirrors `GroupingStatus`.
- `HeadlineCard.tsx` — renders `SentimentPill` next to `CategoryBadge`, plus conditional rationale text.
- `Story.tsx` — member-count-gated outer wrapper with a "Story" label pill + aggregate `SentimentPill`
  (no `gloss` prop — Stories don't have one, so the pill falls back to `enum · rounded score`).
- `SearchPage.tsx` — the poll effect described above, plus rendering `SentimentStatus`.

## Tests

- `search.test.ts`: 3 new tests for `fetchSearchStatus`, mirroring `fetchSearch`'s own three exactly.
- `SentimentStatus.test.tsx` / `SentimentPill.test.tsx`: new, mirroring `GroupingStatus.test.tsx`'s shape.
- `HeadlineCard.test.tsx`, `Story.test.tsx`, `DaySection.test.tsx`: existing `headline()`/`story()` helpers
  extended with the new fields (defaulted to "not yet resolved"), plus new assertions for the pill/wrapper.
- `SearchPage.test.tsx`: new `describe("sentiment polling")` block — first frontend tests in this codebase
  exercising a timer-driven effect. Uses `vi.useFakeTimers({ shouldAdvanceTime: true })` (keeps RTL's own
  `waitFor` working via real-time auto-advance) plus `vi.advanceTimersByTimeAsync()` (correctly flushes the
  poll's own `await fetchSearchStatus(...)` between ticks) to fast-forward the interval instantly instead of
  waiting 5 real seconds per test.

## What actually happened during execution

Built exactly as planned. One test-writing snag, not a design snag: the first version of the "Story shows a
Pending aggregate pill" test left the Story's members with default (unresolved) sentiment, so the page had
*two* "Pending" pills — the aggregate's and the still-unresolved member's own — and `getByText("Pending")`
correctly failed on ambiguity. Fixed by giving both members a real resolved score in that test, so the only
remaining "Pending" pill is unambiguously the aggregate's own. 81/81 tests (22 new), zero regressions.
`tsc --noEmit` clean; `npm run build` clean (only pre-existing bundle-size warnings, unrelated).

No browser was driven directly (no browser-automation tool available in this environment) — verified
instead by: a clean production build, a clean type-check, the full test suite, and live data pulled from
the real running stack confirming the exact response shape the new frontend types assume:

- A real in-flight MSFT search returned `sentiment: "processing"` immediately after the fetch, then
  resolved to `"ok"` on a follow-up `/api/search/status` call seconds later — the exact transition the poll
  effect's stop condition is built to detect.
- A real 3-member MSFT Story: `sentiment_average: 80.666...`, `sentiment_enum: "positive"` — the same
  Story lesson 28 verified, now confirmed to render as `SentimentPill`'s `"positive · 81"` (rounded).
- `spec 0005`'s own Outputs section (written before this lesson was planned) already described this exact
  UI shape in detail — pill beneath the category badge, `"bullish · 82"` format, greyed-out pending state,
  Story outer card gated on member count — confirming the implementation didn't drift from what was speced.
