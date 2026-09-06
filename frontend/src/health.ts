import { API_BASE_URL } from "./config";

export type CheckStatus = "ok" | "stale" | "error" | "unknown";

export interface Check {
  status: CheckStatus;
  detail?: string;
  age_seconds?: number;
}

export interface HealthResponse {
  api: Check;
  db: Check;
  redis: Check;
  worker: Check;
}

export async function fetchHealth(): Promise<HealthResponse> {
  // Genuinely cross-origin: this page is served by the ui container, the
  // aggregate health check lives only on the api container. See
  // docs/adr/0002-cors-over-shared-health-router.md.
  const res = await fetch(`${API_BASE_URL}/health`);
  if (!res.ok) {
    throw new Error(`/health responded ${res.status}`);
  }
  return res.json();
}
