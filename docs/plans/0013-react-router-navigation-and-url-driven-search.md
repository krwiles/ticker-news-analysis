# Lesson 13 plan — React Router: navigation, and URL-driven search

Scope: `NOTES.md`'s lesson 13. Two real, previously-missing pieces: navigation between `/` and `/search`
(there currently is none — both routes only work if you type the URL directly), and making the URL the actual
source of truth for the current search (`useSearchParams`), the data-loading pattern this lesson was scoped
around. Not in scope: Today/Recent split, styled category badges, Refresh button (lesson 14, arc-2 capstone).

Re-checked `docs/specs/0001-first-feature.md` in full: nothing it requires touches routing/URL mechanics
directly, so nothing here is at risk of skipping a spec requirement. Worth carrying forward explicitly: spec
0001 says Refresh "just calls the exact same `GET /api/search` again for the currently-shown ticker" — putting
the ticker in the URL now means lesson 14's Refresh button is just `fetchSearch(searchParams.get("ticker"))`,
not new state to invent later.

## Decisions confirmed with the user (2026-09-13)

1. **Nav links, via a `Layout` component** — added specifically to demonstrate real client-side routing, not
   left implicit. `<Outlet />` is named in the lesson as React Router's closest one-to-one match to Angular's
   `<router-outlet>`.
2. **`useSearchParams` drives the search** — confirmed as the right read of "the data-loading pattern."
3. **Case handling, clarified precisely**: writing the URL (on submit) uppercases — canonical form, e.g. always
   `?ticker=AAPL`, never `?ticker=aapl`. Reading the URL (on mount, or a param change from browser
   back/forward, or a hand-typed/shared link) must work regardless of case — **and already does**, with no
   extra frontend code needed: `search.py`'s endpoint calls `ticker.upper()` before anything else happens
   server-side, so `fetchSearch` passing a lowercase ticker straight through already resolves correctly. This
   gets an explicit test (see below) rather than resting on that claim unverified.

## What gets built

**1. `frontend/src/components/Layout.tsx`** — nav (`<Link to="/">Status</Link>`, `<Link to="/search">Search</Link>`)
+ `<Outlet />`.

**2. `frontend/src/App.tsx`** — nest both existing routes under `Layout`:
```tsx
<Routes>
  <Route element={<Layout />}>
    <Route path="/" element={<StatusPage />} />
    <Route path="/search" element={<SearchPage />} />
  </Route>
</Routes>
```

**3. `frontend/src/pages/SearchPage.tsx`** — `useSearchParams` replaces the purely-local submit flow:
- On submit: normalize once (`ticker.toUpperCase()`), then both `setSearchParams({ ticker: normalized })` and
  `fetchSearch(normalized)` — a single normalization point, not two.
- On mount and whenever the URL's `ticker` param changes: if present, call `fetchSearch` with the raw param
  value as-is (no client-side uppercasing on the read path — deliberately, since it's unnecessary given the
  backend's own normalization, and rewriting the URL on a mere read would add an unwanted extra history entry).

**4. `frontend/src/components/SearchBar.tsx`** — optional `initialValue?: string` prop, seeding its internal
`useState` only, so the input reflects a URL-seeded ticker too. Additive, backward-compatible.

## Verification

1. `Layout` + nested routes: both pages render at their URLs, nav links appear, clicking between them causes no
   full page reload (concretely: `StatusPage`'s poll interval doesn't reset on navigating away and back).
2. New navigation test (`App.test.tsx` or `Layout.test.tsx`): click the "Search" link from `/`, confirm
   `SearchPage`'s content appears — proves routing and navigation work together, not just each page alone.
3. `useSearchParams` wiring: visit `http://localhost:3000/search?ticker=AAPL` directly, confirm real results
   load with zero manual interaction.
4. **Case-insensitivity, verified explicitly, not assumed**: visit (or render, in a test, via
   `<MemoryRouter initialEntries={["/search?ticker=aapl"]}>`) a *lowercase* URL ticker and confirm it still
   fetches and renders correctly — the concrete regression guard for the user's explicit requirement.
5. Existing `SearchPage.test.tsx` suite (4 tests) updated to render inside `<MemoryRouter>` — required because
   `useSearchParams` throws outside a router context, not optional.
6. Full pass: `npm run test`, `npm run typecheck`, `npm run build`, then live via `docker compose up --build`.

## Open items

None outstanding — all three resolved with the user (see Decisions above).
