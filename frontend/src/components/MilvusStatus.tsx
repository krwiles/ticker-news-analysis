import type { MilvusCheck } from "../health";

// Bespoke type, not CheckStatus -- Milvus has a genuine third state (not_initialized, spec 0003).
// Laid out like StatusTile (name + dot + label + detail), matching the other service tiles.
const DOT_COLOR: Record<MilvusCheck["status"], string> = {
  ok: "bg-emerald-500",
  not_initialized: "bg-slate-400",
  error: "bg-red-500",
  unknown: "bg-slate-400",
};

const LABEL: Record<MilvusCheck["status"], string> = {
  ok: "Connected",
  not_initialized: "Not yet initialized",
  error: "Error",
  unknown: "Unknown",
};

// Detail line per state -- "ok" reports the real count, "error" reports
// the real failure, "not_initialized" explains the (expected) empty state.
function detailFor(milvus: MilvusCheck): string | undefined {
  switch (milvus.status) {
    case "ok":
      // Always plural, even at 1 -- deliberate, matches the Database
      // tile's own counts (spec 0004), not grammatically "correct".
      return `${milvus.vector_count} stories indexed`;
    case "not_initialized":
      return "Collection not created yet";
    case "error":
      return milvus.detail;
    case "unknown":
      return undefined;
  }
}

interface MilvusStatusProps {
  milvus: MilvusCheck;
}

export function MilvusStatus({ milvus }: MilvusStatusProps) {
  const detail = detailFor(milvus);
  return (
    <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
      <div>
        <p className="font-medium text-slate-900">Milvus</p>
        {detail && <p className="text-sm text-slate-500">{detail}</p>}
      </div>
      <div className="flex items-center gap-2">
        <span className={`h-2.5 w-2.5 rounded-full ${DOT_COLOR[milvus.status]}`} />
        <span className="text-sm text-slate-600">{LABEL[milvus.status]}</span>
      </div>
    </div>
  );
}
