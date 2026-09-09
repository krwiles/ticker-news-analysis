# The provider fetch runs as an ARQ job, not a direct function call — search enqueues and awaits it

Status: accepted — supersedes `0003-live-fetch-with-shared-persistence-schema.md`

`0003` proposed a plain, reusable function that `/search` would call directly in-process, with a future
scheduled watchlist job calling the same function later. Revisited because this project's actual purpose is
learning the stack (see `MISSION.md`), and a direct function call would mean this feature never exercises
ARQ's core job-enqueue mechanism at all — only the pre-existing heartbeat *cron* touches ARQ, which is a
different, narrower pattern (scheduled, no external trigger vs. triggered-and-awaited).

Decision: the fetch/normalize/persist logic is registered as an ARQ job function in `worker`'s
`WorkerSettings.functions`. `/search` triggers it by enqueueing the job and awaiting its result (with a
timeout), rather than importing and calling the function directly. The fetch only ever executes inside
`worker` — never inside `api`. When the future scheduled watchlist feature arrives, it triggers the identical
job function via `cron_jobs` instead of an enqueue-and-await call. One job function, two different triggers,
always run by the worker — a tighter version of `0003`'s "one function, two callers" intent, not a departure
from it.

## Considered options

- **Direct function call from `/search`** (0003's original proposal): simplest, lowest latency — no job-queue
  round trip. Rejected on revisit because it leaves ARQ's actual job-enqueue pattern completely untouched by
  this feature, which works against this project's explicit purpose.
- **ARQ job, enqueued and awaited by `/search`** (chosen): `/search` calls `redis.enqueue_job(...)`, then waits
  on the job's result via ARQ's result-polling API, with a timeout. Gives real, hands-on practice with the
  `functions` list and job dispatch — the core ARQ pattern this stack was chosen to teach — at the cost of
  dispatch latency and the added complexity of an RPC-style wait-for-a-job-result flow.

## Consequences

- `/search`'s response time now includes ARQ's job-pickup polling delay on top of the fetch itself — a
  deliberate trade of a small, real latency cost for learning value, not an oversight.
- A job that never gets picked up (worker down, or the job exceeds its timeout) is a new failure mode `/search`
  must handle explicitly, distinct from a provider call failing — both need to resolve to the existing
  success/partial/complete-failure status model in spec 0001, not silently hang the request.
- The provider-fetch code (`providers.py`, per the flat-module decision) stays framework-agnostic either way —
  it's the *caller* (`/search` enqueuing vs. a future cron trigger) that changed, not the fetch logic itself.
