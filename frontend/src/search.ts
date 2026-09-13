import { API_BASE_URL } from "./config";

export interface Headline {
  title: string;
  url: string;
  category: "news" | "filing";
  provider: string;
  outlet: string | null;
  summary: string | null;
  published_at: string;
}

export interface SearchResponse {
  ticker: string;
  status: "success" | "partial_failure" | "complete_failure";
  providers: Record<string, string>;
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
