import { API_BASE_URL } from "./config";

// "unknown" is distinct from "error": it means this check couldn't even
// run (e.g. Redis itself is unreachable, so the worker's heartbeat can't
// be read at all) -- see health.py's check_worker for where each value
// actually gets decided.
export type CheckStatus = "ok" | "stale" | "error" | "unknown";

export interface Check {
  status: CheckStatus;
  detail?: string; // human-readable context for a non-ok status, e.g. an exception message
  age_seconds?: number; // worker only -- how long ago its last heartbeat was written
}

// One entry per container/service /api/health actually checks -- see
// health.py's health() for the aggregate this mirrors field-for-field.
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
  const res = await fetch(`${API_BASE_URL}/api/health`);
  if (!res.ok) {
    throw new Error(`/api/health responded ${res.status}`);
  }
  return res.json();
}
