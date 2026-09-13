# Lesson 14 plan — Today/Recent, category badges, and the Refresh button (arc-2 capstone)

Scope: `NOTES.md`'s lesson 14, the last lesson of arc 2. Re-read `docs/specs/0001-first-feature.md` in full
against the current actual frontend code before planning — see the completeness checklist below. Every
remaining gap is frontend-only; the backend (`providers.py`, `search.py`, `models.py`) was re-confirmed
complete, nothing there changes in this lesson.

## Spec 0001 completeness checklist

| Requirement | Status before this lesson | This lesson |
|---|---|---|
| Two lists by recency, Today/Recent, mutually exclusive | ❌ `SearchPage.tsx` concatenates both into one list | Builds it |
| Category badge (News/Filing) | ❌ plain text in `HeadlineList.tsx` | Builds it |
| Manual Refresh button | ❌ doesn't exist | Builds it |
| Status indicator, all three states surfaced | ⚠️ raw enum string shown (`"status: partial_failure"`) | Real message + color per state |
| Empty state shown plainly, including "empty Today is normal" | ⚠️ one combined empty message can't represent this distinction | Per-section empty messages |
| Everything else (concurrent fetch, filing allowlist, dedup, past-week window, ARQ job/timeout, Eastern-time split, CIK caching, no sentiment) | ✅ backend, done (lessons 6–10) | Unchanged |

**Constraint, not just an assumption**: the frontend must keep trusting `results.today`/`results.recent` exactly
as returned — no client-side re-derivation of the split using browser-local time. That guarantee was earned
with real DST tests in lesson 10; nothing here should risk it.

## Decisions confirmed with the user (2026-09-13)

1. **`CategoryBadge` and `SearchStatus` are extracted as their own components**, not inline — same reasoning
   `StatusTile.tsx` was extracted from `StatusPage`: a small enum-to-(color, label) mapping worth testing in
   isolation, not reuse-driven (each is used in exactly one place, same as `StatusTile` was at first).
2. **`success` gets a visible status message too**, not just the two failure states — "better to know that the
   latest news has indeed been fetched," per the user. Copy and colors, all confirmed:
   - `success` → emerald (matches `StatusTile`'s `ok`) → "All sources responded."
   - `partial_failure` → amber → "Some results may be missing — one source didn't respond."
   - `complete_failure` → red → "Couldn't fetch new results right now — showing previously saved data."
3. **Badge colors confirmed**: blue for News, purple for Filing — distinct from the status colors above so the
   two visual systems don't blur together.

## What gets built

**1. `frontend/src/components/CategoryBadge.tsx`** — `{ category: "news" | "filing" }` → a small colored
`<span>`, blue/"News" or purple/"Filing".

**2. `frontend/src/components/SearchStatus.tsx`** — `{ status: "success" | "partial_failure" | "complete_failure" }`
→ colored dot (or text) + the message table above.

**3. `frontend/src/components/HeadlineList.tsx`** — swap the plain-text category for `<CategoryBadge>`; replace
the hardcoded empty-state string with an `emptyMessage: string` prop, so Today and Recent can each show their
own contextually-correct empty text.

**4. `frontend/src/pages/SearchPage.tsx`**:
- Remove the combined-list line entirely (`[...results.today, ...results.recent]`) — replaced with two
  sections, each its own `<HeadlineList>`:
  ```tsx
  <section>
    <h2>Today</h2>
    <HeadlineList headlines={results.today} emptyMessage="No headlines today." />
  </section>
  <section>
    <h2>Recent</h2>
    <HeadlineList headlines={results.recent} emptyMessage="No other headlines in the past week." />
  </section>
  ```
- Replace the raw `{results.ticker} — status: {results.status}` line with `<SearchStatus status={results.status} />`.
- Add a Refresh button calling `runSearch(urlTicker)` directly — the same function the URL-driven-load effect
  already uses, bypassing `setSearchParams` entirely (submitting an unchanged ticker doesn't change the URL,
  which is exactly why this needs its own trigger — named explicitly in lesson 13's own content). Disabled
  while `loading`; shown only once `urlTicker` is truthy (no point refreshing before any search has happened).

## Verification

1. `CategoryBadge` and `SearchStatus`, each verified in isolation before being wired in anywhere.
2. `HeadlineList` wired to `CategoryBadge` + `emptyMessage` — verify existing rendering still looks right with
   real data.
3. `SearchPage`'s two-section split — verify live: a real ticker's Today and Recent entries actually land in
   the correct section, never both, matching what lesson 9's `curl` calls and lesson 10's tests already proved
   about the backend's own split.
4. **The core spec guarantee, proven, not assumed**: find or construct a case where Today is empty but Recent
   has entries, confirm Today's section reads as a plain, calm "no headlines today," not broken or stuck.
5. `SearchStatus` wired in — verify all three states live if feasible (success is trivial; partial/complete
   failure may need a deliberate provider outage or a lowered `job_timeout_seconds`, same technique lesson 9
   used).
6. Refresh — press it, confirm a real re-fetch happens (e.g., watch `fetched_at` change on a headline, or watch
   the network request fire again).
7. Full pass: `npm run test`, `npm run typecheck`, `npm run build`, then live via `docker compose up --build`.

## Open items

None outstanding — all three resolved with the user (see Decisions above).
