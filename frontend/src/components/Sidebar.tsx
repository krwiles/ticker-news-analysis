import { Link } from "react-router";
import type { WatchlistEntry } from "../watchlist";

interface SidebarProps {
  entries: WatchlistEntry[];
  onRemove: (ticker: string) => void;
}

// Purely presentational -- Layout owns the state and polling (ADR 0019), and doesn't mount
// this at all while signed out (spec 0008).
export function Sidebar({ entries, onRemove }: SidebarProps) {
  // An empty watchlist renders nothing, same as being signed out (spec 0008).
  if (entries.length === 0) {
    return null;
  }

  return (
    <nav aria-label="Watchlist" className="w-48 shrink-0 border-r border-slate-200 px-4 py-6 dark:border-slate-800">
      <ul className="space-y-1">
        {entries.map((entry) => (
          <li key={entry.ticker} className="flex items-center justify-between gap-2">
            <Link
              to={`/search?ticker=${entry.ticker}`}
              className="flex-1 truncate text-sm font-medium text-slate-700 hover:text-slate-900 dark:text-slate-300 dark:hover:text-slate-100"
            >
              {entry.ticker}
              {entry.new_headlines > 0 && (
                <span className="ml-1.5 text-xs text-slate-500 dark:text-slate-400">{entry.new_headlines}</span>
              )}
            </Link>
            <button
              onClick={() => onRemove(entry.ticker)}
              aria-label={`Remove ${entry.ticker} from watchlist`}
              className="text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300"
            >
              ×
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
