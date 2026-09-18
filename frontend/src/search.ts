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
  // success: all providers ok. partial_failure: some didn't. complete_failure: nothing new fetched.
  status: "success" | "partial_failure" | "complete_failure";
  providers: Record<string, string>; // e.g. {"edgar": "ok", "finnhub": "error"} -- per-provider detail behind the one overall `status`
  // Independent of `status` -- a grouping problem is a distinct concern from "did EDGAR/Finnhub respond" (ADR 0012).
  // "unknown" means the fetch job itself never returned, so grouping's outcome genuinely can't be known.
  grouping: "ok" | "skipped" | "error" | "unknown";
  sentiment: SentimentStatus;
  // Newest day first; Today always present (even with zero Stories), earlier days only when non-empty.
  days: DayGroup[];
}

// Deliberately narrower than SearchResponse (no ticker/status/providers/grouping -- this endpoint
// only re-reads sentiment state). A poller must merge these keys in, never replace the object.
export interface SearchStatusResponse {
  sentiment: SentimentStatus;
  days: DayGroup[];
}

// True while any Headline still has sentiment_status === null -- the real "more coming" signal, not
// the coarse `sentiment` status (which reports "error" on one failure while others still resolve).
export function hasPendingSentiment(days: DayGroup[]): boolean {
  return days.some((day) =>
    day.stories.some(
      (story) => story.primary.sentiment_status === null || story.other_members.some((h) => h.sentiment_status === null),
    ),
  );
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

// Read-only poll target -- never enqueues fetch_headlines_job or sentiment_job
// (search.py's search_status route structurally can't; see lesson 26).
export async function fetchSearchStatus(ticker: string): Promise<SearchStatusResponse> {
  const res = await fetch(`${API_BASE_URL}/api/search/status?ticker=${encodeURIComponent(ticker)}`);
  // Treat any non-2xx as a failure the caller can catch, rather than
  // returning a body that doesn't match SearchStatusResponse's shape.
  if (!res.ok) {
    throw new Error(`/api/search/status responded ${res.status}`);
  }
  return res.json();
}
