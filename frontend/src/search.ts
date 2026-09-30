import { API_BASE_URL } from "./config";

// positive/neutral/negative only -- never the page-level sentiment status
// below, a completely different value domain (spec 0005, CONTEXT.md).
export type SentimentEnum = "positive" | "neutral" | "negative";

// Mirrors search.py's _headline_to_dict field-for-field -- kept in sync by hand, no shared schema.
export interface Headline {
  title: string;
  url: string;
  category: "news" | "filing"; // filings never have an outlet/summary -- EDGAR is the source itself
  provider: string; // which integration fetched this ("finnhub" | "sec_edgar") -- not who wrote it, see outlet
  outlet: string | null; // the original publisher (e.g. "Yahoo"); null when the provider doesn't report one
  summary: string | null; // a free blurb some providers hand back directly; null otherwise
  published_at: string; // ISO 8601, already the right instant -- no client-side timezone math needed to display it
  sentiment_score: number | null; // 0-100, null until the fire-and-forget sentiment job resolves this headline
  sentiment_gloss: string | null; // one specific word, e.g. "bullish" -- never just a restatement of the enum
  sentiment_rationale: string | null; // one-sentence explanation of the score, distinct from summary
  sentiment_status: "ok" | "skipped" | "error" | null; // null == not yet attempted this run
  sentiment_enum: SentimentEnum | null; // derived server-side from sentiment_score, never stored
}

// One real-world event's coverage -- primary renders in full, other_members (if any) sit behind
// an expandable list. story_id is null when grouping was skipped/failed (ADR 0012), never dropped.
export interface Story {
  story_id: string | null;
  primary: Headline;
  other_members: Headline[];
  // Average of this Story's members' scores -- null until at least one resolves. Present even
  // for a Story of one, but the UI only surfaces it once other_members is non-empty (CONTEXT.md).
  sentiment_average: number | null;
  sentiment_enum: SentimentEnum | null;
}

// One calendar day (Eastern), holding that day's Stories. Only Today is ever
// empty -- earlier days are included only when they have at least one Story (ADR 0013).
export interface DayGroup {
  date: string; // "YYYY-MM-DD", Eastern calendar date -- no time component
  is_today: boolean;
  stories: Story[];
}

// Page-level status of the fire-and-forget sentiment job -- distinct from Headline/Story's own
// sentiment_enum. "processing" is real here, unlike grouping (always finishes within the request).
export type SentimentStatus = "ok" | "skipped" | "error" | "processing";

export interface SearchResponse {
  ticker: string;
  // success: all providers ok. partial_failure: some didn't. complete_failure: a fetch ran and
  // failed. deferred: rate-limited/cooldown -- nothing went wrong, it'll run later on its own.
  status: "success" | "partial_failure" | "complete_failure" | "deferred";
  providers: Record<string, string>; // e.g. {"edgar": "ok", "finnhub": "error"} -- per-provider detail behind the one overall `status`
  // Independent of `status` -- a grouping problem is a distinct concern from "did EDGAR/Finnhub respond" (ADR 0012).
  // "unknown" means there's no fetch outcome to report yet, so grouping's own outcome can't be known either.
  grouping: "ok" | "skipped" | "error" | "unknown";
  sentiment: SentimentStatus;
  // Newest day first; Today always present (even with zero Stories), earlier days only when non-empty.
  days: DayGroup[];
}

// Same shape as SearchResponse minus ticker -- a poller merges all of these keys in fresh
// each time, never replaces the object (ticker itself is the only thing missing here).
export type SearchStatusResponse = Omit<SearchResponse, "ticker">;


export async function fetchSearch(ticker: string): Promise<SearchResponse> {
  // credentials: "include" (ADR 0019) -- /api/search now optionally records a view for a
  // signed-in caller's own watchlist entry, which needs the session cookie to ride along.
  const res = await fetch(`${API_BASE_URL}/api/search?ticker=${encodeURIComponent(ticker)}`, {
    credentials: "include",
  });
  // Treat any non-2xx as a failure the caller can catch, rather than
  // returning a body that doesn't match SearchResponse's shape.
  if (!res.ok) {
    throw new Error(`/api/search responded ${res.status}`);
  }
  return res.json();
}

// Poll target -- never *awaits* a pending fetch, but can trigger one rate-limited in the
// background and report its outcome once complete (ADR 0018).
export async function fetchSearchStatus(ticker: string): Promise<SearchStatusResponse> {
  const res = await fetch(`${API_BASE_URL}/api/search/status?ticker=${encodeURIComponent(ticker)}`);
  // Treat any non-2xx as a failure the caller can catch, rather than
  // returning a body that doesn't match SearchStatusResponse's shape.
  if (!res.ok) {
    throw new Error(`/api/search/status responded ${res.status}`);
  }
  return res.json();
}
