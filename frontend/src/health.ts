import { API_BASE_URL } from "./config";

// "unknown" means the check couldn't even run (e.g. Redis down) -- see health.py's check_worker.
export type CheckStatus = "ok" | "stale" | "error" | "unknown";

export interface Check {
  status: CheckStatus;
  detail?: string; // human-readable context for a non-ok status, e.g. an exception message
  age_seconds?: number; // worker only -- how long ago its last heartbeat was written
}

// Milvus has a genuine third real state ("not_initialized" -- reachable, collection not created
// yet) that isn't an error, so it gets its own type instead of stretching CheckStatus (spec 0003).
export type MilvusCheck =
  | { status: "ok"; vector_count: number }
  | { status: "not_initialized" }
  | { status: "error"; detail: string }
  | { status: "unknown" };

// One entry per container/service /api/health actually checks -- see
// health.py's health() for the aggregate this mirrors field-for-field.
export interface HealthResponse {
  api: Check;
  db: Check;
  redis: Check;
  worker: Check;
  milvus: MilvusCheck;
}

export async function fetchHealth(): Promise<HealthResponse> {
  // Genuinely cross-origin -- ui serves this page, api serves the aggregate check (ADR 0002).
  const res = await fetch(`${API_BASE_URL}/api/health`);
  // Treat any non-2xx as a failure the caller can catch, rather than
  // returning a body that doesn't match HealthResponse's shape.
  if (!res.ok) {
    throw new Error(`/api/health responded ${res.status}`);
  }
  return res.json();
}
