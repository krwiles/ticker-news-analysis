import type { SearchResponse } from "../search";

interface SearchStatusProps {
  status: SearchResponse["status"];
}

// success gets a message too, deliberately -- not just the two failure
// states. Knowing the latest news actually got fetched is worth surfacing
// on its own, per spec 0001's "surface a simple success/partial-failure/
// complete-failure status" (all three, not just the bad ones).
const MESSAGE: Record<SearchResponse["status"], string> = {
  success: "All sources responded.",
  partial_failure: "Some results may be missing — one source didn't respond.",
  complete_failure: "Couldn't fetch new results right now — showing previously saved data.",
};

// Same dot-plus-label shape as StatusTile.tsx, kept as its own component
// (not reused) since the domain is genuinely different -- a search
// result's status, not a service-health check.
const DOT_COLOR: Record<SearchResponse["status"], string> = {
  success: "bg-emerald-500",
  partial_failure: "bg-amber-500",
  complete_failure: "bg-red-500",
};

export function SearchStatus({ status }: SearchStatusProps) {
  return (
    <p className="flex items-center gap-2 text-sm text-slate-600">
      <span className={`h-2 w-2 shrink-0 rounded-full ${DOT_COLOR[status]}`} />
      {MESSAGE[status]}
    </p>
  );
}
