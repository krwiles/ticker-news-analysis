import type { SearchResponse } from "../search";

interface GroupingStatusProps {
  grouping: SearchResponse["grouping"];
}

// "ok" gets a message too, same reasoning as SearchStatus's own success case.
const MESSAGE: Record<SearchResponse["grouping"], string> = {
  ok: "Stories grouped normally.",
  skipped: "Story grouping isn't configured — headlines shown individually.",
  error: "Story grouping failed — headlines shown individually.",
  unknown: "Story grouping status unknown — the fetch didn't complete.",
};

// skipped is a deliberate, expected state (no OPENAI_API_KEY configured),
// not a problem -- kept visually distinct from the real error state.
const DOT_COLOR: Record<SearchResponse["grouping"], string> = {
  ok: "bg-emerald-500",
  skipped: "bg-slate-400",
  error: "bg-red-500",
  unknown: "bg-amber-500",
};

export function GroupingStatus({ grouping }: GroupingStatusProps) {
  return (
    <p className="flex items-center gap-2 text-sm text-slate-600">
      <span className={`h-2 w-2 shrink-0 rounded-full ${DOT_COLOR[grouping]}`} />
      {MESSAGE[grouping]}
    </p>
  );
}
