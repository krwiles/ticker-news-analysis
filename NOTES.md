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
Ties to the mission in MISSION.md. Each lesson builds on the last; build them one (or a couple) at a time across sessions, not all at once.

1. **The multi-mode container pattern** — one image, three roles (`ui`/`api`/`worker`), `APP_MODE`, ADR 0001. Foundational: everything else sits inside this shape.
2. **FastAPI basics: serving both the API and the UI** — path operations, routers, and `app.frontend()` (the new SPA helper we just adopted in `main.py`).
3. **The `/health` aggregation endpoint** — applies #2 to a real feature: real checks (`SELECT 1`, Redis `PING`) vs a fake always-true stub, and why the browser calls one endpoint instead of four.
4. **ARQ's cron/heartbeat mechanism** — `worker` mode, `WorkerSettings`, `cron()`, `ctx["redis"]`, and how a process with no HTTP server proves it's alive.
5. **FastAPI + SQLAlchemy + a real table** — needs an example table to be concrete (learner flagged this explicitly); create one, wire a model + endpoint, see it round-trip through Postgres.
6. **React fundamentals, from Angular** — components, JSX, hooks (`useState`/`useEffect`) mapped via the table above.
7. **React Router + how `StatusPage` actually works** — the polling loop, the router setup in `App.tsx`, tying back to lesson 3's `/health` endpoint from the frontend side.
8. **How docker-compose wires the five services together** — networking, healthchecks gating startup order, the `x-app` YAML anchor trick, env vars. The capstone: by here the learner should be able to read the whole skeleton end to end.

## Preferences
- Wants an example data table created when we reach the database lesson (#5), not before — don't front-load schema/domain work into earlier lessons.
