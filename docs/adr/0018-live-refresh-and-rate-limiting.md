# Live-refresh polling reuses `/api/search/status`; a shared Finnhub rate limit gates the fetch job via ARQ's native deferred execution

Status: accepted — extends `0004-fetch-runs-as-an-arq-job.md` and `0015-single-flight-jobs-per-ticker.md`,
technical design for `docs/specs/0007-live-refresh.md`

Spec 0007's own grilling settled the user-facing behavior (silent, visible-tab-only refresh, a "last refresh
Ns ago" counter, no manual button). This ADR is where the mechanism lives, following this project's usual
spec/ADR split (learning record 0007). One combined ADR, not several, because the polling shape and the
rate-limit design are tightly coupled — the entire reason the rate limit needs any real design at all is that
live-refresh introduces a source of repeated, unattended fetch attempts that didn't exist before.

## One polling endpoint, not two

`/api/search/status` already exists (lesson 26/ADR 0014) as a read-only endpoint: it queries current Postgres
state via `_load_search_results` and enqueues nothing. The frontend's existing sentiment poller already calls
it every 5 seconds. Rather than inventing a second "check for updates" endpoint, `/api/search/status` gains one
new responsibility: alongside its existing read, it decides whether it's also time to trigger a background
fetch for that ticker, and does so without waiting for it.

`/api/search` keeps its existing, distinct role: enqueue-or-join the fetch job and *await* its result (ADR
0004/0015), because a ticker with no existing data has nothing to show while waiting. Once the manual Refresh
button is retired (spec 0007), `/api/search` fires exactly once per ticker per page view (the initial
navigation); every check after that goes through `/api/search/status`.

**Considered:** a dedicated new "check for updates" endpoint, separate from `/api/search/status` (rejected —
`/api/search/status`'s shape, an unawaited read of current state, is already exactly what's needed; a second
endpoint returning the same shape would be pure duplication for no gained clarity).

## Rate limiting gates the whole fetch job, deferred via ARQ, not the Finnhub call alone

A shared Redis counter tracks real Finnhub calls in the current 60-second window (`INCR` + `EXPIRE 60`, a
fixed calendar-style window, not a sliding one). When `/api/search/status`'s background-trigger path wants to
check a ticker and the counter is at Finnhub's free-tier cap (60), it enqueues the *same* deterministic fetch
job (`fetch_headlines:{TICKER}`, ADR 0015) with ARQ's native `_defer_by` set to roughly the time remaining in
the current window, instead of enqueuing it to run now.

This defers the **entire** fetch job — EDGAR included — not just the Finnhub call inside it. `enqueue_job`'s
own ID-collision check (verified directly against ARQ's source) treats a deferred job exactly like an
in-flight one: any other trigger for the same ticker in the meantime gets `None` back and joins the same
deferred job, exactly as ADR 0015's single-flight already works for jobs running right now. ARQ's own queue
(the same Redis sorted set jobs already live in) is the "waiting list" — nothing new needs to track "which
tickers still owe a Finnhub call."

A second, independent gate: a per-ticker `last_fetch:{ticker}` cooldown key (a short TTL, exact value a
tuning detail) prevents one heavily-polled ticker from repeatedly consuming the shared budget on itself while
every other open ticker starves. Either gate being tripped defers the job the same way.

**Considered:**
- **Gate the Finnhub call alone, inside `providers.py`, letting the rest of the job run** (rejected, was the
  original plan) — leaves nothing that guarantees a skipped Finnhub call is ever retried. Whether it happens
  depends entirely on the next poll's luck with the budget, so a heavily-polled-but-unlucky ticker's Finnhub
  data could go stale indefinitely while the job still reports as having "succeeded."
- **A hand-rolled queue of pending Finnhub requests** (rejected) — ARQ's own job queue, via `_defer_by`,
  already provides this; building a second one would be pure duplication.
- **A true sliding-window rate counter** (rejected, for now) — more exact, but more moving parts than a fixed
  window needs to solve the actual problem; same "accept the small, well-understood edge case" call this
  project made for `recent_headlines_cutoff` and ADR 0015 itself. Revisit if the fixed window's boundary case
  ever causes real 429s.

## Explicit searches never wait on the rate gate

`/api/search`'s own enqueue call is never subject to the defer logic above — it always requests the job to run
now. But it can still *join* a job that the background-refresh path already deferred (same job ID), and
naively awaiting that job's result would mean an explicit search silently blocks for however long the defer
window is — the exact "blank screen" risk spec 0007 exists to avoid.

The fix: `/api/search` checks `await job.status()` (ARQ's `JobStatus` enum, confirmed to distinguish
`deferred` from `queued`/`in_progress`/`complete`) immediately after getting a job handle, before deciding
whether to await it:

- **`deferred`** — skip the await entirely. Build the response from current Postgres state immediately, with
  `status = "deferred"` (its own value, distinct from a genuine failure — see the Addendum below) and the same
  `providers_status = {}`/`grouping_status = "unknown"` fallback shape otherwise.
- **`queued` / `in_progress`** — await as today, bounded by `job_timeout_seconds`; this means "about to run"
  or "running," not "waiting for a rate-limit window," so the existing wait is still the right call.

**Considered:** always awaiting regardless of status, relying on `job_timeout_seconds` (10s) to bound the wait
(rejected) — a deferred job can be scheduled well past 10 seconds out, so this would turn a rate-limited
background poll into a misleadingly labeled failure on an otherwise perfectly healthy, data-having page (this
is exactly the mislabeling the Addendum below describes finding in practice, from a different code path).

## Consequences

- **`/api/search/status`'s docstring claim — "no fetch_headlines_job... enqueue, just current Postgres
  state" — is no longer entirely true.** It still never *awaits* a fetch, but it can now *trigger* one in the
  background. **Done** — see the Addendum below, which also covers a real bug this gap in follow-through let
  ship.
- **The rate counter protects the app as a whole, not just live-refresh.** Any future caller of the fetch job
  (a scheduled watchlist refresh, per ADR 0004's own anticipated future) automatically gets the same
  protection for free, since the gate lives at the enqueue-for-background-purposes layer, not inside the
  live-refresh code specifically.
- **A burst of many different tickers deferred to the same future window could, in a rare worst case, still
  exceed 60 calls in that window** if they all land and execute close together. Accepted rather than
  engineering staggered defer times — same risk-acceptance precedent as the fixed-window choice itself.
- **Explicit searches are not perfectly bounded by the 60/min cap either**, since they're deliberately exempt
  from the gate. Accepted: real human-typed searches are inherently self-limiting at this app's actual scale;
  the unbounded risk was always the *background*, unattended polling, which this design fully bounds.
- **This composes with ADR 0015 without changing it.** The deterministic job ID and the
  enqueue-returns-`None`-so-join-instead behavior are exactly what already existed; deferred execution is just
  a new *score* on the same queue entry, not a new mechanism layered awkwardly on top.

## Addendum (2026-10-01): a deferred check needed its own visible status, not a reused failure label

The gap this ADR's own first Consequence flagged and never closed turned into a real bug: `/api/search` labeled
a deferred job `"complete_failure"` — the exact same `status` value used for a genuine fetch failure. A page
loaded (or revisited) while its ticker happened to be on the rate-limit cooldown showed "Couldn't fetch new
results right now" and stayed showing it *permanently*, even once the deferred fetch went on to succeed —
because `/api/search/status`'s own poll only ever refreshed `sentiment`/`days`, never `status`/`providers`/
`grouping`, so nothing could ever correct the mislabeled state. Spec 0007 has been updated to describe the
fix's actual behavior directly (a postponed check gets its own distinct, non-alarming status, not silence and
not a failure label) rather than carrying a stale "entirely invisible" guarantee this fix deliberately moved
away from.

**The fix, in the same two places this ADR already designed:**
- `/api/search` now returns `status = "deferred"` — a fourth value alongside `success`/`partial_failure`/
  `complete_failure` — when `job.status() == JobStatus.deferred`, instead of reusing `complete_failure`.
- `/api/search/status`'s response shape grew: it now also returns `status`/`providers`/`grouping`, not just
  `sentiment`/`days`. It checks its own triggered job's status, and when that job is actually `complete`,
  reads its (already-available, non-blocking — not a new wait) result and reports the real outcome; otherwise
  it reports `"deferred"` with the same `{}`/`"unknown"` fallback `/api/search` uses. The frontend's poll now
  merges this entire response, not two fields, so a page that loaded mid-cooldown actually updates once the
  deferred fetch settles instead of being stuck on its first label forever.
- A second, independent bug surfaced only by live timing, not by any unit test (fakes don't model Redis TTL
  expiry): `FETCH_RESULT_TTL_SECONDS` was 5 seconds — sized only for ADR 0015's single-flight join window —
  far shorter than any realistic poll interval, so a poll landing even slightly late after a job actually
  completed still found its result already expired and fell back to reporting `"deferred"` again. Bumped to 60
  seconds, comfortably outlasting a poll interval with margin.

**Considered:** reverting to silence (matching the original spec text exactly) instead of adding a visible
`"deferred"` status (rejected, by explicit preference once both were seen working) — true silence was the
originally specified behavior, but showing a calm, honest "a check is already scheduled" reads as more
trustworthy than a page that simply never explains why nothing happened, for a state (rate-limit deferral)
that's now a routine, expected part of normal operation rather than a rare edge case.
