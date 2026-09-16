import { useState, type FormEvent } from "react";

interface SearchBarProps {
  onSearch: (ticker: string) => void;
  disabled?: boolean;
  initialValue?: string;
}

export function SearchBar({ onSearch, disabled, initialValue }: SearchBarProps) {
  // useState = Angular's signal(). initialValue only seeds this once at mount, not a
  // continuous @Input() binding -- SearchPage remounts via a key prop to reset it instead.
  const [ticker, setTicker] = useState(initialValue ?? "");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); // stop the browser's own full-page-reload form submission
    const trimmed = ticker.trim();
    // Silently ignores empty/whitespace input -- deliberate, no reason to fire a request that'd come back empty.
    if (trimmed) {
      onSearch(trimmed);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <input
        type="text"
        value={ticker}
        onChange={(event) => setTicker(event.target.value)}
        placeholder="Ticker symbol (e.g. AAPL)"
        disabled={disabled}
        className="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-slate-900 shadow-sm focus:border-slate-400 focus:outline-none disabled:opacity-50"
      />
      <button
        type="submit"
        disabled={disabled}
        className="rounded-lg bg-slate-900 px-4 py-2 font-medium text-white shadow-sm disabled:opacity-50"
      >
        Search
      </button>
    </form>
  );
}
