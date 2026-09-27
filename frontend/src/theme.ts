// The one place that knows about theme storage (docs/plans/0038-*.md) -- localStorage only for now,
// isolated here so a future account-synced version only changes what's inside these two functions.

export type Theme = "light" | "dark";
const STORAGE_KEY = "theme";

// Reads the remembered choice, or falls back to the OS preference on a first-ever visit.
export function getInitialTheme(): Theme {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "light" || stored === "dark") {
      return stored;
    }
  } catch {
    // localStorage can throw (private browsing, disabled storage) -- fall through to OS preference.
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

// Applies the theme to the real DOM (the class Tailwind's dark: variant keys off, index.css) and
// best-effort persists it -- a storage failure shouldn't stop the theme from applying to this page.
export function setTheme(theme: Theme): void {
  document.documentElement.classList.toggle("dark", theme === "dark");
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Best-effort only -- see above.
  }
}
