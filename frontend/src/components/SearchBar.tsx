import { useState, type FormEvent } from "react";

interface SearchBarProps {
  onSearch: (ticker: string) => void;
  disabled?: boolean;
  initialValue?: string;
}

export function SearchBar({ onSearch, disabled, initialValue }: SearchBarProps) {
  // signal() -> useState(): an explicit, read/write reactive value. Typing
  // updates `ticker` on every keystroke; nothing else here reacts to it —
  // it's only read when the form submits.
  //
  // `initialValue` only seeds this once, at mount -- it's not a continuous
  // binding the way an Angular @Input() is. SearchPage handles the "URL
  // ticker changed after mount" case by remounting this component (a
  // `key` prop keyed on the ticker) rather than syncing state via an
  // effect -- see react.dev's "Resetting state with a key".
  const [ticker, setTicker] = useState(initialValue ?? "");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); // stop the browser's own full-page-reload form submission
    const trimmed = ticker.trim();
    // Silently refuses to search on empty/whitespace-only input, rather
    // than calling onSearch("") -- deliberate, not a missed edge case:
    // spec 0001 has no ticker-validation requirement, but there's still no
    // reason to fire a request that can only ever come back empty.
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
