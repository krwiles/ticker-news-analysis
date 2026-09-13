import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { HeadlineList } from "../components/HeadlineList";
import { SearchBar } from "../components/SearchBar";
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
  // button click. Visiting /search?ticker=AAPL directly (a shared link, a
  // bookmark, or the browser's Back/Forward) fetches with zero manual
  // interaction -- this project's declarative-mode answer to what an
  // Angular resolver does (React Router's *data* mode has real loaders;
  // this project uses *declarative* mode, per RESOURCES.md, which doesn't).
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
  //
  // Note: submitting the *same* ticker again doesn't change the URL, so it
  // doesn't re-trigger a fetch -- exactly why spec 0001 needs a dedicated
  // Refresh button (lesson 14) rather than relying on this path for that.
  function handleSearch(ticker: string) {
    setSearchParams({ ticker: ticker.toUpperCase() });
  }

  // Combined list, not Today/Recent -- see HeadlineList's own comment.
  // Lesson 14 replaces this with the real two-list split.
  const headlines = results ? [...results.today, ...results.recent] : [];

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

      {loading && <p className="mt-6 text-sm text-slate-500">Searching…</p>}
      {error && <p className="mt-6 text-sm text-red-600">Couldn&apos;t reach the API: {error}</p>}

      {results && !loading && (
        <div className="mt-6">
          <p className="mb-3 text-sm text-slate-500">
            {results.ticker} — status: {results.status}
          </p>
          <HeadlineList headlines={headlines} />
        </div>
      )}
    </main>
  );
}
