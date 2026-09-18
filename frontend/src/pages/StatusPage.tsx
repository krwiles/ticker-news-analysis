import { useEffect, useState } from "react";
import { MilvusStatus } from "../components/MilvusStatus";
import { StatusTile } from "../components/StatusTile";
import { fetchHealth, type HealthResponse } from "../health";

const POLL_INTERVAL_MS = 5000;

export function StatusPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Effect-driven, on a timer -- polls on its own schedule for as long as the page is mounted.
  useEffect(() => {
    // Guards against a race: if this unmounts mid-poll, its result would otherwise call setState
    // on an unmounted component -- a plain fetch Promise has no built-in cancel, unlike an Observable.
    let cancelled = false;

    async function poll() {
      try {
        // Fetch and store the latest health snapshot on success.
        const result = await fetchHealth();
        if (!cancelled) {
          setHealth(result);
          setError(null);
        }
      } catch (err) {
        // Store a human-readable error message instead of crashing the poll loop.
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "unknown error");
        }
      }
    }

    poll(); // fire once immediately, don't wait POLL_INTERVAL_MS for the first result
    const id = setInterval(poll, POLL_INTERVAL_MS);
    // Cleanup on unmount: stop the timer and flag any still-in-flight poll's result as stale.
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []); // empty deps: subscribe once on mount, not on every render

  return (
    <main className="mx-auto max-w-md px-6 py-16">
      <h1 className="text-2xl font-semibold text-slate-900">Ticker News Analysis</h1>
      <p className="mt-1 text-sm text-slate-500">Walking-skeleton status</p>

      <div className="mt-8 flex flex-col gap-3">
        <StatusTile name="UI" status="ok" detail="You're looking at it" />
        <StatusTile name="API" status={health?.api.status ?? "unknown"} />
        <StatusTile name="Database" status={health?.db.status ?? "unknown"} detail={health?.db.detail} />
        <StatusTile name="Redis" status={health?.redis.status ?? "unknown"} detail={health?.redis.detail} />
        <StatusTile
          name="Worker"
          status={health?.worker.status ?? "unknown"}
          detail={
            health?.worker.detail ??
            (health?.worker.age_seconds !== undefined ? `heartbeat ${health.worker.age_seconds}s ago` : undefined)
          }
        />
        <MilvusStatus milvus={health?.milvus ?? { status: "unknown" }} />
      </div>

      {error && <p className="mt-6 text-sm text-red-600">Couldn&apos;t reach the API: {error}</p>}
    </main>
  );
}
