# Lesson 37 plan — User Accounts: Google Sign-In (Arc 7, spec 0006, ADR 0016)

Scope: exactly spec 0006's walking skeleton — sign in with Google, see your name and profile picture plus a
sign-out control in the shared `Layout` (site-wide), sign out. No watchlists, no per-user data, no admin role.
One lesson, not split, matching lesson 16's precedent for this shape of feature. Argues from spec 0006
(behavior) and ADR 0016 (technical approach) — decisions already made there aren't re-litigated here.

## Architectural approach

Frontend loads Google's GIS script and renders its button. On success, GIS hands the frontend a signed
credential (ID token) via a JS callback — the frontend POSTs it to a new backend endpoint, which verifies it
(`google-auth`), upserts a `users` row, creates a Redis-backed session, and sets an `HttpOnly` cookie holding
only an opaque session ID. Every later page load calls a read-only "who am I" endpoint that resolves the
cookie to a user (or nothing) — necessary because the cookie is `HttpOnly` by design (ADR 0016), so the
frontend has no way to read it directly.

**Sessions reuse the existing Redis connection, not a second pool.** `search.py`'s `api_lifespan` already
creates `app.state.arq_redis` via `create_pool(...)`, and ARQ's `ArqRedis` class is a real `redis.asyncio.Redis`
subclass — plain `GET`/`SET`/`DELETE` calls work on it directly. No new Redis client needed, no new connection
pool to manage.

**New flat module, `auth.py`** — mirrors `sentiment.py`/`providers.py`'s convention (one module, not a
package) for: verifying a Google credential, upserting a `User` row, and the session `GET`/`SET`/`DELETE`
helpers against Redis. Token verification is injected as a FastAPI dependency
(`get_token_verifier`), the same pattern `get_arq_redis`/`get_session_factory` already establish in
`search.py` — tests override it with a fake, never calling Google for real.

## Files and components likely to change

**New**:
- `backend/src/ticker_backend/auth.py` — credential verification, `User` upsert, session helpers.
- `db/migrations/*_create_users.sql` — `users(sub TEXT PRIMARY KEY, email TEXT, name TEXT, picture_url TEXT,
  created_at TIMESTAMPTZ DEFAULT now(), last_seen_at TIMESTAMPTZ DEFAULT now())`. Keyed on `sub` per ADR 0016,
  not email.
- `backend/tests/test_auth.py`.
- `frontend/src/auth.ts` — `fetchMe()`, `signOut()`, thin wrappers matching `search.ts`/`health.ts`'s own shape.
- `frontend/src/components/AuthControls.tsx` — the sign-in button / name+picture+sign-out area.

**Changed**:
- `backend/src/ticker_backend/models.py` — new `User` model.
- `backend/src/ticker_backend/main.py` — mounts the new `/api/auth/*` router; `CORSMiddleware` gains
  `allow_credentials=True` (ADR 0002's existing single-known-origin restriction is the prerequisite this
  already satisfies — browsers refuse credentials paired with a wildcard origin).
- `backend/src/ticker_backend/config.py` — new `google_client_id: str = ""` and `cookie_secure: bool = False`
  settings (the latter environment-driven per ADR 0016 — `False` for local HTTP dev, `True` once real HTTPS
  exists).
- `.env.example`, `docker-compose.yml`'s `&app-env` — `GOOGLE_CLIENT_ID` (no client secret needed at all —
  GIS's credential flow never exchanges one, confirmed against Google's own docs).
- `frontend/public/index.html` — a static `<script src="https://accounts.google.com/gsi/client" async
  defer>` tag, GIS's own documented integration method.
- `frontend/src/config.ts` — `GOOGLE_CLIENT_ID` constant, hardcoded like `API_BASE_URL` already is (not a
  secret — client IDs are safe to embed in shipped frontend code — and this project has no build-time
  env-var injection mechanism to plumb it through otherwise).
- `frontend/src/components/Layout.tsx` — mounts `<AuthControls />` in the nav, visible on every route.

**Untouched**: `search.py`, `providers.py`, `sentiment.py`, every existing endpoint and test — anonymous search
is unaffected, per spec 0006's own Non-goal.

## Database / data model changes

One new table, `users`, as above. No changes to `headlines`/`stories`/`companies` — nothing here is
user-scoped yet (that's the next arc).

## API / interface changes

- `POST /api/auth/google` — body `{"credential": "<GIS JWT>"}`. Verifies it, upserts the `User` (all of
  `email`/`name`/`picture_url` overwritten from the token's claims every time, per spec 0006's read-only,
  always-mirrors-Google requirement), creates a session, sets the cookie. Returns the current user.
- `GET /api/auth/me` — resolves the session cookie to a user, or `null`/401 if there isn't a valid one
  (expired, revoked, or never signed in — all three collapse to this one response, per spec 0006's "no broken
  state" requirement). Called once on app load to establish initial UI state.
- `POST /api/auth/logout` — deletes the Redis session key outright (real revocation, not just an expiring
  cookie) and clears the cookie.

All three live under a new `router` in `auth.py`, mounted the same way `search.py`'s router already is.

## Backend / frontend changes

Both, as detailed above. Frontend: `AuthControls` calls `fetchMe()` on mount to decide its initial
signed-in/signed-out render; the GIS button's callback POSTs the credential and re-fetches `/api/auth/me`
(simplest correct option — reuses the one source of truth rather than trusting the POST response to stay in
sync with it); sign-out calls the logout endpoint then clears local state. All auth fetches use
`credentials: "include"`, matching ADR 0016.

## Existing tests / new tests required

New `backend/tests/test_auth.py`:
- A verified credential creates a new `User` row on first sign-in, and overwrites `name`/`email`/`picture_url`
  on a later one (never a second row for the same `sub`).
- A rejected/invalid credential (the injected verifier raises) never creates a session or a cookie.
- `/api/auth/me` with no cookie, an unknown session ID, and a real session ID all return the correct shape
  (signed-out for the first two, the real user for the third) — the three "not really signed in" cases
  collapsing to one response is the actual behavior spec 0006 requires, worth a dedicated test each.
- `/api/auth/logout` actually deletes the Redis key, not just clears the cookie — verified by checking Redis
  directly, not just the response.

No new frontend test framework needed — `AuthControls` gets the same Vitest + React Testing Library treatment
existing components already use, `fetchMe`/`signOut` mocked at the fetch boundary like `search.ts` already is.

## Risks and assumptions

- GIS's script is a real external dependency loaded from Google at runtime — if it fails to load (network,
  ad blocker), the sign-in button simply doesn't render; nothing else on the page breaks, matching spec
  0006's "anonymous access unaffected" requirement.
- The two still-open Google Cloud Console questions (billing, the 100-user cap exemption) block getting a
  real `GOOGLE_CLIENT_ID` at all — the wizard below resolves these before any code needs them.
- `ArqRedis`-as-a-plain-Redis-client is a real capability of the library, not yet exercised by this codebase
  outside ARQ's own job machinery — verify live during implementation, not just assumed from its class
  hierarchy.

## Incremental steps

1. **Wizard**: walk through creating the Google Cloud OAuth client ID and consent screen, confirming both
   open questions along the way.
2. `users` migration + `User` model.
3. `auth.py` — credential verification (injectable), `User` upsert, Redis session helpers. Unit-testable
   without a real Google account per the injectable verifier.
4. The three `/api/auth/*` routes, mounted in `main.py`; CORS `allow_credentials=True`.
5. Live verification: a real browser, a real Google account, confirm the whole loop (sign in → cookie set →
   `/api/auth/me` reflects it → sign out → cookie/session both gone) before writing any frontend code against
   it.
6. Frontend: GIS script tag, `auth.ts`, `AuthControls`, mounted in `Layout`.
7. Full stack sanity check: existing search flow untouched and working, sign-in/out working end to end in a
   real browser.

## What actually happened during execution

_(filled in after execution)_
