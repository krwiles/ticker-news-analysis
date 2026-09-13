# Lesson 12 plan — testing React components

Scope: `NOTES.md`'s lesson 12, inserted after lesson 11 specifically to resolve ADR 0005's deliberately
deferred frontend testing-tool decision. Tests lesson 11's new code (`SearchBar`, `HeadlineList`, `search.ts`,
`SearchPage`). Not in scope: any new product behavior (that's lessons 13/14).

## Decisions confirmed with the user (2026-09-13)

1. **Vitest + React Testing Library**, not Jest — this project's `tsconfig.json` is already modern-ESM
   (`"module": "ESNext"`, `"moduleResolution": "bundler"`); Vitest needs no separate transform config for this
   (Jest would need `ts-jest`/`babel-jest`). Vitest runs standalone, same relationship to the app as `pytest`
   has to `uvicorn` — `webpack.config.js` is untouched.
2. **Scope extended past `NOTES.md`'s original wording** to cover all four of lesson 11's new files, not just
   `SearchBar`/`HeadlineList` — mirrors lesson 10's two-layer backend shape (pure-logic tests, an HTTP-boundary
   mock, one integration test at the next layer up) rather than testing only the simplest pieces.
3. **Mocking**: a global `fetch` stub (`vi.stubGlobal`), not MSW. MSW is the closer conceptual match to
   `respx` (intercepts at the network layer), but a stub is smaller and sufficient for a first pass — same
   "targeted, not overbuilt" reasoning ADR 0005 used to defer this whole decision in the first place. `search.ts`
   gets the `fetch`-boundary mock (this project's `respx` analogue); `SearchPage` gets a `vi.mock("../search")`
   module mock one layer up (this project's `dependency_overrides` analogue) — worth naming as a real
   contrast: frontend testability comes from swapping an imported *module*, not an injected *parameter*, per
   `[[di-mechanism-follows-two-independent-questions]]`.
4. **Co-located test files** (`Component.test.tsx` beside `Component.tsx`), not a separate `frontend/tests/`
   directory — idiomatic for this ecosystem; the backend's separate directory was really about matching
   `pytest`'s own discovery conventions, which doesn't translate here.

## What gets built

**1. Toolchain** — new `devDependencies`: `vitest`, `jsdom`, `@testing-library/react`,
`@testing-library/jest-dom`, `@testing-library/user-event`. New `frontend/vitest.config.ts`
(`environment: "jsdom"`, `setupFiles`) and `frontend/vitest.setup.ts` (registers `@testing-library/jest-dom`'s
matchers). New `"test": "vitest run"` script. No changes to `webpack.config.js` or `tsconfig.json` — test
files import `describe`/`it`/`expect`/`vi` explicitly from `"vitest"` rather than relying on injected globals,
keeping this addition isolated from the production build config.

**2. `HeadlineList.test.tsx`** — empty-state message when `headlines` is `[]`; a headline's title renders as a
link to its real `url`; outlet renders as `via {outlet}` when present and is absent when `null`; summary
renders when present and is absent when `null`; category renders as plain text (a regression guard against
shipping a styled badge before lesson 14).

**3. `SearchBar.test.tsx`** — renders input + button; typing updates the displayed value
(`@testing-library/user-event`); submitting a non-empty value calls `onSearch` with the trimmed ticker;
submitting empty or whitespace-only input does **not** call `onSearch` (the guard-clause case); `disabled`
disables both controls.

**4. `search.test.ts`** — `fetchSearch` builds the correct URL against a stubbed global `fetch`
(`vi.stubGlobal("fetch", ...)`); a non-ok response throws with the expected message; an ok response returns the
parsed body.

**5. `SearchPage.test.tsx`** — `vi.mock("../search")` replacing `fetchSearch`; initial render shows no
results; submitting shows a loading state, then renders headlines once the mocked promise resolves; a rejected
promise shows the error message, not a crash.

## Verification

1. Install packages, add config, write one throwaway smoke test (`expect(1 + 1).toBe(2)`) — confirms the
   runner itself works before testing anything real.
2. `HeadlineList.test.tsx`, verified case by case, including deliberately breaking one assertion to confirm the
   suite can actually fail (same discipline lesson 10 used).
3. `SearchBar.test.tsx` — first test needing simulated interaction, not just render-and-assert.
4. `search.test.ts` — first test needing a mocked network boundary.
5. `SearchPage.test.tsx` — the integration layer, tying the mocked `search.ts` boundary to real component
   rendering and user interaction together.
6. `npm run test` (full suite) and `npm run typecheck` both clean; confirm the existing production
   `npm run build` still succeeds (test additions shouldn't affect the app bundle at all).

## Open items

None outstanding — all four resolved with the user (see Decisions above).
