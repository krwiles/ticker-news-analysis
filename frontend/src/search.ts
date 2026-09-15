import { API_BASE_URL } from "./config";

// Mirrors search.py's _headline_to_dict field-for-field -- kept in sync by
// hand, same trade-off models.py's own docstring names for the
// dbmate/SQLAlchemy split (no shared schema generates both sides).
export interface Headline {
  title: string;
  url: string;
  category: "news" | "filing"; // filings never have an outlet/summary -- EDGAR is the source itself
  provider: string; // which integration fetched this ("finnhub" | "sec_edgar") -- not who wrote it, see outlet
  outlet: string | null; // the original publisher (e.g. "Yahoo"); null when the provider doesn't report one
  summary: string | null; // a free blurb some providers hand back directly; null otherwise
  published_at: string; // ISO 8601, already the right instant -- no client-side timezone math needed to display it
}

export interface SearchResponse {
  ticker: string;
  // success: every provider responded. partial_failure: at least one
  // didn't, but some results still came back. complete_failure: nothing
  // new was fetched (see SearchStatus.tsx for how each renders).
  status: "success" | "partial_failure" | "complete_failure";
  providers: Record<string, string>; // e.g. {"edgar": "ok", "finnhub": "error"} -- per-provider detail behind the one overall `status`
  // Never overlapping -- a headline appears in exactly one of these two,
  // already split server-side by US-Eastern calendar day (search.py's
  // split_today_recent). Not re-derived here on purpose.
  today: Headline[];
  recent: Headline[];
}

export async function fetchSearch(ticker: string): Promise<SearchResponse> {
  // Same cross-origin shape as health.ts's fetchHealth — the api container's
  // CORS config (main.py) already allows this origin in; nothing new to set
  // up for this endpoint specifically. See docs/adr/0002.
  const res = await fetch(`${API_BASE_URL}/api/search?ticker=${encodeURIComponent(ticker)}`);
  if (!res.ok) {
    throw new Error(`/api/search responded ${res.status}`);
  }
  return res.json();
}
