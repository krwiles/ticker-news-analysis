import { Link, Outlet } from "react-router";
import { AuthControls } from "./AuthControls";

// <Outlet /> is React Router's near-literal translation of Angular's
// <router-outlet> -- "render whichever child route matched here."
export function Layout() {
  return (
    <div>
      <nav className="mx-auto flex max-w-md items-center justify-between gap-4 px-6 pt-6 text-sm font-medium text-slate-600">
        <div className="flex gap-4">
          <Link to="/" className="hover:text-slate-900">
            Status
          </Link>
          <Link to="/search" className="hover:text-slate-900">
            Search
          </Link>
        </div>
        {/* Same place on every route (spec 0006), since Layout wraps every page. */}
        <AuthControls />
      </nav>
      <Outlet />
    </div>
  );
}
