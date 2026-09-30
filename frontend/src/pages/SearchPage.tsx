import { useEffect, useState } from "react";
import { useOutletContext, useSearchParams } from "react-router";
import type { WatchlistOutletContext } from "../components/Layout";
import { DaySection } from "../components/DaySection";
import { GroupingStatus } from "../components/GroupingStatus";
import { RefreshIndicator } from "../components/RefreshIndicator";
import { SearchBar } from "../components/SearchBar";
import { SearchStatus } from "../components/SearchStatus";
import { SentimentStatus } from "../components/SentimentStatus";
import { fetchSearch, fetchSearchStatus, type SearchResponse } from "../search";

// Bumped from 5000 on adding the watchlist sidebar's own 20s poll -- a tuning adjustment,
// not a behavior commitment (ADR 0019).
const STATUS_POLL_INTERVAL_MS = 10000;

export function SearchPage() {
  const { isSignedIn, entries, add, remove } = useOutletContext<WatchlistOutletContext>();
  const [searchParams, setSearchParams] = useSearchParams();
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Timestamp of the last successful check with the backend (initial load counts) -- drives the
  // "last refresh Ns ago" indicator (spec 0007). null before any search has ever succeeded.
  const [lastRefreshAt, setLastRefreshAt] = useState<number | null>(null);

  // The URL is the actual source of truth for "what's being searched" --
  // not a mirror of some separate piece of component state.
  const urlTicker = searchParams.get("ticker");

  async function runSearch(ticker: string) {
    // Reset UI state before the fetch begins.
    setLoading(true);
    setError(null);
    try {
      // Fetch and store the results on success.
      const result = await fetchSearch(ticker);
      setResults(result);
      setLastRefreshAt(Date.now());
    } catch (err) {
      // Store a human-readable error message and drop any stale results.
      setError(err instanceof Error ? err.message : "unknown error");
      setResults(null);
    } finally {
      // Always clear the loading state, whether the fetch succeeded or failed.
      setLoading(false);
    }
  }

  // The URL itself drives what loads -- visiting /search?ticker=AAPL fetches with no click needed.
  // Passed through as-is, not uppercased -- the backend already normalizes case.
  useEffect(() => {
    if (urlTicker) {
      runSearch(urlTicker);
    }
  }, [urlTicker]);

  // Live-refresh (spec 0007): polls /api/search/status whenever results exist, not just while
  // sentiment is pending. Keyed on the ticker alone so each poll's own setResults doesn't restart this.
  useEffect(() => {
    if (!results) {
      return;
    }

    let cancelled = false;
    const ticker = results.ticker;
    // The refocus-immediate-check can overlap a poll already in flight (stopPolling only clears
    // the timer, not an in-flight fetch) -- this discards any response that isn't the latest call.
    let latestRequestId = 0;

    async function poll() {
      const requestId = ++latestRequestId;
      try {
        const status = await fetchSearchStatus(ticker);
        // Merge only sentiment + days -- /api/search/status doesn't return
        // ticker/status/providers/grouping, so a full replace would drop them.
        if (!cancelled && requestId === latestRequestId) {
          setResults((prev) => (prev ? { ...prev, sentiment: status.sentiment, days: status.days } : prev));
          setLastRefreshAt(Date.now());
        }
      } catch {
        // Silent, on purpose (spec 0007) -- a transient failure never changes what's on screen;
        // the next scheduled check tries again as if nothing happened.
      }
    }

    let intervalId: ReturnType<typeof setInterval> | undefined;

    function startPolling() {
      if (intervalId === undefined) {
        intervalId = setInterval(poll, STATUS_POLL_INTERVAL_MS);
      }
    }

    function stopPolling() {
      if (intervalId !== undefined) {
        clearInterval(intervalId);
        intervalId = undefined;
      }
    }

    // Only runs while the tab is actually visible -- refocusing checks immediately rather than
    // waiting for the next tick, so a long-backgrounded tab doesn't look stale for a full interval.
    function handleVisibilityChange() {
      if (document.visibilityState === "visible") {
        poll();
        startPolling();
      } else {
        stopPolling();
      }
    }

    if (document.visibilityState === "visible") {
      startPolling();
    }
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      cancelled = true;
      stopPolling();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [results?.ticker]);

  // Writes the URL; the effect above reacts to that change and does the actual fetch.
  function handleSearch(ticker: string) {
    setSearchParams({ ticker: ticker.toUpperCase() });
  }

  // Sourced from Layout's own shared watchlist state (ADR 0019), not a separate fetch --
  // add/remove mutate that same state, so the sidebar reflects this instantly too.
  const isWatched = results !== null && entries.some((entry) => entry.ticker === results.ticker);

  async function handleWatchlistToggle() {
    if (!results) {
      return;
    }
    if (isWatched) {
      await remove(results.ticker);
    } else {
      await add(results.ticker);
    }
  }

  return (
    <main className="mx-auto max-w-2xl px-6 py-16">
      <h1 className="text-2xl font-semibold text-slate-900 dark:text-slate-100">Search</h1>
      <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">News and filings from the past week, by ticker.</p>

      <div className="mt-8">
        {/* Keyed on the URL ticker: forces a fresh SearchBar (and a fresh
            initialValue) whenever the URL changes to a different ticker --
            e.g. browser Back/Forward -- rather than leaving stale input
            text behind. */}
        <SearchBar
          key={urlTicker ?? ""}
          onSearch={handleSearch}
          disabled={loading}
          initialValue={urlTicker ?? undefined}
        />
      </div>

      {/* Hiding results while loading (rather than showing stale ones
          underneath a spinner) is deliberate, not a gap -- spec 0001's own
          Non-goals rule out stale-then-fresh loading for v1. */}
      {loading && <p className="mt-6 text-sm text-slate-500 dark:text-slate-400">Searching…</p>}
      {error && <p className="mt-6 text-sm text-red-600 dark:text-red-400">Couldn&apos;t reach the API: {error}</p>}

      {results && !loading && (
        <div className="mt-6">
          <div className="mb-1 flex items-center justify-between gap-3">
            <SearchStatus status={results.status} />
            {/* Replaces the old manual Refresh button (spec 0007) -- purely informational, isolated
                into its own component so its once-a-second tick doesn't re-render this whole page. */}
            {lastRefreshAt !== null && <RefreshIndicator lastRefreshAt={lastRefreshAt} />}
          </div>
          <div className="mb-1">
            <GroupingStatus grouping={results.grouping} />
          </div>
          <div className="mb-4">
            <SentimentStatus sentiment={results.sentiment} />
          </div>

          {/* Signed-in only (spec 0008 frames watchlists as a signed-in feature entirely) --
              hidden rather than shown-but-broken for an anonymous visitor. */}
          {isSignedIn && (
            <div className="mb-4">
              <button
                onClick={handleWatchlistToggle}
                className="rounded border border-slate-300 px-2 py-1 text-sm text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                {isWatched ? `Remove ${results.ticker} from watchlist` : `Add ${results.ticker} to watchlist`}
              </button>
            </div>
          )}

          {results.days.map((day) => (
            <DaySection key={day.date} day={day} />
          ))}
        </div>
      )}
    </main>
  );
}
