import { useState } from "react";
import { HeadlineList } from "../components/HeadlineList";
import { SearchBar } from "../components/SearchBar";
import { fetchSearch, type SearchResponse } from "../search";

export function SearchPage() {
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Event-driven, not effect-driven: this runs once, in direct response to
  // a form submit -- unlike StatusPage's useEffect-based polling, which
  // reruns on its own on a timer. Angular terms: closer to a plain method
  // bound to (ngSubmit) than to an effect().
  async function handleSearch(ticker: string) {
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

  // Combined list, not Today/Recent -- see HeadlineList's own comment.
  // Lesson 14 replaces this with the real two-list split.
  const headlines = results ? [...results.today, ...results.recent] : [];

  return (
    <main className="mx-auto max-w-md px-6 py-16">
      <h1 className="text-2xl font-semibold text-slate-900">Search</h1>
      <p className="mt-1 text-sm text-slate-500">News and filings from the past week, by ticker.</p>

      <div className="mt-8">
        <SearchBar onSearch={handleSearch} disabled={loading} />
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
