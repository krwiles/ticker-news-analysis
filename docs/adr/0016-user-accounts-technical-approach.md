# User accounts: Google Identity Services, Redis-backed sessions, and the `users` table

Spec 0006's own grilling rounds covered real technical ground before any code exists. This ADR is where that
reasoning lives, so it isn't lost the way a conversation eventually is — spec 0006 itself stays behavior-only
by design (learning record 0007). One combined ADR, not several: the sign-in mechanism, session storage, and
`users` table shape are tightly coupled — unlike spec 0002's genuinely separable decisions (ADR 0006-0009),
splitting these would mean three documents constantly cross-referencing each other.

## Sign-in mechanism: Google Identity Services, not a classic OAuth Authorization Code flow

**This section was revised before any code was written**, not after — worth recording exactly how, since it's
a real example of a first answer turning out wrong on closer inspection. The first pass researched "FastAPI +
Google OAuth" broadly and found Authlib as the dominant community library for the classic
redirect-to-Google/exchange-a-code-for-tokens flow. That's a real, working pattern — but it's built for apps
that need an access token to call a Google API *on the user's behalf* later (Calendar, Drive, and so on).
Checked directly against Google's own current guidance: for an app that only ever needs to know *who* signed
in, Google explicitly recommends **Google Identity Services (GIS)** — the "Sign in with Google" button —
over classic OAuth, calling the latter "unnecessarily complex" for identity-only needs.

**Considered:**
- **Classic OAuth Authorization Code flow, via Authlib** (rejected) — the right tool if this app ever calls a
  Google API on the user's behalf. It never does (spec 0006 has no such goal), so the redirect dance, code
  exchange, and refresh-token handling this flow requires are all machinery for a capability that isn't used.
- **Google Identity Services, credential flow** (chosen) — the frontend loads Google's small GIS script and
  renders its sign-in button; on success, GIS hands the frontend a signed credential (an ID token, a JWT)
  directly via a JS callback — no authorization code, no server-to-server token exchange at all. The frontend
  POSTs that credential to the backend, whose only job is verifying it.

**Consequence, noted for the future, not solved now**: GIS's credential flow is Google-specific. Spec 0006
leaves the door open for another provider later but explicitly makes account-linking a Non-goal until that's
real — this is the same shape of deferral. GitHub, Microsoft, etc. have no GIS equivalent; a second provider
would mean building a classic OAuth flow *then*, alongside GIS, not extending GIS to cover it. Accepted:
building the simplest correct tool for today's actual requirement, matching how this project has consistently
deferred generalizing for a hypothetical need (no rate limiting until real, no backfill job until needed).

## Backend verification: Google's own `google-auth` library

Verifying the ID token GIS hands back means checking its signature against Google's own public keys (which
rotate), plus its issuer, audience, and expiry. Google's own docs are explicit that this step specifically
should go through a client library, not hand-rolled JWT/JWKS handling — this is exactly the kind of fiddly,
security-sensitive logic ADR 0010's raw-`httpx` precedent was never meant to cover (that precedent is about
avoiding unnecessary SDK weight for simple REST calls, not about hand-rolling cryptographic verification).
**Chosen: `google-auth`** (`google.oauth2.id_token.verify_oauth2_token`) — Google's own official library,
narrowly scoped to exactly this verification step, nothing more (no OAuth-flow machinery, since GIS already
handled that on the frontend).

## Session storage: Redis-backed, not a signed cookie

Settled during spec 0006's grilling round: a signed cookie needs no server-side storage but can never be
revoked early — the only lever is rotating the signing secret, which logs out everyone at once. Redis is
already running here for ARQ (lesson 35 covers how the two coexist in one instance without colliding or
competing); a session lookup is one cheap Redis round-trip, and it buys real per-session revocation — useful
the moment a "log out everywhere" action or an admin capability exists, not something to retrofit later.

**Shape**: the cookie holds only an opaque session ID — never session data itself. Redis holds
`session:{opaque-id}` → the signed-in user's internal id, with a sliding TTL (refreshed on each authenticated
request) long enough to match spec 0006's "persists across browser restarts" requirement in practice — **30
days**, a common default for this kind of persistent-login session, refreshed forward on activity so an
actively-used session never silently expires. An explicit sign-out deletes the Redis key directly — instant,
real revocation, not just an expired-and-ignored cookie.

## The cookie's own attributes — verified, not assumed, since this project's `ui`/`api` split makes it easy to get wrong

`ui` (`:3000`) and `api` (`:8000`) are different **origins** (ADR 0002) but the same **site** — the
`SameSite` cookie attribute is evaluated against the registrable domain alone, which doesn't include the port.
Checked directly rather than assumed (two wrong guesses were caught and corrected during this exact research,
worth being honest about): Chrome does *not* exempt `localhost` from `SameSite=None`'s `Secure` requirement,
but `SameSite=None` was never actually needed here in the first place, because `localhost:3000` and
`localhost:8000` are same-site by definition (port is irrelevant to "site").

- **`SameSite=Lax`** — the modern default, and sufficient here since `ui` and `api` are same-site. Verified:
  cookie auth across different `localhost` ports works under `Lax` in every real report checked; `None` is
  only required when frontend and backend are genuinely different registrable domains.
- **`HttpOnly`** — always on; JavaScript never needs to read this cookie, only send it, so there's no reason
  to expose it to a script (mitigates a class of XSS-driven token theft for free).
- **`Secure`** — **environment-dependent, not a fixed value.** `Secure` requires HTTPS to be honored at all;
  set it `True` over this project's current plain-HTTP local dev and the browser refuses to store the cookie
  outright, silently breaking sign-in. Driven off `Settings` (matching `config.py`'s existing pattern) —
  `False` for local dev, `True` once a real HTTPS deployment exists. Already flagged as a known gap in the
  existing secrets-management idea (`NOTES.md`, 2026-09-21: "no HTTPS or real CORS origin yet") — this is the
  same gap, not a new one.
- **CORS**: `api`'s existing `CORSMiddleware` (ADR 0002) is already restricted to the single known `ui`
  origin, not a wildcard — the prerequisite for enabling credentialed cross-origin requests at all (browsers
  refuse `allow_credentials` paired with a wildcard origin). Needs `allow_credentials=True` added
  server-side, and the frontend's `fetch` calls need `credentials: "include"` — both already anticipated in
  `NOTES.md`'s own pre-research.

## `users` table shape

Keyed on Google's own stable `sub` claim, not email — an email can change on Google's side; `sub` cannot, and
is exactly what Google's own docs specify as the correct comparison key for "is this the same person as
before." Columns: `sub` (primary key), `email`, `name`, `picture_url`. Per spec 0006's "read-only, always
mirrors Google" requirement, `name`/`picture_url`/`email` are overwritten from the ID token's claims on every
successful sign-in, not just set once — the app's copy should never drift from what Google currently reports.
A row is created transparently on a `sub` the table hasn't seen before; first-ever sign-in and every later one
go through the identical upsert, no separate "new account" path to maintain.

## Not decided here

Exact FastAPI route shapes, the `Layout` component's sign-in/sign-out UI, and test strategy belong in the
implementation plan, not this ADR — this document is the technical *approach*, the plan is the *build*.
