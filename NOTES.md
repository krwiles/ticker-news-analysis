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
Broken into smaller slices than originally planned (was 3 lessons, now 8) — per-lesson rhythm mirrors arc 1's:
a short concept intro immediately before building that slice, then verify it against the live stack before
moving on. Each lesson should end with something real and pokeable, not just theory. Lesson 10 (testing) was
added after a post-exploration architecture review — see ADR 0004 and ADR 0005. Lesson 8 (async/await
fundamentals) was added after lesson 7, once a real teaching gap surfaced.

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
8. **Async/await fundamentals, Python and TypeScript side by side** — inserted after lesson 7 (2026-09-10):
   `async`/`await` has been load-bearing since lesson 2 (every FastAPI route, `asyncio.gather` in lesson 7,
   `AsyncSession`, `httpx.AsyncClient`) with no dedicated lesson on *why* it's shaped the way it is — a real
   gap, caught late rather than not at all. Coroutines vs. calling a function (`async def` does nothing until
   `await`ed), the event loop (single-threaded, cooperative — not real parallelism), I/O-bound vs. CPU-bound
   (lesson 7's `asyncio.gather` as the concrete already-built example of where this genuinely helps; async does
   *nothing* for CPU-bound work), why `await` is contagious up the call stack. Taught against JS `Promise`/
   `async function` (already known from Angular/TypeScript) rather than from zero, same translation-table
   instinct as React — including the one real divergence worth naming: Python's GIL is part of *why*
   `asyncio` exists (a cheap alternative to OS threads for I/O-bound work), where JS's single-threaded model
   has no GIL story at all. Ends with a concrete "when not to reach for async" checklist. ✅ built.
9. **The `/api/search` endpoint** — enqueues lesson 7's job and awaits its result (10s timeout, per ADR 0004
   and spec 0001), maps the outcome to the success/partial/complete-failure status model, including the
   job-timeout case. `/health` also moves to `/api/health` here for consistency. Verify with `curl`, same style
   as lesson 2. ✅ built (plan: `docs/plans/0009-*.md`) — real bug found live: a plain default parameter
   (`session_factory=async_session_factory`, fine in `providers.py`) crashes every request as a FastAPI route
   parameter, since FastAPI introspects those; needed `Depends()` instead. Verified the worker-down case for
   real (stopped the container) — graceful fallback to existing Postgres data confirmed, not just assumed.
10. **Testing the search feature** — `pytest` + `pytest-asyncio`, `httpx`'s test client, `respx` for mocking
    EDGAR/Finnhub, a dedicated `ticker_test` database (ADR 0005). Unit tests for the Eastern-time/DST today-vs-
    recent boundary and the dedup/CHECK-constraint behavior; an integration test for `/api/search` end to end
    with mocked providers; failure-path tests (partial, complete, job-timeout). Verify by watching a test fail
    when you deliberately break the logic it covers, then pass again once fixed — proof the test is meaningful,
    not just green by accident. ✅ built (plan: `docs/plans/0010-*.md`) — 17 tests, all passing. Real platform
    gap found: `greenlet` (needed by SQLAlchemy's async engine) has a dependency marker that lists Linux's
    `aarch64` but not macOS's own `arm64`, so it silently didn't install on this Mac; fixed by declaring it
    directly. Also found: a session-scoped async engine fixture breaks across pytest-asyncio's per-test event
    loops (fixed: function-scoped instead); a test fixture forgot the real `headlines` FK needs a `companies`
    row first. Best finding: a DST test named for what it claimed to prove didn't actually prove it (both
    interpretations landed on the same date) — caught by deliberately breaking it and watching it *not* fail,
    then strengthened to a pair that genuinely distinguishes EST from EDT.
11. **React fundamentals, from Angular** — components, JSX, hooks (`useState`/`useEffect`) mapped via the
    translation table above, built against the search bar + a first pass at rendering results from lesson 9's
    endpoint: one combined list (today+recent merged, category shown as plain text — the real split and
    styled badges wait for lesson 14), mounted on a new `/search` route added now but not yet explained —
    lesson 13 is where routing itself becomes the lesson. (plan: `docs/plans/0011-*.md`)
12. **Testing React components** — inserted after lesson 11 (2026-09-11), mirroring how lessons 8 and 10 got
    added mid-arc once a real teaching gap surfaced rather than being pre-planned: ADR 0005 deliberately
    deferred the frontend testing-tool decision to exactly this point ("when the React lessons actually
    begin") rather than deciding it in the abstract. Resolved: **Vitest + React Testing Library** (matches
    this project's already-modern-ESM `tsconfig`, no separate transform config needed, unlike Jest). Tests all
    four of lesson 11's new files — `SearchBar`, `HeadlineList`, `search.ts`'s `fetchSearch`, and `SearchPage`
    — deliberately extending past `NOTES.md`'s original narrower wording to mirror lesson 10's two-layer shape
    (pure-component tests + an HTTP-boundary mock + one integration test one layer up). Mocking: global `fetch`
    stub, not MSW (smaller footprint for a first pass — same "targeted, not overbuilt" reasoning ADR 0005 used
    to defer this whole decision). Test files co-located (`Component.test.tsx` beside `Component.tsx`), not a
    separate `frontend/tests/` directory. (plan: `docs/plans/0012-*.md`)
13. **React Router + how the UI actually works** — two real, previously-missing pieces: (1) a `Layout`
    component (nav + `<Outlet />`, React Router's near-literal translation of Angular's `<router-outlet>`)
    wrapping both routes so `/` and `/search` are actually navigable via `<Link>`, not just reachable by typing
    a URL; (2) `useSearchParams` makes the URL the real source of truth for "what's being searched" — the
    data-loading pattern named in this lesson's original scope, and this project's declarative-mode answer to
    what Angular resolvers do. Submitting a search writes `?ticker=` to the URL (uppercased — canonical form);
    visiting `/search?ticker=AAPL` (or any case — the backend already normalizes, see `search.py`) directly
    auto-fetches with zero manual interaction. Sets up lesson 14's Refresh button for free: "the currently-shown
    ticker" (spec 0001's own phrase) is just `searchParams.get("ticker")`. (plan: `docs/plans/0013-*.md`)
14. **Today/Recent, category badges, and the Refresh button** — the UI polish that makes the feature match the
    spec end to end: two recency lists (stops merging `today`/`recent` into one), a real `CategoryBadge`
    component (blue News / purple Filing, replacing plain text), a `SearchStatus` component showing all three
    states — including `success` ("All sources responded.") shown deliberately, not just the failure cases, so
    a user actually knows fresh data was fetched — and a Refresh button that calls the existing `runSearch`
    directly (lesson 13 built this hook point on purpose). Both new components are extracted, not inline, same
    reasoning `StatusTile` was: a small enum-to-(color,label) mapping worth testing in isolation. Capstone of
    arc 2 — after this, spec 0001 is fully built, not just modeled. ✅ built (plan: `docs/plans/0014-*.md`) —
    38 tests passing, all green. Arc 2 is complete.

### Arc 3 — infra/deployment (opened 2026-09-14, following a tech-stack audit)

With spec 0001 fully built, a tech-stack audit compared what's actually been used against the original stack
list (`MISSION.md`'s and the `nvidia-vulnops-portfolio-stack` project memory's). Genuinely learned: everything
in arcs 1–2. Still unused: Kubernetes/OpenShift/ArgoCD, Vault, Milvus, GitHub Actions, Kaizen UI (deferred, not
dropped — see the memory's "Next steps, brainstormed" section for the full reasoning and feature ideas per
item). GitHub Actions was picked as the lowest-effort, most-ready candidate: both test suites already exist and
pass, no new secrets/services beyond what CI itself needs to stand up.

15. **Continuous integration with GitHub Actions** — wires up the existing 17 backend + 38 frontend tests (no
    new tests written for this lesson — the point is reproducing what already passes locally, in CI) plus a
    Docker build validation, into one `.github/workflows/ci.yml` with three independent jobs
    (`frontend-tests`, `backend-tests`, `docker-build`), all running on every push/PR. No secrets needed —
    verified, not assumed: every backend test mocks provider calls via `respx`. Postgres service container
    pinned to `postgres:17-alpine` and Node to `24`, both matching what `docker-compose.yml`/`Dockerfile`
    already use, rather than arbitrary different versions. `dbmate` pinned to `2.35.1` (the locally-verified
    version — no version pin existed anywhere in-repo before this). Deliberately out of scope: linting (no
    linter exists on either side yet — a separate decision), a live end-to-end smoke test (the existing mocked
    suites are the real regression coverage for this pass). ✅ built (plan: `docs/plans/0015-*.md`) — pushed
    and watched run for real (`gh`/`act` weren't available locally, so verification meant polling the GitHub
    API directly): all three jobs green on the first real run, no fixes needed. One real design issue found
    and fixed *while building*, before ever pushing: a job-level `working-directory` default didn't compose
    safely with a per-step override needed for `dbmate` — resolved by removing the job-level default and
    setting it explicitly per step instead of guessing at GitHub Actions' composition rules.

### Arc 4 — Daily Story Grouping (spec 0002), rough outline

Opened 2026-09-15, once `docs/specs/0002-daily-story-grouping.md` was finalized via a full grilling round (see
that file, and `CONTEXT.md`'s new `Story` entry). This is a rough sketch, not yet per-lesson planned — same
starting shape arc 2 had ("was 3 lessons, now 8") before real per-lesson planning reshaped it. Sequenced the
same way arc 2 was: infra/schema before business logic, business logic before the endpoint, endpoint before
UI — not because that order is mandatory, just because it's the shape that's worked every time so far.

16. **Milvus, standalone** — docker-compose wiring (`etcd` + `MinIO` sidecars, the real standalone shape,
    chosen deliberately over Milvus Lite for scalability exposure, see ADR 0008), a real
    collection, basic insert/search via `pymilvus` — no app logic yet. Walking-skeleton style, same as how
    lesson 1 proved the container architecture before lesson 6 put a real table in Postgres. ✅ built (plan:
    `docs/plans/0016-*.md`) — two real bugs found live: (1) the fetched reference config itself was broken —
    MinIO pulled `minio/minio` from Docker Hub entirely this week; fixed via `quay.io/minio/minio`, same tag,
    cross-checked against Milvus' own maintainers hitting the identical issue; (2) a healthy `milvus` container
    still returned zero search results after a real insert — `insert()` doesn't make data searchable until
    explicitly `flush()`ed, confirmed via `get_collection_stats()` (`row_count` stayed 0 until flushed). Second
    finding flagged explicitly for lesson 19: a new Story's primary embedding needs to be flushed somewhere in
    the real matching flow, not just in a throwaway script. `worker`'s `depends_on` deliberately not shared via
    the `&app` anchor like `db`/`redis` are — Milvus' 90s healthcheck `start_period` would otherwise slow down
    `api`/`ui` startup for a dependency they'll never use; verified live that `api`/`ui` start without waiting
    on it while `worker` does.
17. **The `stories` table + migration** — `SQLAlchemy` model + `dbmate` migration for `stories` and
    `headlines.story_id`. Mirrors lesson 6's shape exactly: schema first, no matching logic wired to it yet.
    ✅ built (plan: `docs/plans/0017-*.md`) — `story_id` shipped **nullable**, a deliberate deviation from ADR
    0009's eventual `NOT NULL` design, tightened once lesson 19's real matching logic can populate it on every
    path (same staged-rollout pattern `outlet`/`summary` used). Built with a circular-FK back-pointer
    (`stories.primary_headline_id`) first, then **simplified under review before shipping**: a Story's primary
    is always its earliest-published member — a pure function of already-stored data — so storing it a second
    time (a back-pointer, or the `headlines.is_primary` flag considered next) was redundant state for no real
    benefit. Final shape: `stories(id, ticker)` only, primary derived via `ORDER BY published_at ASC LIMIT 1`
    against a `(story_id, published_at)` index — no circular FK anywhere. See ADR 0009's revised Considered
    options for the full comparison. Two real findings along the way: `conftest.py`'s `TRUNCATE` fixture didn't
    know about the new table (Postgres refuses to truncate a referenced table without the referencing table in
    the same statement — fixed by adding `stories` to it), and the "zero blast radius" claim for the nullable
    column was only half true because of that. 18/18 tests passing (the one new test proves the derivation
    works even when headlines are inserted out of chronological order), full stack sanity check clean.
18. **OpenAI embeddings integration** — a new provider-style call in `providers.py` (same shape as EDGAR/
    Finnhub), get real embeddings for real headline text, verify live. No Milvus wiring yet — just proves the
    API call works. ✅ built (plan: `docs/plans/0018-*.md`) — `get_embeddings()` + `embedding_input_text()`
    added to `providers.py` per ADR 0010's raw-httpx shape, `openai_api_key` wired into `config.py` and
    `docker-compose.yml`'s shared `&app-env`. Two decisions closed during planning: model
    (`text-embedding-3-small`) and input-text join format (`title` alone, or `title\n\nsummary` when present).
    **Revised after the first live call**: a single isolated embedding measured 2.23s, which projects to ~18s
    for a realistic 10-headline search — well past `job_timeout_seconds`'s 10s budget on embeddings alone.
    Replaced the original one-call-per-headline `get_embedding()` with a batched `get_embeddings(texts, client)`
    using OpenAI's native array `input` support, placing each vector by its own `index` field rather than
    trusting response order. Live-verified: 10 headlines in one batched call took 1.13s — flat against batch
    size, not linear. ADR 0007 and ADR 0010 both updated in place to record this (same precedent as ADR 0009's
    revision in lesson 17). 23/23 tests passing, zero regressions. `fetch_and_persist_headlines` and Milvus
    itself both still untouched, as scoped — lesson 19 wires this in, now knowing embeddings should be fetched
    once per run for every new headline that run found, not one call per headline.
19. **The actual grouping logic** — combines 16–18 inside the existing `fetch_and_persist_headlines` job:
    oldest-to-newest processing of only new headlines, threshold search against Milvus, `story_id` assignment.
    ✅ built (plan: `docs/plans/0019-*.md`, design: ADR 0011) — the new-vs-known gap flagged during lesson 18's
    planning closed via `INSERT ... ON CONFLICT ... RETURNING (xmax = 0)` (verified live against a real
    session before trusting it), not a pre-query. `story_primaries` Milvus collection: one vector per Story
    (the founding member's, permanent), cosine metric, threshold 0.75 empirically measured against six real
    headline pairs — the recurring-quarterly-report pair scored *highest* of all (0.943), direct live proof
    that ADR 0006's day-scoping is load-bearing, not theoretical. News-matching gates on `OPENAI_API_KEY` being
    configured (graceful degradation, not a test hack) — closed the real regression this caused in the existing
    suite before it shipped. `run_in_executor` finally closed, three lessons after first flagged (8, 16, 18).
    Three real bugs found live, not anticipated in planning: an unflushed insert invisible to the very next
    search; the fix (explicit `flush()`) working but too slow at real scale (249 new headlines took 20s+),
    replaced with `consistency_level="Strong"` (same correctness, 3.86s for the same data); and a search
    result's primary-key field assumed to be named `"id"` when it's actually named after the schema
    (`story_id`) — caught by printing a raw result rather than guessing twice. Full containerized sanity check:
    real `/api/search?ticker=MSFT`, 3.57s, 188/188 new news headlines correctly grouped, zero worker errors.
20. **Backend tests for grouping** — mocking OpenAI and Milvus at their boundaries, same `respx`-style
    discipline as `test_providers.py`. Mirrors lesson 10's shape. **One specific case to include, confirmed
    live during lesson 19's follow-up**: a "late match" test — a headline should still correctly match an
    existing Story's primary many iterations after that Story was created, not just on the very next search.
    Verified manually against real Milvus with `consistency_level="Strong"` (20 genuinely distinct intervening
    Stories, the original still matched correctly 20 inserts later) — this needs a real, committed regression
    test, not just the throwaway script that checked it this once.
    **Two decisions made during this lesson's planning, recorded in ADR 0012, both to be built before the rest
    of this lesson's test suite**: (1) the Milvus client becomes an injectable parameter on
    `_match_or_create_story`/`_assign_stories`/`ensure_story_primaries_collection` (mirrors the
    `session_factory`/`client` pattern already used everywhere else), tested against a hand-rolled in-memory
    fake with a real cosine-similarity `search()`, not canned responses — this refactor must be done first, in
    isolation, and re-verified against lesson 19's own live-verification scripts before any new tests get
    written. (2) News-matching now degrades gracefully on *both* "OpenAI not configured" and "OpenAI configured
    but transiently failing" (previously only the first case was graceful) — headlines always persist either
    way, and the distinction is preserved via a new `grouping` status (`"ok"`/`"skipped"`/`"error"`) that flows
    from `_assign_stories` through `fetch_and_persist_headlines`'s result into `/api/search`'s JSON response,
    independent of the existing `status` field. Lesson 21's `/api/search` reshaping must preserve this field,
    not drop it. The same "is my dependency configured and currently working" signal is flagged in ADR 0007 as
    something a future sentiment-analysis spec should reuse, not re-derive.
    ✅ built (plan: `docs/plans/0020-*.md`) — the Milvus DI refactor landed first, in isolation, re-verified
    against all three of lesson 19's live-verification scripts before any test code was written. A late gap the
    plan hadn't anticipated: `fetch_and_persist_headlines` itself also needed a `milvus` parameter (not just
    `_assign_stories`) for the permanence test to work at all — found only once test-writing demanded it. All
    three `grouping` outcomes (`"ok"`, `"skipped"`, `"error"` against a real OpenAI 401) verified live before
    being written up as mocked tests. `_FakeMilvusClient` computes real cosine similarity, not canned
    responses — its result shape doubles as a live regression test for lesson 19's "id" vs "story_id" bug.
    10 new tests, 33/33 total. Verification per lesson 10's precedent: deliberately broke the threshold check,
    confirmed exactly the two match-dependent tests failed, reverted.
21. **`/api/search` reshaped for N days** — replaces the `today`/`recent` two-array response with something
    that represents an arbitrary number of days, each holding Stories. Must preserve the `grouping` status
    field lesson 20/ADR 0012 adds to the response, not drop it while reshaping everything else.
    ✅ built (plan: `docs/plans/0021-*.md`, design: ADR 0013) — two decisions made during planning, both
    accepted deliberately rather than deferred: the response shape is replaced outright, not rolled out
    additively (breaks the current frontend until lesson 22 — accepted, not guarded against), and only Today
    is always emitted; earlier days appear only when they actually have a Story (no rigid 7-day scaffold of
    mostly-empty buckets). `split_today_recent` replaced by `_group_into_stories` + `build_daily_view` in
    `search.py`, both pure functions in the same "`now` passed in explicitly" style as the function they
    replaced — every existing DST/Eastern-boundary test ported into the new shape, not dropped. One real gap
    caught only by planning ahead of code, not live: a `story_id=None` headline (grouping skipped/errored,
    ADR 0012) must become its own singleton Story rather than merging with every other null-story headline —
    a naive `groupby(story_id)` would have silently collapsed them all into one fake Story, exactly the failure
    mode ADR 0012's graceful degradation exists to prevent. Caught a second real gap only while writing the
    integration test: `headlines.story_id` has a live FK constraint into `stories` (not previously exercised
    by a test using a bare `uuid4()`) — fixed by seeding real `Story` rows first, not by weakening the test.
    38/38 tests passing (5 new). Live-verified against the real running stack (rebuilt `api`/`worker`): a real
    `/api/search?ticker=AAPL` returned 8 day-buckets (today empty, 7 populated), several genuinely multi-member
    Stories (one with 4 other members), zero worker/api errors.
22. **Frontend: per-day lists + the `Story` component** — replaces `SearchPage`'s Today/Recent sections with
    one per day; a `Story` shows its primary headline per spec 0001's existing rules, plus an expandable list
    for other members when there are any. Capstone of this arc, same role lesson 14 played for arc 2.
    ✅ built (plan discussed inline in conversation, design decisions below) — two decisions made before any
    code: display `grouping` status underneath the existing `SearchStatus` (a new `GroupingStatus` component,
    same dot+message shape, distinguishing all four states — `ok`/`skipped`/`error`/`unknown` — per ADR 0012's
    own forward-looking note about future UI messaging); and delete `HeadlineList` entirely rather than keep
    it as an unused wrapper, since `Story` renders `other_members` directly via a newly-extracted
    `HeadlineCard`. New components: `HeadlineCard` (one headline, shared by a Story's primary and its
    members), `Story` (primary + a native `<details>` disclosure for other members, no local state needed),
    `DaySection` (one day's heading + its Stories), `GroupingStatus`. A real bug caught and fixed before it
    shipped, not left as a gotcha: `day.date` is a plain `"YYYY-MM-DD"` string, and `new Date("2026-09-16")`
    parses as UTC midnight — formatting that with `toLocaleDateString()` renders as the *previous* day in any
    timezone west of UTC, Eastern included. Fixed by parsing the string's components manually and using the
    local-time `Date` constructor instead, with a dedicated regression test. Unlike arc 2's lesson 11/12 split,
    this lesson's own tests were written inline as part of the same change (13 new: `HeadlineCard`, `Story`,
    `DaySection`, `GroupingStatus`, plus rewritten `SearchPage`/`search.ts` fixtures) rather than deferred to a
    separate lesson — 51/51 frontend tests passing, `tsc --noEmit` clean. Live-verified only partially: the
    `ui` container was rebuilt and confirmed serving (200, correct title, clean startup logs), but no browser-
    automation tool was available in this session to actually click through the rendered page — flagged
    explicitly rather than assumed, with a manual check in a real browser recommended before calling this
    fully done. This also completes lesson 23 as originally sketched below (a separate frontend-tests lesson);
    that slot is superseded, not left as stale future work — same "arcs get reshaped once real per-lesson work
    happens" precedent this file already states at its close.
23. ~~**Frontend tests for the new Story UI**~~ — superseded: lesson 22 above wrote its own tests inline
    rather than as a separate follow-up lesson.

**Post-lesson-22 investigation: the 0.75 similarity threshold, re-examined.** Using the real UI, a genuine
same-event split was spotted live (five MSFT dividend headlines split into two Stories over a 0.7247-vs-0.75
miss). Rather than retune to that one case, ran an independent, larger experiment against real data across
four tickers (33 headlines, 31 same-event pairs, 6 deliberately hard different-event pairs) — see ADR 0011's
new section for full methodology and numbers. Result: the two distributions genuinely overlap (no threshold
gets perfect separation), and 0.75 already sits in the best available zero-false-positive position this
sample supports. Threshold left unchanged, but now re-confirmed against real, independently-built evidence
rather than left untouched by default. The MSFT split itself is accepted as a real, now-quantified limitation
of the primary-only/single-threshold design, not fixed.

Not committed to this exact split or order — the real per-lesson plans (once each one actually gets planned)
may reshape it, same as arc 2's did.

### Arc 5 — Headline Sentiment Analysis (spec 0005), rough outline

Opened 2026-09-17, once `docs/specs/0005-headline-sentiment-analysis.md` was finalized via a full grilling
round and its technical approach recorded in `docs/adr/0014-sentiment-analysis-technical-approach.md`. Rough
sketch, not yet per-lesson planned — same starting shape arcs 2 and 4 had before real per-lesson planning
reshaped them. Sequenced the same way: infra/schema before business logic, business logic before the
endpoint, endpoint before UI.

23. **Migration: sentiment columns** — nullable columns on `headlines` (score, the enum derived from it,
    gloss, rationale, status) and a running average + member count on `stories` (ADR 0014's incremental
    aggregate, and exactly what ADR 0009 speculated `stories` might eventually need). Schema-only, no app
    logic wired yet — mirrors lesson 6/17's shape.
24. **OpenAI sentiment classification call** — a new provider-style call (mirrors lesson 18's embeddings
    integration): given a headline's title + `summary`, get back a score/gloss/rationale via a raw HTTP chat
    completion call (ADR 0010's raw-httpx discipline, not an SDK); enum derived from the score by one
    consistent rule. No filing content, no job wiring, no Story aggregate yet — just proves the call works,
    same scope discipline lesson 18 kept for embeddings. **Two things ADR 0014 flagged as needing
    re-verification at this point, not assumed from the ADR**: the model choice (`gpt-5-nano` was cheapest
    when checked, but pricing already moved once during that same discussion) and the actual score-to-enum
    threshold cutoffs (not yet chosen anywhere — same empirical-tuning treatment lesson 19 gave
    `story_similarity_threshold`, not a guessed number).
25. **Filing content extraction** — the three-tier strategy from ADR 0014 (structural anchor extraction by
    matching the anchor `id`, not visible label text; plain-text heading search fallback; blind
    head-truncation fallback), as a standalone content-preparation step given a raw filing URL. Substantial,
    real-world HTML-parsing work — deserves its own lesson, mirroring lesson 19's dedicated treatment of "the
    actual grouping logic." The content-size caps (filings ~20k tokens, news ~500 — both explicitly working
    values in ADR 0014) get reconfirmed against a broader real sample here, not treated as final.
26. **The actual sentiment job** — wires 23-25 together inside a new background job, separate from
    `fetch_and_persist_headlines` per ADR 0014's job-architecture decision (not the same synchronous job
    grouping uses): selects input per Headline (news vs. filing, using lesson 25's extraction for filings),
    applies the right content cap, calls lesson 24's classifier, persists results + status to `headlines`,
    and incrementally updates the owning Story's running average via the cumulative-moving-average formula
    (including the first-member special case — no prior average to update from).
27. **Backend tests for the sentiment job** — mirrors lesson 20's dedicated testing lesson. Mocking OpenAI at
    its boundary; the three-tier extraction fallback tested against fixtures modeling the three real cases
    ADR 0014 found live (anchor present, anchor present but label-mismatched, no anchor and content
    incorporated by reference elsewhere); the incremental average update including the first-member edge
    case; all three `sentiment_status` outcomes (`ok`/`skipped`/`error`).
28. **`/api/search` reshaped again** — response gains per-Headline sentiment fields and each Story's
    aggregate; must stay pollable as the *same* shape (per ADR 0014's chosen "poll the full response" design,
    not a new lightweight status endpoint) — mirrors lesson 21's shape.
29. **Frontend: sentiment UI + polling** — `SearchPage` gains a poll loop (mirrors `StatusPage`'s existing
    pattern); `HeadlineCard` gains the sentiment pill (gloss + score together, colored by enum, greyed-out
    while pending, rationale as small text beneath); `Story` gains the nested outer card (its own "Story"
    pill + aggregate pill) for multi-member Stories only — the primary Headline inside it gets zero special
    treatment. Capstone of this arc, same role lesson 22 played for arc 4.

Not committed to this exact split or order — the real per-lesson plans (once each one actually gets planned)
may reshape it, same as arcs 2 and 4's did.

## Preferences
- Wants an example data table created once the spec round produces a real entity to model it on (lesson 6 above), not before — don't front-load schema/domain work into earlier lessons. Satisfied: spec 0001 + `CONTEXT.md` now exist, arc 2 is modeled on them.
- Confirmed (2026-09-08): prefers small vertical slices over front-loaded theory or a build-everything-then-explain approach — a short concept intro right before building each slice, then verify it against the live stack, then move to the next slice. This is why arc 2 became 6 (now 7) lessons instead of 3.
- Confirmed (2026-09-09): wants to genuinely learn testing as its own discipline, not skip it as out-of-scope for a personal project — pushed back twice now (also on routing the fetch through an ARQ job rather than calling it directly) when a leaner option would have skipped real learning value. When a scope decision trades stack/skill learning against build speed, weight learning higher, but keep it bounded (targeted tests for this feature, not retrofitting old code — see ADR 0005) rather than open-ended.
