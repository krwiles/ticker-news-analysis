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

// One real-world event's coverage -- primary renders in full, other_members
// (if any) sit behind an expandable list. story_id is null when grouping
// was skipped or failed (ADR 0012) -- still its own Story, never dropped.
export interface Story {
  story_id: string | null;
  primary: Headline;
  other_members: Headline[];
}

// One calendar day (Eastern), holding that day's Stories. Only Today is ever
// empty -- earlier days are included only when they have at least one Story (ADR 0013).
export interface DayGroup {
  date: string; // "YYYY-MM-DD", Eastern calendar date -- no time component
  is_today: boolean;
  stories: Story[];
}

export interface SearchResponse {
  ticker: string;
  // success: all providers ok. partial_failure: some didn't. complete_failure: nothing new fetched.
  status: "success" | "partial_failure" | "complete_failure";
  providers: Record<string, string>; // e.g. {"edgar": "ok", "finnhub": "error"} -- per-provider detail behind the one overall `status`
  // Independent of `status` -- a grouping problem is a distinct concern from "did EDGAR/Finnhub respond" (ADR 0012).
  // "unknown" means the fetch job itself never returned, so grouping's outcome genuinely can't be known.
  grouping: "ok" | "skipped" | "error" | "unknown";
  // Newest day first; Today always present (even with zero Stories), earlier days only when non-empty.
  days: DayGroup[];
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
