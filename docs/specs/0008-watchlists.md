# Watchlists

Spec for a signed-in user's personal, persistent list of tracked tickers. Split out from an originally-combined
idea during grilling for spec 0007: that spec covers keeping any ticker page current for every visitor; this one
covers the separate, signed-in-only concern of tracking specific tickers and counting what's new on them since
last viewed. Behavior only, per this project's spec/ADR split (see learning record 0007).

## One-line summary

A signed-in user can track up to 10 tickers in a persistent left-sidebar watchlist, where each entry shows a
live count of headlines published since they last viewed that ticker's own page.

## Problem / motivation

Today there's no way to keep tabs on a ticker without repeatedly re-searching it, and no signal for whether
anything new has shown up on a ticker someone cares about. The left sidebar, present on every page, is currently
empty and reserved for exactly this. This spec gives signed-in users a lightweight way to track a small set of
tickers and see, at a glance, which of them have something new to look at.

## Goals

- A signed-in user can build a personal list of up to 10 tickers, visible in the left sidebar on every page.
- Each row in the list shows the ticker symbol, a count of headlines published since the user last viewed that
  ticker's own page, and a small "×" control for removing it.
- Adding a ticker happens from the search page: searching a ticker shows an "Add SYMBOL to watchlist" button for
  it. Because this reuses the existing search/resolution flow, only real, already-resolved tickers can ever be
  added — there's no separate validation path.
- That same button toggles to "Remove SYMBOL from watchlist" when the currently-searched ticker is already on
  the watchlist, making it the single add/remove entry point on the search page.
- The sidebar's own "×" is a second entry point for removal, available from anywhere in the app.
- Both removal paths are instant — no confirmation step, no undo.
- Viewing a ticker's own page — whether reached by clicking it in the sidebar, searching it manually, browser
  back/forward, or a bookmark — resets that ticker's "new since last viewed" count to zero, regardless of which
  path was used to get there.
- The sidebar's counts stay current on their own, the same way spec 0007 keeps a ticker's own page current —
  no manual refresh is needed to see an up-to-date count.
- The watchlist is hidden entirely for signed-out visitors.

## Non-goals

- No multiple or named watchlists — one single, implicit list per signed-in user.
- No notifications or alerts of any kind (a separate, future spec: Roadmap Phase 3 item 2).
- No admin-facing view of any user's watchlist (a separate, future item: Roadmap Phase 3 item 3, which also
  needs an admin-role concept that doesn't exist yet).
- No manual reordering of the sidebar list (drag-and-drop or otherwise) — list order is simply the order
  tickers were added, oldest first.
- No confirmation or undo step on removal, from either entry point.
- No commitment to exactly how the "new since last viewed" count is computed, or exactly how the sidebar stays
  current — both are technical design decisions for a forthcoming ADR, not behavior commitments of this spec.

## Core entities & terminology

No new named entity beyond what a watchlist *is* as user-facing behavior: a signed-in user's ordered set of up
to 10 tracked tickers, where each tracked ticker also remembers when that user last viewed its page. `CONTEXT.md`'s
existing `Ticker`/`Headline` entries already define what a "headline" or "ticker" is; this spec only adds the
notion of a user tracking a ticker and having a per-ticker last-viewed point in time.

## Outputs / user-facing behavior

Signed out, the sidebar area is simply absent — no empty state, no prompt to sign in. Signed in, the sidebar
lists every ticker the user has added, in the order they added them, each showing its symbol, its current count
of headlines published since that ticker's page was last viewed, and an "×" that removes it immediately when
clicked. Clicking a ticker's row navigates to that ticker's search/detail page exactly as if it had been
searched manually, and viewing that page — by any route — zeroes its count going forward. On the search page
itself, whatever ticker is currently searched shows either "Add SYMBOL to watchlist" or "Remove SYMBOL from
watchlist," reflecting whether it's already on the list; clicking it adds or removes the ticker and the sidebar
updates to match. The list never exceeds 10 tickers; the exact treatment of an attempt to add an 11th (a
disabled button, an inline message, etc.) is left to implementation rather than committed to as behavior here.

## Success criteria

- A signed-in user can add up to 10 tickers to their watchlist from the search page and no more.
- Each watchlisted ticker's sidebar row shows a count of headlines published since that ticker's page was last
  viewed by that user.
- Viewing a watchlisted ticker's page, via any navigation path, resets its count to zero.
- Both the sidebar's "×" and the search page's toggle button remove a ticker instantly, with no confirmation.
- The search page's add/remove button always reflects the current watchlist membership of whatever ticker is
  searched.
- Clicking a sidebar row navigates to that ticker's normal page, identical to a manual search for it.
- The sidebar is entirely absent for signed-out visitors.
- Sidebar counts reflect reality without the user needing to manually refresh the page.
- The sidebar list order is add-order; removing and re-adding a ticker moves it to the end.

## Technical approach

See a forthcoming ADR. It will decide: how the "new since last viewed" count is actually computed (e.g. a
stored per-user-per-ticker last-viewed timestamp queried at read time, versus some other mechanism); the new
endpoints needed to add/remove/list watchlist entries; and how the sidebar's counts hook into the live-refresh
and rate-limiting machinery spec 0007 and ADR 0018 already built, so this doesn't reinvent that mechanism. This
spec depends on spec 0006 for the notion of a signed-in user to whom a watchlist belongs, and on spec 0007 /
ADR 0018 (merged) for how anything on this page can stay current without a manual reload.
