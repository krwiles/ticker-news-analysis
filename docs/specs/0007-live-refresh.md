# Live-Refreshing Ticker Search Results

Spec for keeping a ticker's search results current automatically. Split out from an originally-combined
"Watchlists" idea during grilling: this is a genuinely separate concern — it applies to every ticker page for
every visitor, not just signed-in users with a watchlist — and Watchlists (a follow-up spec) builds its own
per-ticker "new since last viewed" counts on top of whatever mechanism this spec's ADR designs. Behavior only,
per this project's spec/ADR split (see learning record 0007).

## One-line summary

While a ticker's search results page is open and visible, it checks for new headlines/filings and updated
sentiment automatically, folding anything new in without the visitor ever needing to reload.

## Problem / motivation

Today, `/api/search` is a one-shot fetch: what you see is a snapshot from the moment you searched, and a manual
"Refresh" button is the only way to check again. A new headline published a minute later, or a sentiment score
that finishes processing after the page loaded, never appears unless you click it. This spec makes the page keep
itself current on its own, retiring the manual button in favor of a passive indicator of how current the page
already is — and, because any number of open pages doing this compete for the same limited Finnhub request
budget, it's also where this project first has to design a real, centrally-enforced rate limit rather than
relying on ADR 0015's single-flight dedup alone (which only prevents *simultaneous* duplicate fetches, not
frequent *repeated* ones over time).

## Goals

- A ticker's search results page automatically picks up newly published headlines and filings, and sentiment
  scores that finish resolving, without the visitor reloading — for anonymous and signed-in visitors alike, no
  sign-in required.
- This only happens while the page is actually visible/focused; switching away or backgrounding the tab stops
  it, and returning to the tab triggers one immediate check before resuming its normal rhythm.
- New content appears folded into the existing feed as if it had always been there — no highlighting, banners,
  or "new" markers in this version.
- However often this happens, it never causes visible errors, stalls, or degraded behavior — even with many
  pages open across many visitors at once, all sharing the same underlying provider rate limits.
- A background check that fails outright (a network error, a timeout) is entirely invisible: the page simply
  keeps showing whatever it last successfully loaded, and quietly tries again later.
- A background check that comes back *postponed* by the shared provider rate limit — not failed, just not its
  turn yet — says so plainly, with its own calm, factual status distinct from both success and failure: nothing
  is wrong, a check is already scheduled to run on its own.
- The manual "Refresh" button is removed. In its place, the page shows a live "last refresh Ns ago" indicator —
  how long it's been since the last *successful* check with the backend, counting up in whole seconds from 0. It
  resets to zero on every successful check, whether or not that check found anything new, so it always answers
  "how current is my view," not "when did something change."

## Non-goals

- No visual indication of what's new (highlighting, badges, "N new" banners) — silent, in-place updates only.
  Revisit if silent updates turn out to be too easy to miss in practice.
- No user-configurable refresh interval, and no manual "refresh now" control of any kind — the "last refresh"
  indicator is informational only, not a button; there's no way to force a check on demand.
- No specific promised interval or latency — how often this checks is a rate-budget-driven tuning decision for
  the technical design, not a behavior commitment.
- No watchlists, per-ticker "new since last viewed" counts, or any signed-in-only behavior — that's a separate,
  follow-up spec building on this one.
- No live-refresh anywhere else in the app (the status page, etc.) — scoped to a ticker's own search results
  page only.
- No user-visible error state or retry control for a background check that fails outright — always silent to
  the visitor (still logged server-side for diagnosis, an implementation detail, not a behavior commitment). A
  postponed check is not an error and is covered separately above, not by this non-goal.

## Core entities & terminology

No new entity. `CONTEXT.md`'s existing `Ticker`/`Headline` entries already define what's shown; this spec only
changes when the page picks up changes to them, not what they are.

## Outputs / user-facing behavior

The first search looks the same as it does today. Once results are showing, the "Refresh" button is gone;
in its place, near where the button used to be, is a small "last refresh Ns ago" indicator that counts up once a
second, starting from "last refresh 0s ago." New headlines and filings for that ticker appear in the feed on
their own, in the same place they'd already sort to; a headline's sentiment pill updates in place if it resolves
(e.g. "processing" to a real score) while you're looking at it — and either way, the indicator resets to
"last refresh 0s ago" the moment that check succeeds. Switch to another tab or app and checks pause entirely —
nothing happens in the background. Switching back checks immediately, so in practice you'd see the indicator
reset to 0 right away rather than showing a large stale number from however long you were gone. If a check fails
for any reason, nothing about the page changes, and the indicator simply keeps counting up from whenever the
last successful check was; the next check happens on schedule as if nothing went wrong. If a check instead comes
back postponed by the shared rate limit, the page's status area shows that plainly — a calm, distinct message,
not an error — while everything already on the page stays exactly as it was until a later check actually runs.

## Success criteria

- Leaving a ticker's search results page open and visible, headlines/filings published after the initial load
  eventually appear without a manual reload.
- A headline's sentiment status visibly updates in place if it resolves while the page is open.
- Backgrounding the tab stops refresh checks; returning to it triggers an immediate check, then resumes.
- New content is indistinguishable from content that was there on first load — no separate visual treatment.
- This behavior is identical for anonymous and signed-in visitors.
- No visible errors, stalls, or degradation occur from this feature, regardless of how many pages are open at
  once across however many visitors.
- A background check that fails outright produces no visible change to the page at all.
- A background check that comes back postponed by the rate limit shows its own distinct, non-alarming status,
  never the same treatment as a failure.
- The manual "Refresh" button no longer exists anywhere on the page.
- A "last refresh Ns ago" indicator is visible and counts up once per second, starting from 0.
- The indicator resets to zero on every successful check, including one that finds nothing new.

## Technical approach

See a forthcoming ADR — the refresh mechanism itself (frontend polling vs. a push connection), the split between
"check whether anything's new" and "actually fetch from providers," and, most importantly, how a shared Finnhub
request budget gets enforced centrally across every open page and every visitor, are all decided there. This
builds directly on ADR 0015's single-flight job design, which already gives one piece of the puzzle (never two
simultaneous fetches for the same ticker) but not the other (bounding total fetch *frequency* over time).
