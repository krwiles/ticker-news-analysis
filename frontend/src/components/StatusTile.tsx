import type { CheckStatus } from "../health";

const DOT_COLOR: Record<CheckStatus, string> = {
  ok: "bg-emerald-500",
  stale: "bg-amber-500",
  error: "bg-red-500",
  unknown: "bg-slate-400",
};

const LABEL: Record<CheckStatus, string> = {
  ok: "Connected",
  stale: "Stale",
  error: "Error",
  unknown: "Unknown",
};

interface StatusTileProps {
  name: string;
  status: CheckStatus;
  detail?: string;
}

export function StatusTile({ name, status, detail }: StatusTileProps) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
      <div>
        <p className="font-medium text-slate-900">{name}</p>
        {detail && <p className="text-sm text-slate-500">{detail}</p>}
      </div>
      <div className="flex items-center gap-2">
        <span className={`h-2.5 w-2.5 rounded-full ${DOT_COLOR[status]}`} />
        <span className="text-sm text-slate-600">{LABEL[status]}</span>
      </div>
    </div>
  );
}
