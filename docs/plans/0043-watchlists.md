# Watchlists

Implements `docs/specs/0008-watchlists.md`, technical design in `docs/adr/0019-watchlists.md`. Both finalized
via grilling, plus a domain-modeling pass confirming `watchlist_entries`'s shape. One new table, one new
router, a shared auth dependency extracted from existing logic, and — since no sidebar exists in `Layout.tsx`
today — new frontend layout work, not just new data plumbing.

## A frontend decision this plan makes, not settled in the ADR

ADR 0019 deliberately left "how the search page's button and the sidebar stay in sync" to this plan. The spec's
own success criteria ("the button always reflects current membership," "the sidebar updates to match") commit
to *instant* consistency between the two, not eventually-consistent-within-20-seconds — so they need one shared
piece of state, not two independent pollers. This codebase has no existing shared-state pattern (no
`createContext` anywhere today), but it already uses `react-router`, which provides exactly this via
`<Outlet context={...}>` / `useOutletContext()` — reused rather than introducing a new primitive:

- `Layout.tsx` becomes the single owner of both auth identity and watchlist state: it calls `fetchMe()` once
  (lifted out of `AuthControls`, which currently owns this privately) and holds the resulting `user`; it fetches
  the watchlist once when `user` transitions from signed-out to signed-in, then polls every 20s while signed in
  (pausing/resuming on visibility, same pattern as `SearchPage.tsx`'s existing poll), and clears everything
  immediately on sign-out.
- `AuthControls` changes from owning `fetchMe()`/`user` state itself to receiving `user` and callbacks as props
  from `Layout` — a refactor of existing, tested code, not new behavior; its GIS button wiring is unchanged.
- The `Sidebar` (new) renders only while `Layout`'s `user` is non-null, straight from the same state.
- `Layout` passes `{ entries, add, remove }` via `<Outlet context={...}>`; `SearchPage` reads it with
  `useOutletContext()` to derive whether the current ticker is watched and to call `add`/`remove` — both
  mutate `Layout`'s one copy of the state, so the sidebar reflects a click on the search page's button (or vice
  versa) without waiting for the next poll tick.

## What changes

| File | Change |
| --- | --- |
| `db/migrations/<timestamp>_create_watchlist_entries.sql` (new) | `watchlist_entries(user_sub, ticker, added_at, last_viewed_at)`, composite PK `(user_sub, ticker)`, no FKs (matches this codebase's convention). |
| `backend/src/ticker_backend/models.py` | New `WatchlistEntry` ORM class mirroring the migration. |
| `backend/src/ticker_backend/auth.py` | Extracts `/api/auth/me`'s inline cookie→session→user lookup into `require_user` (raises `401`) and `optional_user` (returns `None`), both as FastAPI dependencies; `/api/auth/me` refactored to call `optional_user` internally — same response shape, no behavior change. |
| `backend/src/ticker_backend/watchlist.py` (new) | New router: `POST /api/watchlist`, `DELETE /api/watchlist/{ticker}`, `GET /api/watchlist` (see ADR 0019 for each endpoint's exact contract). |
| `backend/src/ticker_backend/search.py` | `/api/search` gains `optional_user` and, as an unawaited, exception-swallowed side effect, upserts `last_viewed_at = now()` on the caller's `watchlist_entries` row for this ticker if one exists. |
| `backend/src/ticker_backend/main.py` | Registers the new `watchlist` router alongside the existing ones. |
| `frontend/src/watchlist.ts` (new) | `fetchWatchlist()`, `addToWatchlist(ticker)`, `removeFromWatchlist(ticker)` — same typed-fetch-wrapper shape as `search.ts`/`auth.ts`, all with `credentials: "include"`. |
| `frontend/src/search.ts` | `fetchSearch` adds `credentials: "include"` (now cares about an optional session cookie). |
| `frontend/src/components/AuthControls.tsx` | Refactored to receive `user`/`onSignedIn`/`onSignedOut` as props instead of owning `fetchMe()`/local `user` state. |
| `frontend/src/components/Sidebar.tsx` (new) | Renders watched tickers (symbol, live count, "×"); purely presentational — state and polling live in `Layout`. |
| `frontend/src/components/Layout.tsx` | Owns `user` (lifted from `AuthControls`) and watchlist state/polling (new, per the decision above); renders `Sidebar` conditionally; passes watchlist state via `<Outlet context>`. |
| `frontend/src/pages/SearchPage.tsx` | `STATUS_POLL_INTERVAL_MS` 5000 → 10000; new add/remove button reading/calling `Layout`'s watchlist state via `useOutletContext()`. |

`jobs.py` and `rate_limit.py` are unchanged — `GET /api/watchlist` calls `enqueue_background_fetch` exactly as
`search_status` already does, just once per watched ticker in a loop.

## Order of work (TDD at each seam)

1. **Migration** — write it, run it against the local stack, confirm the table exists with the right columns/PK.
2. **`models.py`** — add `WatchlistEntry`; no tests of its own (mirrors the existing convention: `Company`/`User`
   aren't unit-tested directly either).
3. **`auth.py`** — tests first: `require_user` returns the `User` for a valid session and raises `401` for a
   missing/invalid one; `optional_user` returns the `User` or `None` for the same two cases, never raising.
   Then refactor `/api/auth/me` onto `optional_user` and confirm every existing `test_auth.py` test still
   passes unchanged — this step must not alter `/api/auth/me`'s observable behavior at all.
4. **`watchlist.py`** — tests first, one seam at a time:
   - `POST /api/watchlist` — creates an entry for a valid, already-`companies`-known ticker; `404`/`400` for a
     ticker with no `companies` row; `400` at exactly 10 existing entries; idempotent (no error, no duplicate)
     if the ticker's already watchlisted; `401` signed out.
   - `DELETE /api/watchlist/{ticker}` — removes an existing entry; idempotent if it wasn't there; `401` signed
     out.
   - `GET /api/watchlist` — returns entries ordered by `added_at` ascending, each with a `COUNT`-derived
     `new_headlines` figure; calls `enqueue_background_fetch` once per entry as an unawaited, exception-
     swallowed side effect (verified via a fake/spy, not by slowing the response down — same technique
     `test_search_endpoint.py` already uses for `search_status`'s own trigger); `401` signed out; empty list
     (not an error) for a signed-in user with no entries.
5. **`search.py`** — tests first: a signed-in user with a matching `watchlist_entries` row gets it upserted to
   `now()` after a successful `/api/search` call; a signed-in user with no matching row is untouched; a
   signed-out call is unaffected; an exception during the upsert never surfaces as a failed search (same
   swallow-and-log pattern already proven for `search_status`'s background trigger).
6. **Frontend, backend-shape-driven first:**
   - `watchlist.ts` — tests first, mirroring `search.test.ts`'s shape: each function's request/response
     handling, `credentials: "include"`, throwing on non-2xx.
   - `AuthControls.test.tsx` — update for the new props-based shape; behavior (button rendering, sign-in/out
     flow) must stay identical from a user's perspective.
   - `Layout.test.tsx` (new) — the `fetchMe()`-then-conditionally-poll-watchlist orchestration: no poll while
     signed out; an immediate fetch and 20s poll while signed in; visibility pause/resume; `Sidebar` absent
     while signed out; `add`/`remove` update the shared state immediately (no waiting for the next poll tick).
   - `Sidebar.test.tsx` (new) — renders entries with their counts; "×" calls the passed-in `remove`; renders
     nothing given a null/empty watchlist state.
   - `SearchPage.test.tsx` — the add/remove button's label/action derived from `useOutletContext()`'s entries;
     `STATUS_POLL_INTERVAL_MS`'s new value.

## Tests

- `test_auth.py`: new `require_user`/`optional_user` tests, plus confirming `/api/auth/me`'s existing tests
  pass unchanged after the refactor.
- `test_watchlist_endpoint.py` (new): every case listed under step 4 above.
- `test_search_endpoint.py`: new cases for the view-recording side effect.
- Frontend: `watchlist.test.ts` (new), `AuthControls.test.tsx` (updated), `Layout.test.tsx` (new),
  `Sidebar.test.tsx` (new), `SearchPage.test.tsx` (updated).
- Deliberate-break checks on: `require_user`/`optional_user`'s two branches, the 10-entry cap check, the
  `companies`-row validation check, the view-recording upsert's scoping (only an existing entry gets touched),
  and `Layout`'s signed-in/out state transitions — this project's usual discipline (a test that can't fail for
  the right reason proves nothing, per lesson 39's finding, reaffirmed in plan 0042's own execution notes).

## Verification

1. Full backend and frontend suites green.
2. Live, against the real stack: sign in, add a ticker that's never been searched before (expect rejection),
   search it once, add it again (expect success), confirm it appears in the sidebar immediately with the
   right initial count (0).
3. Remove it via the sidebar's "×" and confirm the search page's button flips back to "Add" without a page
   reload; re-add via the button and confirm the sidebar picks it up the same way.
4. Leave a watched ticker's page open in one tab and the app open in another; confirm a genuinely new headline
   (or a manually-inserted test row) eventually shows up in the sidebar's count without the user refreshing,
   and that visiting that ticker's page resets it to 0.
5. Background several tabs, confirm the sidebar's poll pauses, and refocusing triggers an immediate check
   (mirroring spec 0007's already-verified pattern).
6. Sign out and confirm the sidebar disappears entirely, immediately, without a page reload.
7. While the shared Finnhub budget is deliberately exhausted (same technique plan 0042 used to verify ADR
   0018), confirm `GET /api/watchlist` still returns promptly with current data — no hang, no error — proving
   this composes with the existing rate limit rather than needing new handling of its own.
