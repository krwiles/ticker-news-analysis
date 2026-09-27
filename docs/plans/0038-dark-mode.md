# Dark mode

Not a planned lesson, no spec/ADR — a small, self-contained UI feature (same reasoning as lessons 30/32/33's
own "not a lesson" plans: user-facing but not architecturally significant enough to warrant either doc).
Scoped and decided via a `/grill-me` round; this plan records those decisions and the concrete file-by-file
change list.

## Decisions from grilling

1. **Two-state toggle (light/dark), not three-state.** No "system" option that tracks the OS live — on a
   brand-new visitor's first-ever load, before any explicit choice exists, default to their OS preference
   (`prefers-color-scheme`); after that, whatever they explicitly pick is remembered and wins.
2. **Storage: `localStorage` only, for now — architected so account-sync can layer on later without a
   rewrite.** The user wants this to eventually follow a signed-in user across devices, but that needs a
   backend field/endpoint that doesn't exist yet. Per this project's standing discipline against pre-building
   schema ahead of an actual feature (spec 0006's own account-linking deferral, the "don't front-load
   schema/domain work" preference), **no `users` column is added now** — the only preparation is putting the
   read/write behind one small module (`theme.ts`) so a future account-synced version only changes what's
   inside that module, not every call site.
3. **Full pass, not base-only.** Every component with hardcoded light-mode colors gets a `dark:` variant — a
   half-dark app (dark shell, still-light badges) reads as broken, not scoped down.
4. **Toggle control: a hand-rolled inline SVG icon button, no new dependency.** A state toggle, not a nav
   link, so it shouldn't blend into the `Status`/`Search` text links.
5. **Placement: immediately left of `AuthControls`** in `Layout`'s nav — site chrome, grouped with but
   visually distinct from the identity control next to it.
6. **The nav widens to `max-w-2xl`** (currently `max-w-md`) to match `SearchPage`'s own card width.
7. **`StatusPage` widens to `max-w-2xl` too** (currently `max-w-md`), so the nav isn't wider than the content
   directly beneath it on that page. `SearchPage` stays as it is — it was already deliberately widened for its
   cards (lesson 30's follow-up).

## Architecture

**Class-based dark mode**, not Tailwind v4's default media-query-only variant. The project's `index.css` is
currently just `@import "tailwindcss";` with no config file (CSS-first Tailwind v4, per `RESOURCES.md`) — by
default `dark:` only ever responds to the OS. Adding one line switches it to class-based, which a manual
toggle needs:

```css
@import "tailwindcss";
@custom-variant dark (&:where(.dark, .dark *));
```

With that in place, every `dark:` utility anywhere in the app now activates when a `dark` class is present on
`<html>` (or any ancestor), not from `prefers-color-scheme` directly.

**New `frontend/src/theme.ts`** — the one place that knows about storage, isolating the future account-sync
extension point (decision 2):

```ts
export type Theme = "light" | "dark";
const STORAGE_KEY = "theme";

export function getInitialTheme(): Theme {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "light" || stored === "dark") return stored;
  } catch {
    // localStorage can throw (private browsing, disabled storage) -- fall through to OS preference.
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function setTheme(theme: Theme): void {
  document.documentElement.classList.toggle("dark", theme === "dark");
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Best-effort persistence -- the theme still applies for this page view even if storage fails.
  }
}
```

**`index.tsx`** calls `setTheme(getInitialTheme())` once, before the first render, so the correct class is on
`<html>` before React ever paints — no flash of the wrong theme.

**New `frontend/src/components/ThemeToggle.tsx`** — owns its own `useState<Theme>(getInitialTheme())`; on
click, computes the opposite theme, calls `setTheme(next)`, and updates its own state (no context needed, one
consumer). Renders a moon icon while light (click to go dark) or a sun icon while dark (click to go light),
each an inline `<svg>` — no icon package. `aria-label` names the action ("Switch to dark mode" / "Switch to
light mode"), not the icon.

## Color mapping convention

Applied consistently across every file below. Solid, saturated status dots (`bg-emerald-500` /
`bg-amber-500` / `bg-red-500` / `bg-slate-400`) are **left unchanged** — a 500-shade dot already has enough
contrast against both a white and a dark-slate background, so touching them would be effort with no visible
benefit.

| Light | Dark | Used for |
|---|---|---|
| `bg-white` | `dark:bg-slate-950` | page background (`Layout`'s outer wrapper) |
| `bg-white` | `dark:bg-slate-900` | card backgrounds (`StatusTile`, `MilvusStatus`, `HeadlineCard`, `SearchBar`'s input, the Refresh button) |
| `bg-slate-50` / `bg-slate-50/50` | `dark:bg-slate-800` / `dark:bg-slate-800/50` | nested sub-cards (`HeadlineCard`'s sentiment box, `Story`'s multi-member wrapper) |
| `bg-slate-100` (chip) | `dark:bg-slate-800` | plain slate chips (`Story`'s "Story" label, `SentimentPill`'s neutral/pending) |
| `border-slate-200` | `dark:border-slate-800` | card borders |
| `border-slate-100` | `dark:border-slate-700` | nested borders (`HeadlineCard`'s sentiment box, `Story`'s member-list divider) |
| `text-slate-900` | `dark:text-slate-100` | headings, primary text, link text |
| `text-slate-700` | `dark:text-slate-300` | secondary text (names, labels) |
| `text-slate-600` | `dark:text-slate-400` | body/status text |
| `text-slate-500` | `dark:text-slate-400` | muted/detail text |
| `text-slate-400` | `dark:text-slate-500` | least-prominent text (pending pill) |
| `bg-{color}-100 text-{color}-700` (badges: blue/purple/emerald/red) | `dark:bg-{color}-900/30 dark:text-{color}-300` | `CategoryBadge`, `SentimentPill`'s resolved colors |
| `bg-slate-900 text-white` (primary button) | `dark:bg-slate-100 dark:text-slate-900` | Search button — inverted, not just darkened, so it stays the visually prominent action on a dark page |

## Files changed

**New:**
- `frontend/src/theme.ts` — as above.
- `frontend/src/theme.test.ts` — `getInitialTheme`/`setTheme` unit tests.
- `frontend/src/components/ThemeToggle.tsx` — as above.
- `frontend/src/components/ThemeToggle.test.tsx`.

**Changed:**
- `frontend/src/index.css` — the `@custom-variant dark` line.
- `frontend/src/index.tsx` — calls `setTheme(getInitialTheme())` before `createRoot(...).render(...)`.
- `frontend/src/components/Layout.tsx` — outer wrapper gets `min-h-screen bg-white text-slate-900
  dark:bg-slate-950 dark:text-slate-100`; nav widens `max-w-md` → `max-w-2xl`; nav link text/hover get dark
  variants; mounts `<ThemeToggle />` between the nav links and `<AuthControls />`.
- `frontend/src/pages/StatusPage.tsx` — widens `max-w-md` → `max-w-2xl`; heading/subtitle/error text get dark
  variants.
- `frontend/src/pages/SearchPage.tsx` — heading/subtitle/loading/error text get dark variants; the Refresh
  button gets dark variants per the mapping table.
- `frontend/src/components/StatusTile.tsx`, `MilvusStatus.tsx`, `SearchStatus.tsx`, `GroupingStatus.tsx`,
  `SentimentStatus.tsx` — card/text colors per the mapping table (the three status-line components share the
  same `text-slate-600` body-text treatment).
- `frontend/src/components/CategoryBadge.tsx`, `SentimentPill.tsx` — badge colors per the mapping table's
  `bg-{color}-100` row.
- `frontend/src/components/HeadlineCard.tsx` — card, nested sentiment sub-card, and all text per the mapping
  table.
- `frontend/src/components/Story.tsx` — multi-member wrapper, "Story" chip, disclosure `<summary>` text, and
  member-list divider per the mapping table.
- `frontend/src/components/DaySection.tsx` — heading and empty-state text per the mapping table.
- `frontend/src/components/SearchBar.tsx` — input and Search button per the mapping table (button uses the
  inverted-primary-button row).
- `frontend/src/components/AuthControls.tsx` — name text and sign-out button per the mapping table.

**Untouched:** `frontend/src/health.ts`, `search.ts`, `auth.ts`, `config.ts` — no visual code, nothing to
change. Backend — this is a frontend-only feature.

## Tests

`theme.test.ts` (mirrors this project's existing fetch-boundary-stub style, stubbing `localStorage` and
`window.matchMedia` instead):
- `getInitialTheme` returns a validly-stored value from `localStorage` without touching `matchMedia`.
- `getInitialTheme` falls back to `matchMedia` when nothing is stored.
- `getInitialTheme` falls back to `matchMedia` when `localStorage.getItem` throws.
- `setTheme("dark")` adds the `dark` class to `document.documentElement`; `setTheme("light")` removes it.
- `setTheme` persists to `localStorage`, and doesn't throw when `localStorage.setItem` throws.

`ThemeToggle.test.tsx` (React Testing Library, same shape as the project's other component tests):
- Renders the moon icon (by `aria-label`, "Switch to dark mode") when the initial theme is light.
- Renders the sun icon (`aria-label`, "Switch to light mode") when the initial theme is dark.
- Clicking toggles `document.documentElement`'s `dark` class and flips the rendered icon/label.

No new tests asserting literal Tailwind class strings on the ~13 changed display components — same as this
project's existing tests for those files, which check rendered text/behavior, not raw `className` values. The
full-pass styling itself is verified visually (see Verification below), not through unit tests.

## Verification

1. `npx tsc --noEmit`, `npx vitest run`, `npm run build` — all clean, per this project's standard bar.
2. Rebuild the `ui` container; use `claude-in-chrome` to actually load the app, toggle dark mode, and confirm
   live: the toggle's icon flips, `Layout`/`StatusPage`/`SearchPage` all render with dark colors (not a
   half-dark page), a reload preserves the choice, and the nav/`StatusPage` are now visibly the same width as
   `SearchPage`'s cards. Screenshot both modes.
3. Confirm existing search/auth flows are visually unaffected in light mode (regression check, not just
   passing tests).

## Not in scope

- Account-synced theme preference — the real future work decision 2 is preparing for, not building. When
  picked up, it means a new nullable column, a way to read/write it from `/api/auth/me`-adjacent routes, and
  a decision about precedence when a signed-in user has both a `localStorage` value and an account value that
  disagree. None of that is designed here.
- `lessons/`'s own teaching stylesheet (`assets/lesson.css`) — unrelated, already has its own
  `prefers-color-scheme` dark mode, not part of this app.
- Kaizen UI (a separate Phase 1 roadmap item) — not blocking or blocked by this.

## What actually happened during execution

Built as planned, with one real gap found during verification, not in the design: **jsdom implements no
`matchMedia` at all**, and `ThemeToggle` calls it on every mount via `getInitialTheme()` — this crashed
`App.test.tsx` (which mounts `Layout`, and therefore `ThemeToggle`, without its own stub). Fixed with a safe
"light" default in `vitest.setup.ts` (`window.matchMedia ??= ...`), the shared place RTL's own cleanup already
lives — tests that care about the OS preference specifically still override it per-test with `vi.stubGlobal`,
unaffected.

TDD followed for the two new modules: `theme.test.ts` written and confirmed failing (module didn't exist)
before `theme.ts`; same for `ThemeToggle.test.tsx`/`ThemeToggle.tsx`. The ~13 remaining display-component
changes (the full-pass color mapping) were applied directly rather than test-first, per the plan's own
"Tests" section — this project's existing tests for those files check rendered text/behavior, not literal
Tailwind class strings, so there was no meaningful failing assertion to write first for a color addition; the
real verification for those is visual, not unit-level.

100/100 frontend tests (12 new: 8 `theme.ts`, 4 `ThemeToggle`), zero regressions. `tsc --noEmit` and
`npm run build` both clean.

**No browser automation was available at first** (`claude-in-chrome`'s browser tools weren't enabled) —
verified in the meantime, more directly than usual: inspected the actual compiled bundle running in the
rebuilt `ui` container and confirmed `.dark\:bg-slate-950:where(.dark, .dark *) { background-color: ... }` is
really present (proof the `@custom-variant dark` directive compiled to a class-based selector, not a media
query, exactly as designed) and that `ThemeToggle`'s "Switch to dark mode"/"Switch to light mode" labels are
in the shipped JS.

**Real browser click-through completed once browser tools were enabled** (`/chrome`): loaded the real app,
found it already in dark mode on first visit (confirming the OS-preference fallback actually works — this
Mac's own dark mode is on), toggled to light and back on both `StatusPage` and `SearchPage`, and searched a
real ticker (AAPL) to check the full-pass styling against real data — multiple `News` badges and resolved
`SentimentPill`s (`bullish`/`concerning`/`speculative`/`contrarian` at various scores) all rendered correctly
themed in both modes, no half-dark artifacts. Reloaded the page and confirmed the choice persisted with no
flash of the wrong theme (the `setTheme(getInitialTheme())` call in `index.tsx`, applied before first paint,
working as designed).
