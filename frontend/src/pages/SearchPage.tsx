import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { HeadlineList } from "../components/HeadlineList";
import { SearchBar } from "../components/SearchBar";
import { SearchStatus } from "../components/SearchStatus";
import { fetchSearch, type SearchResponse } from "../search";

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
          <div className="mb-4 flex items-center justify-between gap-3">
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

          <section className="mb-8">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Today</h2>
            <HeadlineList headlines={results.today} emptyMessage="No headlines today." />
          </section>

          <section>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Recent</h2>
            <HeadlineList headlines={results.recent} emptyMessage="No other headlines in the past week." />
          </section>
        </div>
      )}
    </main>
  );
}
