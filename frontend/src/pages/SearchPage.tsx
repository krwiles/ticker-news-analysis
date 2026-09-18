import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { DaySection } from "../components/DaySection";
import { GroupingStatus } from "../components/GroupingStatus";
import { SearchBar } from "../components/SearchBar";
import { SearchStatus } from "../components/SearchStatus";
import { SentimentStatus } from "../components/SentimentStatus";
import { fetchSearch, fetchSearchStatus, hasPendingSentiment, type SearchResponse } from "../search";

// Same cadence as StatusPage's own health poll -- no evidence sentiment resolves
// meaningfully faster or slower than a health check, so no reason to invent a
// different number without one (lesson 29 planning).
const SENTIMENT_POLL_INTERVAL_MS = 5000;

export function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  // Polls /api/search/status (never re-enqueues the fetch job -- see search.py's
  // search_status route) while any Headline still hasn't had a real sentiment
  // attempt, and stops on its own once every one of them has. Deliberately keyed
  // on the whole `results` object, not narrowed fields: any fresh fetch --
  // the initial search, a poll tick, or a manual Refresh -- produces a new object,
  // so the effect re-evaluates from scratch every time. That's what makes a
  // Refresh reliably restart polling even when it lands back on the same overall
  // status (e.g. "error" both before and after) -- a narrower dependency list
  // wouldn't have noticed anything changed. No immediate first tick (unlike
  // StatusPage): results here are always already fresh, so firing again at t=0
  // would just re-fetch the same data.
  useEffect(() => {
    if (!results || !hasPendingSentiment(results.days)) {
      return;
    }

    let cancelled = false;
    const ticker = results.ticker;

    async function poll() {
      try {
        const status = await fetchSearchStatus(ticker);
        // Merge only sentiment + days -- /api/search/status doesn't return
        // ticker/status/providers/grouping, so a full replace would drop them.
        if (!cancelled) {
          setResults((prev) => (prev ? { ...prev, sentiment: status.sentiment, days: status.days } : prev));
        }
      } catch {
        // A transient poll failure shouldn't blow away results already on screen -- just try again next tick.
      }
    }

    const id = setInterval(poll, SENTIMENT_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [results]);

  // Writes the URL; the effect above reacts to that change and does the actual fetch.
  function handleSearch(ticker: string) {
    setSearchParams({ ticker: ticker.toUpperCase() });
  }

  // Bypasses the URL and calls runSearch directly -- resubmitting the same ticker wouldn't
  // change the URL, so the effect above wouldn't re-fire on its own.
  function handleRefresh() {
    if (urlTicker) {
      runSearch(urlTicker);
    }
  }

  return (
    <main className="mx-auto max-w-md px-6 py-16">
      <h1 className="text-2xl font-semibold text-slate-900">Search</h1>
      <p className="mt-1 text-sm text-slate-500">News and filings from the past week, by ticker.</p>

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
          Non-goals rule out stale-then-fresh loading for v1. This applies
          identically whether it's the first search or a Refresh. */}
      {loading && <p className="mt-6 text-sm text-slate-500">Searching…</p>}
      {error && <p className="mt-6 text-sm text-red-600">Couldn&apos;t reach the API: {error}</p>}

      {results && !loading && (
        <div className="mt-6">
          <div className="mb-1 flex items-center justify-between gap-3">
            <SearchStatus status={results.status} />
            <button
              type="button"
              onClick={handleRefresh}
              disabled={loading}
              className="shrink-0 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-50"
            >
              Refresh
            </button>
          </div>
          <div className="mb-1">
            <GroupingStatus grouping={results.grouping} />
          </div>
          <div className="mb-4">
            <SentimentStatus sentiment={results.sentiment} />
          </div>

          {results.days.map((day) => (
            <DaySection key={day.date} day={day} />
          ))}
        </div>
      )}
    </main>
  );
}
