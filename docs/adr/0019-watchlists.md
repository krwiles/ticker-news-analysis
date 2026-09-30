# Watchlists: one `watchlist_entries` table doubling as view-tracking, a shared auth dependency, and `GET /api/watchlist` as the batched poll target

Status: accepted — extends `0016-user-accounts-technical-approach.md`, `0018-live-refresh-and-rate-limiting.md`;
technical design for `docs/specs/0008-watchlists.md`

Spec 0008's own grilling (two rounds, plus a follow-up round for this ADR) settled the user-facing behavior:
a signed-in user's single list of up to 10 tickers, add/remove from a search-page button and a sidebar "×,"
live counts that reset on viewing a ticker's page, and a sidebar that stays current on its own. This ADR is
where the mechanism lives, per this project's spec/ADR split (learning record 0007).

## One table serves both membership and "last viewed," scoped to watchlisted tickers only

A watchlist entry and a "last viewed" timestamp are both naturally keyed on `(user, ticker)`, so they live in
one table rather than two:

```sql
CREATE TABLE watchlist_entries (
    user_sub TEXT NOT NULL,
    ticker TEXT NOT NULL,
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_viewed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_sub, ticker)
);
```

No foreign keys, matching this codebase's existing no-`relationship()`/no-FK convention (`users.sub` and
`companies.ticker` are both plain natural-key columns elsewhere). `last_viewed_at` defaults to the same instant
as `added_at`, so a freshly-added ticker starts at "0 new" rather than reflecting headlines from before it was
ever watched.

Viewing a ticker's page only updates `last_viewed_at` for tickers that already have a row in this table — a
signed-in user looking at a ticker they haven't watchlisted writes nothing. The count the spec describes
("headlines published since the last time the user viewed that ticker's page") is computed at read time — a
`COUNT` of `headlines` where `ticker` matches and `published_at > last_viewed_at` — not maintained as an
incremented column, for the same reason `Story.sentiment_score_count` is the one deliberate exception to this
project's general "derive at read time" rule: incrementing on every ingested headline would fan out a write to
every watcher's row on every fetch, for a number almost nobody is looking at in that instant.

**Considered:** a separate `ticker_views` table tracking every signed-in user's view of every ticker,
regardless of watchlist membership (rejected — unbounded write growth with no payoff; a ticker added after
being viewed already gets the "0 new since now" behavior for free from `added_at`'s own default, so there's
nothing a pre-existing view record would add).

## Recording a view is a side effect of `/api/search`, not a new endpoint

`/api/search`'s handler already runs exactly once per ticker per page view (ADR 0018's own note). Rather than
adding a dedicated "mark as viewed" endpoint the frontend would need to remember to call, `/api/search` gains
one small addition: if the request resolves to a signed-in user (see below) who has a `watchlist_entries` row
for the ticker being searched, upsert that row's `last_viewed_at = now()` as an unawaited side effect, errors
swallowed — the same shape `jobs.py`'s `enqueue_sentiment_after_fetch` and `search_status`'s background-fetch
trigger already use. This covers every way of landing on a ticker's page (sidebar click, manual search,
back/forward, a bookmark) for free, since all of them funnel through the same `/api/search` call the page
already makes on load.

**Considered:** a dedicated `POST /api/watchlist/{ticker}/viewed` endpoint, called explicitly by the frontend
alongside its existing `fetchSearch` call (rejected — asks the frontend to remember a second call on every
page view for no behavioral difference; `/api/search` already fires at exactly the right moment).

## A shared, two-flavor auth dependency, extracted from `/api/auth/me`'s inline logic

No reusable "who's signed in" FastAPI dependency exists today — `/api/auth/me` resolves the session cookie
inline (`request.cookies.get(SESSION_COOKIE_NAME)` → `_resolve_session` → `session.get(User, sub)`). Four new
endpoints need the same resolution, so this ADR extracts it into `auth.py` as two thin dependencies built on
the same underlying lookup:

- `require_user(request, session_factory, arq_redis) -> User` — raises `401` if there's no valid session.
  Used by all four new watchlist endpoints.
- `optional_user(request, session_factory, arq_redis) -> User | None` — returns `None` instead of raising.
  Used by `/api/search`'s view-recording side effect, and by `/api/auth/me` itself (a pure refactor of its
  existing body, no behavior change).

This is a targeted extraction of code that already exists, not new behavior — the same cookie, the same
`_resolve_session`, the same `User` lookup, now shared instead of duplicated four (soon five) times.

A cookie carrying identity on every request doesn't conflict with REST's statelessness constraint: the server
still keeps no per-client memory between requests — every request is self-contained, bringing its own
credential, which the server resolves via a stateless-per-request Redis lookup rather than recalling anything
from a prior request.

## New endpoints

- **`POST /api/watchlist`** `{"ticker": "MSFT"}` — `require_user`. `400`/`404` if the ticker has no row in
  `companies` (i.e. it's never been searched/fetched before — reuses `/api/search`'s existing resolution
  instead of triggering a fresh one, per the spec's "no separate validation path" goal). `400` if the user
  already has 10 entries. Idempotent if the ticker's already watchlisted. Inserts a row with `added_at`/
  `last_viewed_at` both `now()`.
- **`DELETE /api/watchlist/{ticker}`** — `require_user`. Idempotent delete; no error if the ticker wasn't
  watchlisted.
- **`GET /api/watchlist`** — `require_user`. Loads the user's entries ordered by `added_at` ascending (this
  alone gives add-order; removing and re-adding a ticker naturally moves it to the end, since re-adding
  inserts a fresh row). For each entry, computes its current count via the read-time `COUNT` query above, and
  — as an unawaited, exception-swallowed side effect — calls `enqueue_background_fetch` for every entry's
  ticker, exactly like `/api/search/status` already does for one ticker. This single batched endpoint is both
  "read current counts" and "maybe trigger fetches," so the frontend's sidebar poll makes one call per tick,
  not one per watchlisted ticker.

**Considered:** having the sidebar poll `/api/search/status` once per watchlisted ticker instead of adding a
batched `GET /api/watchlist` (rejected, per explicit direction during grilling — N separate requests every
poll tick is needless duplication when one endpoint can loop server-side over the same small list it's already
loading to build the response).

## Rate-limit interaction needs no new code

`GET /api/watchlist` calling `enqueue_background_fetch` up to 10 times per invocation is safe by construction:
each call independently checks its own per-ticker cooldown and the one shared 60/min Finnhub window
(`rate_limit.py`, ADR 0018, untouched). A burst of watchlist polls across many users composes with
`/api/search/status`'s own triggers through the exact same shared counter — there's only ever one gate, and
every caller of `enqueue_background_fetch` already shares it by construction. This is the "any future caller
of the fetch job... automatically gets the same protection for free" consequence ADR 0018 already called out.

## Frontend

- New `frontend/src/watchlist.ts`, mirroring `search.ts`/`auth.ts`'s existing per-endpoint fetch-wrapper shape:
  `fetchWatchlist()`, `addToWatchlist(ticker)`, `removeFromWatchlist(ticker)`, each passing
  `credentials: "include"` (this app's cross-origin UI/API split, ADR 0002/0016, means the session cookie
  never travels on a fetch that doesn't opt in explicitly).
- `fetchSearch` (`search.ts`) also adds `credentials: "include"`, since `/api/search` now cares about an
  optional session cookie where it didn't before.
- A new sidebar component polls `fetchWatchlist()` on a 20-second interval, reusing `SearchPage.tsx`'s existing
  Page Visibility pause/resume pattern verbatim (pause while hidden, immediate check on refocus) rather than
  inventing a second one.
- `SearchPage.tsx`'s `STATUS_POLL_INTERVAL_MS` changes from 5000 to 10000 — a tuning adjustment (spec 0007's
  own Non-goals explicitly leave the exact interval unspecified), made here because a watchlist sidebar
  checking up to 10 tickers every 20 seconds alongside a single open ticker page checking every 5 seconds was
  an unnecessarily aggressive combination for how time-sensitive either indicator actually needs to feel.
- The search page's add/remove button's state is sourced from whether the currently-searched ticker appears in
  the same `fetchWatchlist()` list the sidebar already loads — exact wiring (e.g. a shared context vs. a
  redundant fetch) is an implementation-plan concern, not an architectural one.

## Consequences

- **`/api/search` gains a side effect it didn't have before.** Its docstring/behavior now depends on an
  optional session cookie, where it was previously indifferent to authentication entirely — needs a doc note
  so a future reader doesn't assume it's still auth-blind.
- **`auth.py` gains two dependencies where zero existed.** `/api/auth/me`'s behavior is unchanged (same cookie,
  same lookup, same response shape), but its logic now lives in a shared function four other endpoints also
  depend on — a bug in session resolution now has one place to fix instead of five.
- **The 20-second/10-second interval split is a tuning choice, not a behavior commitment** — either number can
  change later without touching spec 0007 or spec 0008, both of which deliberately left exact timing
  unspecified.
- **This composes with ADR 0018 without changing it.** `enqueue_background_fetch` and `rate_limit.py` are
  reused as-is; watchlists simply become a second caller of an already-shared gate, exactly as ADR 0018
  anticipated.
