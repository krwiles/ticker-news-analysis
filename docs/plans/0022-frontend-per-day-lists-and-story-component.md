# Lesson 22 plan — Frontend: per-day lists + the Story component

Scope per `NOTES.md`: replace `SearchPage`'s Today/Recent sections with one section per day (lesson 21's
`days` shape), and a `Story` component rendering a primary headline plus an expandable list of other members.
Plan was discussed and agreed inline in conversation rather than written to a file before implementation;
recorded here after the fact, per this project's usual convention of a plan doc per lesson.

Two decisions made before any code:

1. Display the `grouping` status underneath the existing `SearchStatus` — a new `GroupingStatus` component,
   same dot+message shape, distinguishing `ok`/`skipped`/`error`/`unknown`. Fulfills ADR 0012's own
   forward-looking note that a future UI would want this signal.
2. Delete `HeadlineList` entirely rather than keep it as an unused wrapper — `Story` renders `other_members`
   directly via a newly-extracted `HeadlineCard`, leaving `HeadlineList` with no remaining call site.

## Architectural approach

Pure consumer of lesson 21's already-shipped `days`/`grouping` fields — no backend or API changes. New
components, each individually testable (mirrors this codebase's existing `CategoryBadge`/`SearchStatus`/
`StatusTile` precedent):

- `HeadlineCard` — one headline's full rendering (extracted from `HeadlineList`'s old markup), shared by a
  Story's primary and each of its `other_members` so the two never drift into different markup.
- `Story` — primary via `HeadlineCard`, plus (only when `other_members.length > 0`) a native `<details>`
  disclosure — no local state needed, the browser handles open/closed.
- `DaySection` — one day's heading (`"Today"` or a formatted date) and its Stories, or an empty message.
- `GroupingStatus` — same shape as `SearchStatus`, one new field.

## Files and components changed

- `frontend/src/search.ts` — `Story`/`DayGroup` types added; `SearchResponse.grouping` and `.days` replace
  `today`/`recent`.
- `frontend/src/components/HeadlineCard.tsx` (new) + test.
- `frontend/src/components/Story.tsx` (new) + test.
- `frontend/src/components/DaySection.tsx` (new) + test.
- `frontend/src/components/GroupingStatus.tsx` (new) + test.
- `frontend/src/components/HeadlineList.tsx` + `HeadlineList.test.tsx` — deleted.
- `frontend/src/pages/SearchPage.tsx` — rewired to render `days` and `GroupingStatus`.
- `frontend/src/pages/SearchPage.test.tsx`, `frontend/src/search.test.ts` — updated for the new shape.

## Database / API / backend changes

None — both already shipped in lesson 21.

## Existing tests / new tests required

Deleted `HeadlineList.test.tsx` (component removed). New: `HeadlineCard.test.tsx` (ports `HeadlineList`'s
per-headline assertions), `Story.test.tsx` (primary always renders; no disclosure for a singleton Story;
disclosure reveals members on click; pluralization), `DaySection.test.tsx` (Today heading vs. formatted date,
including the UTC-midnight regression case below; empty message; one Story per entry), `GroupingStatus.test.tsx`
(all four states, never the raw value). Rewrote `SearchPage.test.tsx`'s day-specific tests and every fixture
literal; trivial fixture update in `search.test.ts`.

## Risks and assumptions — resolved during this lesson

- **A real bug caught before shipping, not a design choice**: `day.date` is `"YYYY-MM-DD"` with no time
  component. `new Date("2026-09-16")` parses as UTC midnight; formatting that with `toLocaleDateString()`
  renders as the *previous calendar day* in any timezone west of UTC, Eastern included. Fixed in `DaySection`
  by parsing the string's components manually and using the local-time `Date` constructor
  (`new Date(year, month - 1, day)`), which never reinterprets across timezones. Covered by a dedicated
  regression test.
- **Browser verification gap, stated explicitly rather than assumed**: the `ui` container was rebuilt and
  confirmed serving cleanly (200 response, correct title, clean startup logs, no console/build errors visible
  in logs), but no browser-automation tool was available in this session to actually render and click through
  the page. `tsc --noEmit` is clean and 51/51 tests pass, which verifies logic and types, not visual
  correctness — a manual check in a real browser is recommended before treating this as fully verified,
  consistent with this project's own stated standard for UI changes.

## Incremental steps (as executed)

1. Update `search.ts` types.
2. Extract `HeadlineCard` from `HeadlineList`'s markup; delete `HeadlineList` + its test.
3. Build `Story.tsx` + test.
4. Build `DaySection.tsx` + test (catching the UTC-midnight date bug here).
5. Build `GroupingStatus.tsx` + test.
6. Rewire `SearchPage.tsx`; rewrite its test file and `search.test.ts`'s fixture.
7. Run the full frontend suite (51/51 passing) and `tsc --noEmit` (clean).
8. Rebuild and restart the `ui` container; confirm it serves without errors (browser click-through not
   performed — no tool available).
9. Update `NOTES.md` (also closing out lesson 23 as originally sketched — superseded, since this lesson wrote
   its own tests inline); write lesson content.
