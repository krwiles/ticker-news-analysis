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

**→ Hinge: after lesson 5, stop and spec some basic features before continuing.** This is the `grill-with-docs`
domain-modeling round that got set aside when the walking-skeleton detour started — not a new process, the same
one, picked back up. What comes out of it (ticker scope, news sources, what "analysis" produces, the first real
entities) is what arc 2 below gets modeled after, rather than inventing placeholder examples now.

### Arc 2 — applying it to a real feature (wait for the spec above; do not build ahead of it)
6. **FastAPI + SQLAlchemy + a real table** *(was #5)* — the table is whatever the spec round produces as the first real entity, not an invented placeholder (learner flagged this explicitly). Model + endpoint, seen round-tripping through Postgres.
7. **React fundamentals, from Angular** *(was #6)* — components, JSX, hooks (`useState`/`useEffect`) mapped via the translation table above, taught against whatever real component the spec's first feature actually needs.
8. **React Router + how the UI actually works** *(was #7)* — the polling/data-loading pattern, the router setup in `App.tsx`, tying back to lesson 3's `/health` endpoint and lesson 6's new endpoint from the frontend side.

## Preferences
- Wants an example data table created once the spec round produces a real entity to model it on (lesson 6 above), not before — don't front-load schema/domain work into earlier lessons.
