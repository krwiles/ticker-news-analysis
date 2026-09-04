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
  const res = await fetch("/health");
  if (!res.ok) {
    throw new Error(`/health responded ${res.status}`);
  }
  return res.json();
}
