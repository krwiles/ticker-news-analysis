import { useState, type FormEvent } from "react";

interface SearchBarProps {
  onSearch: (ticker: string) => void;
  disabled?: boolean;
}

export function SearchBar({ onSearch, disabled }: SearchBarProps) {
  // signal() -> useState(): an explicit, read/write reactive value. Typing
  // updates `ticker` on every keystroke; nothing else here reacts to it —
  // it's only read when the form submits.
  const [ticker, setTicker] = useState("");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = ticker.trim();
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
