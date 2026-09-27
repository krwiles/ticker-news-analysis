import { Link, Outlet } from "react-router";
import { AuthControls } from "./AuthControls";
import { ThemeToggle } from "./ThemeToggle";

// <Outlet /> is React Router's near-literal translation of Angular's
// <router-outlet> -- "render whichever child route matched here."
export function Layout() {
  return (
    // min-h-screen so the dark background fills the viewport even on a short page,
    // not just as far as the content extends (docs/plans/0038-*.md).
    <div className="min-h-screen bg-white text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <nav className="mx-auto flex max-w-2xl items-center justify-between gap-4 px-6 pt-6 text-sm font-medium text-slate-600 dark:text-slate-400">
        <div className="flex gap-4">
          <Link to="/" className="hover:text-slate-900 dark:hover:text-slate-100">
            Status
          </Link>
          <Link to="/search" className="hover:text-slate-900 dark:hover:text-slate-100">
            Search
          </Link>
        </div>
        {/* Site chrome, grouped with but visually distinct from AuthControls next to it. */}
        <div className="flex items-center gap-3">
          <ThemeToggle />
          {/* Same place on every route (spec 0006), since Layout wraps every page. */}
          <AuthControls />
        </div>
      </nav>
      <Outlet />
    </div>
  );
}
