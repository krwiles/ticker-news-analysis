# Notes

## Learner background
- Fluent in Angular 21 conventions: standalone components (no NgModules), signals as the default reactivity primitive, the `@if`/`@for` control-flow syntax, zoneless change detection.
- Teach React *against* this, not from zero. Angular 21's signal model is a closer analogy to React than older Angular (RxJS/Zone.js-heavy) would have been — use it.

## Working Angular → React translation table
(Built directly from the React and Angular docs in RESOURCES.md — no single secondary source covers this well, see the Gaps section there.)

| Angular 21 | React | Notes |
|---|---|---|
| Standalone component (`@Component`) | Function component | Neither needs a module system to register itself. |
| `signal()` | `useState()` | Both: explicit read/write reactive value, re-render/recompute on change. |
| `computed()` | `useMemo()` | Derived value, recalculated when a dependency changes. |
| `effect()` | `useEffect()` | Side effect that reruns when a tracked dependency changes. |
| `@Input()` (signal input) | Props | Both are how a parent passes data down; React has no separate decorator, it's just function arguments. |
| Dependency injection (`inject()`, services) | No direct equivalent — plain imports, or Context for cross-tree data | React has no DI container. This is a real gap to call out, not paper over. |
| `@if` / `@for` in templates | Plain JS (`condition && <X/>`, `array.map()`) inside JSX | JSX is just JavaScript — no special template syntax to learn, which is itself the mental shift. |
| Angular Router | React Router | Conceptually similar (route config → component); React Router's declarative mode (`<Routes>`/`<Route>`) is the closest match to Angular's router module, which is what this project uses. |
| RxJS `Observable` (async data) | `useEffect` + `fetch`/`useState`, or a data-fetching library later | This project's `StatusPage` uses the plain hooks version — worth naming as the "manual" approach before any library shows up. |

## Proposed lesson sequence
Ties to the mission in MISSION.md. Reordered (2026-09-04) around the learner's actual goal: understand how the
five services communicate *before* business logic fills in and the structure potentially drifts. Split into two
arcs, with feature-speccing as the hinge between them — build lessons one (or a couple) at a time across
sessions, never all at once.

### Arc 1 — the plumbing (no feature dependency, buildable now)
Every lesson here explains code that already exists and won't change regardless of what business logic shows up
later — no reason to defer any of these.

1. **The multi-mode container pattern** — one image, three roles (`ui`/`api`/`worker`), `APP_MODE`, ADR 0001. Foundational: everything else sits inside this shape. ✅ built
2. **FastAPI basics: serving both the API and the UI** — path operations, routers, and `app.frontend()` (the new SPA helper adopted in `main.py`). ✅ built
3. **The `/health` aggregation endpoint** — applies #2 to a real feature: real checks (`SELECT 1`, Redis `PING`) vs a fake always-true stub, and why the browser calls one endpoint instead of four.
4. **ARQ's cron/heartbeat mechanism** — `worker` mode, `WorkerSettings`, `cron()`, `ctx["redis"]`, and how a process with no HTTP server proves it's alive.
5. **How docker-compose wires the five services together** — networking, healthchecks gating startup order, the `x-app` YAML anchor trick, env vars. Capstone of this arc: by here the learner should be able to read the whole skeleton end to end. *(was #8 — pulled forward: it's pure infra, no feature dependency either.)*

**→ Hinge: after lesson 5, stop and spec some basic features before continuing. Done (2026-09-08).** The
`grill-with-docs` domain-modeling round that got set aside when the walking-skeleton detour started ran to
completion — see `docs/specs/0001-first-feature.md` ("News Search"), `CONTEXT.md` (the `Ticker`/`Provider`/
`Headline` glossary), and `docs/adr/0003-live-fetch-with-shared-persistence-schema.md`. Arc 2 below is now
modeled directly on that spec, not invented placeholders.

### Arc 2 — applying it to a real feature (modeled on `docs/specs/0001-first-feature.md`)
Broken into smaller slices than originally planned (was 3 lessons, now 7) — per-lesson rhythm mirrors arc 1's:
a short concept intro immediately before building that slice, then verify it against the live stack before
moving on. Each lesson should end with something real and pokeable, not just theory. Lesson 9 (testing) was
added after a post-exploration architecture review — see ADR 0004 and ADR 0005.

6. **The `Headline` model + migration** — SQLAlchemy 2.x async ORM mapped onto the entity `CONTEXT.md` already
   defines (ticker, title, url, raw content, `category`, published timestamp; `sentiment` fields nullable for
   now, filled in by spec 0002 later), plus the `dbmate` migration creating the table. Verify by inserting and
   querying a row directly — first real Postgres schema in the project. ✅ built (plan: `docs/plans/0006-*.md`)
7. **The provider-fetch job** — calling SEC EDGAR and Finnhub concurrently (`asyncio.gather`, the direct payoff
   of lesson 3's sequential-vs-concurrent discussion) via `httpx`, normalizing two different response shapes
   into one `Headline` shape, upserting by URL for dedup — written in a flat `providers.py` module and
   registered as an **ARQ job** in `worker`'s `WorkerSettings.functions`, per ADR 0004 (not a plain function
   called directly — deliberately routed through ARQ for hands-on job-enqueue practice). Verify by enqueueing
   it directly (not yet from `/search`) and checking Postgres for real fetched rows. ✅ built (plan:
   `docs/plans/0007-*.md`) — also added a `companies` cache table (CIK lookup) beyond the original plan, and
   found/fixed two real bugs live (EDGAR had no date filter; filing titles were redundant).
8. **The `/api/search` endpoint** — enqueues lesson 7's job and awaits its result (10s timeout, per ADR 0004
   and spec 0001), maps the outcome to the success/partial/complete-failure status model, including the
   job-timeout case. `/health` also moves to `/api/health` here for consistency. Verify with `curl`, same style
   as lesson 2.
9. **Testing the search feature** — `pytest` + `pytest-asyncio`, `httpx`'s test client, `respx` for mocking
   EDGAR/Finnhub, a dedicated `ticker_test` database (ADR 0005). Unit tests for the Eastern-time/DST today-vs-
   recent boundary and the dedup/CHECK-constraint behavior; an integration test for `/api/search` end to end
   with mocked providers; failure-path tests (partial, complete, job-timeout). Verify by watching a test fail
   when you deliberately break the logic it covers, then pass again once fixed — proof the test is meaningful,
   not just green by accident.
10. **React fundamentals, from Angular** — components, JSX, hooks (`useState`/`useEffect`) mapped via the
    translation table above, built against the search bar + a first pass at rendering results from lesson 8's
    endpoint.
11. **React Router + how the UI actually works** — the data-loading pattern, router setup in `App.tsx`, tying
    back to lesson 3's `/health` endpoint and lesson 8's new endpoint from the frontend side.
12. **Today/Recent, category badges, and the Refresh button** — the UI polish that makes the feature match the
    spec end to end: two recency lists, a badge per entry, a manual re-fetch, and the success/partial/failure
    status display. Capstone of arc 2 — after this, spec 0001 is fully built, not just modeled.

## Preferences
- Wants an example data table created once the spec round produces a real entity to model it on (lesson 6 above), not before — don't front-load schema/domain work into earlier lessons. Satisfied: spec 0001 + `CONTEXT.md` now exist, arc 2 is modeled on them.
- Confirmed (2026-09-08): prefers small vertical slices over front-loaded theory or a build-everything-then-explain approach — a short concept intro right before building each slice, then verify it against the live stack, then move to the next slice. This is why arc 2 became 6 (now 7) lessons instead of 3.
- Confirmed (2026-09-09): wants to genuinely learn testing as its own discipline, not skip it as out-of-scope for a personal project — pushed back twice now (also on routing the fetch through an ARQ job rather than calling it directly) when a leaner option would have skipped real learning value. When a scope decision trades stack/skill learning against build speed, weight learning higher, but keep it bounded (targeted tests for this feature, not retrofitting old code — see ADR 0005) rather than open-ended.
