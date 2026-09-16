import { API_BASE_URL } from "./config";

// Mirrors search.py's _headline_to_dict field-for-field -- kept in sync by hand, no shared schema.
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
  // success: all providers ok. partial_failure: some didn't. complete_failure: nothing new fetched.
  status: "success" | "partial_failure" | "complete_failure";
  providers: Record<string, string>; // e.g. {"edgar": "ok", "finnhub": "error"} -- per-provider detail behind the one overall `status`
  // Never overlapping -- already split server-side by Eastern calendar day (search.py's split_today_recent).
  today: Headline[];
  recent: Headline[];
}

export async function fetchSearch(ticker: string): Promise<SearchResponse> {
  // Same cross-origin shape as fetchHealth -- api's CORS config (main.py) already allows this origin.
  const res = await fetch(`${API_BASE_URL}/api/search?ticker=${encodeURIComponent(ticker)}`);
  // Treat any non-2xx as a failure the caller can catch, rather than
  // returning a body that doesn't match SearchResponse's shape.
  if (!res.ok) {
    throw new Error(`/api/search responded ${res.status}`);
  }
  return res.json();
}
