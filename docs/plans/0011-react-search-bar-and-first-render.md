# Lesson 11 plan — React fundamentals: search bar + first-pass results rendering

Scope: `NOTES.md`'s lesson 11. Components, JSX, hooks (`useState`/`useEffect`) taught against the Angular→React
translation table (`NOTES.md`'s Working Translation Table), built against a real search bar and a first pass at
rendering `/api/search`'s results (lesson 9, tested lesson 10 — backend contract is finished and untouched by
this lesson). Not in scope: routing mechanics as a taught concept (lesson 13), Today/Recent split + styled
category badges + Refresh button (lesson 14, arc-2 capstone), frontend test tooling (lesson 12, inserted
specifically to hold that — see below).

Circling back to `docs/specs/0001-first-feature.md`: this lesson starts building toward it on the frontend for
the first time. Two deliberate simplifications keep it a small vertical slice rather than pulling lesson 14's
work forward — confirmed with the user rather than assumed:

- **One combined list, not Today/Recent.** The response already carries `today`/`recent` as separate arrays;
  grouping/heading them is lesson 14's job. This lesson concatenates them (`[...data.today, ...data.recent]`)
  into one flat rendered list.
- **Category shown as plain text, not a styled badge.** Spec 0001 calls for a "category badge" specifically;
  building the actual badge component is lesson 14's.

## Decisions confirmed with the user (2026-09-11)

1. Combined-list / plain-text-category scoping above — confirmed as-is.
2. **A real `/search` route is added now**, not deferred — `App.tsx` gets a second `<Route>` using the exact
   same pattern the existing `"/"` route already uses. No new React Router concepts are taught when this
   happens (no params, no loaders, no `<Link>`/`useNavigate`) — it's mechanically identical to the route
   that's already there, just duplicated. Lesson 13 is where routing itself becomes the actual subject,
   including explaining this route properly in retrospect.
3. **Frontend testing gets its own inserted lesson** (new lesson 12, `NOTES.md`), not folded into this one —
   mirrors how lessons 8 and 10 were inserted mid-arc once a real gap surfaced. Resolves ADR 0005's explicitly
   deferred tooling decision (Jest/Vitest + Testing Library) at exactly the point it said that decision should
   be made, without bloating this lesson's single tangible win.

## What gets built

**1. `frontend/src/search.ts`** — new API client, same shape as `health.ts`:
```typescript
export interface Headline {
  title: string;
  url: string;
  category: "news" | "filing";
  provider: string;
  outlet: string | null;
  summary: string | null;
  published_at: string;
}

export interface SearchResponse {
  ticker: string;
  status: "success" | "partial_failure" | "complete_failure";
  providers: Record<string, string>;
  today: Headline[];
  recent: Headline[];
}

export async function fetchSearch(ticker: string): Promise<SearchResponse> {
  const res = await fetch(`${API_BASE_URL}/api/search?ticker=${encodeURIComponent(ticker)}`);
  if (!res.ok) {
    throw new Error(`/api/search responded ${res.status}`);
  }
  return res.json();
}
```
Types mirror `search.py`'s `_headline_to_dict`/response shape by hand — same hand-sync trade-off `models.py`'s
own docstring already names for the dbmate/SQLAlchemy split, not a new problem.

**2. `frontend/src/components/SearchBar.tsx`** — controlled input (`useState`) + submit handler. The direct
`signal()`↔`useState()` teaching example from the translation table.

**3. `frontend/src/components/HeadlineList.tsx`** — presentational, takes `Headline[]`, renders title-as-link,
published date, category as plain text, outlet when present (`via {outlet}`), summary when present. Reuses
`StatusTile.tsx`'s existing Tailwind conventions rather than inventing new styling.

**4. `frontend/src/pages/SearchPage.tsx`** — owns `loading`/`error`/`results` state (mirrors `StatusPage.tsx`'s
existing error-handling shape), wires `SearchBar`'s submit to `fetchSearch`, renders `HeadlineList` or a
loading/error/empty state. **Fetch is event-driven (on submit), not effect-driven (on mount/interval)** — a
real, worth-naming contrast with `StatusPage`'s `useEffect`-based polling; in Angular terms, closer to a plain
method bound to `(ngSubmit)` than to an `effect()`.

**5. `frontend/src/App.tsx`** — add the second route:
```tsx
<Route path="/search" element={<SearchPage />} />
```
No `<Link>` added between the two pages yet — reached directly via URL for this lesson's verification.
Deliberately not teaching React Router's navigation primitives here; that's lesson 13.

## Verification

1. `SearchBar` in isolation — mount with a `console.log` submit handler, no fetch yet. Confirms
   component/JSX/hooks fundamentals before any network code.
2. Wire `fetchSearch` + dump the raw JSON response in `SearchPage`. Confirms the real round trip against the
   already-built `/api/search` endpoint.
3. Replace the raw dump with `HeadlineList`. First real UI output.
4. Loading/error state — verify against a slow search and a deliberately-broken request (e.g. a bad ticker,
   or the API container stopped).
5. Full integration at `http://localhost:3000/search` — real ticker search, cross-checked against what lesson
   9's `curl` calls showed against the same data.
6. Confirm spec 0001's empty-state behavior live: an invalid/unknown ticker renders the plain empty state, not
   an error (spec's Non-goals: no ticker validation; Success Criteria: an empty Today list is normal, not a
   bug).

## Open items

None outstanding — all three flagged during planning were resolved with the user (see Decisions above).
