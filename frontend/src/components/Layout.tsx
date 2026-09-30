import { useEffect, useState } from "react";
import { Link, Outlet } from "react-router";
import { fetchMe, type AuthUser } from "../auth";
import { addToWatchlist, fetchWatchlist, removeFromWatchlist, type WatchlistEntry } from "../watchlist";
import { AuthControls } from "./AuthControls";
import { Sidebar } from "./Sidebar";
import { ThemeToggle } from "./ThemeToggle";

// Slower than SearchPage's own poll -- checks up to 10 tickers at once and is an ambient
// indicator, not something actively focused on (ADR 0019).
const WATCHLIST_POLL_INTERVAL_MS = 20000;

// Read by SearchPage via useOutletContext<WatchlistOutletContext>() -- one shared copy keeps
// the sidebar and the search page's own add/remove button instantly in sync (ADR 0019).
export interface WatchlistOutletContext {
  isSignedIn: boolean;
  entries: WatchlistEntry[];
  add: (ticker: string) => Promise<void>;
  remove: (ticker: string) => Promise<void>;
}

// <Outlet /> is React Router's near-literal translation of Angular's
// <router-outlet> -- "render whichever child route matched here."
export function Layout() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authLoaded, setAuthLoaded] = useState(false);
  const [entries, setEntries] = useState<WatchlistEntry[]>([]);
  const isSignedIn = user !== null;

  // Establishes initial signed-in/signed-out state -- the cookie is HttpOnly, so a real
  // request is the only way to know (spec 0006). Lifted here from AuthControls (ADR 0019).
  useEffect(() => {
    let cancelled = false;
    fetchMe()
      .then((res) => {
        // ?? null, not res.user directly -- an unexpected shape must never read as signed-in
        // (caught live: it otherwise slips past `user !== null` and polls the watchlist).
        if (!cancelled) setUser(res.user ?? null);
      })
      .catch(() => {
        // A failed check is treated the same as signed-out, never a broken page (spec 0006).
        if (!cancelled) setUser(null);
      })
      .finally(() => {
        if (!cancelled) setAuthLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // The watchlist sidebar (spec 0008): fetches once on sign-in, then polls while visible,
  // pausing/resuming like SearchPage's own live-refresh effect (spec 0007). Clears on sign-out.
  useEffect(() => {
    if (!isSignedIn) {
      setEntries([]);
      return;
    }

    let cancelled = false;

    async function refresh() {
      try {
        const res = await fetchWatchlist();
        if (!cancelled) setEntries(res.entries);
      } catch {
        // Silent, matching spec 0007's discipline -- a failed check changes nothing visible.
      }
    }

    let intervalId: ReturnType<typeof setInterval> | undefined;

    function startPolling() {
      if (intervalId === undefined) {
        intervalId = setInterval(refresh, WATCHLIST_POLL_INTERVAL_MS);
      }
    }

    function stopPolling() {
      if (intervalId !== undefined) {
        clearInterval(intervalId);
        intervalId = undefined;
      }
    }

    function handleVisibilityChange() {
      if (document.visibilityState === "visible") {
        refresh();
        startPolling();
      } else {
        stopPolling();
      }
    }

    refresh();
    if (document.visibilityState === "visible") {
      startPolling();
    }
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      cancelled = true;
      stopPolling();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [isSignedIn]);

  async function refreshWatchlist() {
    try {
      const res = await fetchWatchlist();
      setEntries(res.entries);
    } catch {
      // Silent -- the previous list stays showing rather than disappearing on a blip.
    }
  }

  async function add(ticker: string) {
    await addToWatchlist(ticker);
    await refreshWatchlist();
  }

  async function remove(ticker: string) {
    await removeFromWatchlist(ticker);
    await refreshWatchlist();
  }

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
          {/* Nothing renders until the initial check resolves -- avoids a signed-out flash. */}
          {authLoaded && <AuthControls user={user} onSignedIn={setUser} onSignedOut={() => setUser(null)} />}
        </div>
      </nav>
      <div className="flex">
        {/* Hidden entirely when signed out (spec 0008) -- Sidebar also renders nothing when empty. */}
        {isSignedIn && <Sidebar entries={entries} onRemove={remove} />}
        <div className="flex-1">
          <Outlet context={{ isSignedIn, entries, add, remove } satisfies WatchlistOutletContext} />
        </div>
      </div>
    </div>
  );
}
