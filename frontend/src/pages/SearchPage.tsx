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
    setLoading(true);
    setError(null);
    try {
      const result = await fetchSearch(ticker);
      setResults(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "unknown error");
      setResults(null);
    } finally {
      setLoading(false);
    }
  }

  // The data-loading pattern: the URL itself drives what loads, not just a
  // button click. Visiting /search?ticker=AAPL directly fetches with zero
  // manual interaction -- this project's declarative-mode answer to what
  // an Angular resolver does.
  //
  // Deliberately passed through as-is, not uppercased here -- the backend
  // already normalizes case (search.py's `ticker.upper()`), so a lowercase
  // URL ticker still resolves correctly without this component needing to
  // duplicate that normalization on the read path.
  useEffect(() => {
    if (urlTicker) {
      runSearch(urlTicker);
    }
  }, [urlTicker]);

  // Event-driven (form submit): normalizes once, writes the URL, and lets
  // the effect above pick up the resulting param change and do the actual
  // fetch -- one single fetch-triggering path, not two copies of it.
  function handleSearch(ticker: string) {
    setSearchParams({ ticker: ticker.toUpperCase() });
  }

  // Refresh bypasses the URL entirely and calls runSearch directly -- the
  // reason it needs its own trigger at all: resubmitting the *same*
  // ticker via the search bar wouldn't change the URL, so it wouldn't
  // re-fire the effect above. See lesson 13, and spec 0001's own words:
  // Refresh "just calls the exact same GET /api/search again for the
  // currently-shown ticker."
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
