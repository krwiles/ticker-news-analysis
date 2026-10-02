import { API_BASE_URL } from "./config";

// Mirrors watchlist.py's _entry_to_dict field-for-field -- kept in sync by hand, no shared schema.
export interface WatchlistEntry {
  ticker: string;
  added_at: string; // ISO 8601
  new_headlines: number; // headlines published since this entry's last_viewed_at (ADR 0019)
}

export interface WatchlistResponse {
  entries: WatchlistEntry[]; // add-order (oldest first) -- watchlist.py's own ORDER BY
}

// credentials: "include" on every call -- ui/api are different origins (ADR 0002/0016), and
// every endpoint here requires sign-in (require_user, ADR 0019).
export async function fetchWatchlist(): Promise<WatchlistResponse> {
  const res = await fetch(`${API_BASE_URL}/api/watchlist`, { credentials: "include" });
  // Treat any non-2xx as a failure the caller can catch, rather than
  // returning a body that doesn't match WatchlistResponse's shape.
  if (!res.ok) {
    throw new Error(`/api/watchlist responded ${res.status}`);
  }
  return res.json();
}

// Idempotent server-side (ADR 0019) -- calling this for an already-watchlisted ticker
// just returns its current state rather than erroring.
export async function addToWatchlist(ticker: string): Promise<WatchlistEntry> {
  const res = await fetch(`${API_BASE_URL}/api/watchlist`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ticker }),
  });
  // Treat any non-2xx as a failure the caller can catch, rather than
  // returning a body that doesn't match WatchlistEntry's shape.
  if (!res.ok) {
    throw new Error(`/api/watchlist responded ${res.status}`);
  }
  return res.json();
}

// Idempotent server-side -- removing a ticker that isn't watchlisted is not an error.
export async function removeFromWatchlist(ticker: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/watchlist/${encodeURIComponent(ticker)}`, {
    method: "DELETE",
    credentials: "include",
  });
  // Treat any non-2xx as a failure the caller can catch -- this call has no body to mismatch.
  if (!res.ok) {
    throw new Error(`/api/watchlist/${ticker} responded ${res.status}`);
  }
}
