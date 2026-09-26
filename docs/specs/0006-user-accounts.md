# User Accounts (Google Sign-In)

Spec for the first lesson of a new arc — user accounts, the dependency root for watchlists, notifications, and
an eventual admin role. Finalized via a grilling round. Behavior only, per this project's spec/ADR split (see
learning record 0007) — the OAuth mechanics and session design belong in a follow-up ADR, not here.

## One-line summary

A user can sign in with their Google account, see their name and profile picture plus a sign-out control
everywhere in the app, and sign out — with everything the app does today staying exactly as open to anonymous
visitors as it is now.

## Problem / motivation

Nothing today has a concept of a user — every search is anonymous and shared. Accounts are the prerequisite for
anything actually personal to a user: a watchlist, a notification, an admin view. This spec is that first,
minimal step — prove a real person can sign in and be recognized — before anything is built on top of it.

## Goals

- Sign in with a Google account — the only supported method; no in-house username/password is ever stored,
  sign-in always delegates entirely to Google.
- Once signed in, the user's name and profile picture are visible everywhere in the app, alongside a sign-out
  control — not just on one page.
- A signed-in session persists across closing and reopening the browser; only an explicit sign-out ends it
  early.
- Signing out is a real, visible action, immediately returning the app to its signed-out state.

## Non-goals

- No in-house password storage or a competing sign-in method, now or ever — Google, and potentially other real
  OAuth providers later, is the only path in.
- No linking or merging accounts across multiple providers — irrelevant until a second provider actually
  exists; revisit then, not now.
- No editing a profile inside the app — name and picture always mirror Google exactly, read-only.
- No change to anonymous access — every existing feature works exactly as it does today, signed in or not.
- No watchlists, notifications, per-user data, or an admin role — those are later, separate specs that build on
  this one existing at all.

## Core entities & terminology

Adds one new entry to `CONTEXT.md`: **User** — a real person who has signed in at least once, identified by
their Google identity. Everything else (`Ticker`, `Company`, `Headline`, etc.) is unchanged.

## Outputs / user-facing behavior

Every page shows, in the same place regardless of route: a sign-in control when signed out, or the user's name,
profile picture, and a sign-out control when signed in.

Signing in hands the user off to Google's own sign-in process and returns them to the app already signed in —
no separate account-creation step, no password to set. The very first sign-in and every later one look
identical to the user.

If the session ever goes stale for any reason — it expired, the user revoked access on Google's side, or they
cancelled or denied partway through signing in — the app simply shows the signed-out state. Never a broken page
or an error to make sense of; signing in again is always the way forward.

## Success criteria

- A real Google account can sign in and see its real name and profile picture in the app, in the same place on
  every page.
- Signing out immediately returns the app to the signed-out state, everywhere.
- Closing and reopening the browser without signing out leaves the user still signed in.
- Every existing feature works identically for a signed-in and a signed-out visitor.
- Cancelling or denying Google's sign-in prompt, or an expired/revoked session, always lands back at a normal
  signed-out state — never an error page or a stuck loading state.
- No password field, password storage, or in-house credential exists anywhere in the app.

## Technical approach

See `docs/adr/0016-user-accounts-technical-approach.md` — the sign-in mechanism, session storage, and the
`users` table shape, all decided during this spec's own grilling round, following this project's usual
pattern (see ADR 0006/0007 for the equivalent decisions grouping made).
