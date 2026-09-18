import type { SentimentEnum } from "../search";

interface SentimentPillProps {
  enumValue: SentimentEnum | null;
  score: number | null;
  // Only Headlines have one -- a Story's aggregate is just a number, no gloss (CONTEXT.md).
  gloss?: string | null;
}

// Colors distinct from CategoryBadge's own -- same "shouldn't blur together" reasoning that badge already uses.
const COLOR: Record<SentimentEnum, string> = {
  positive: "bg-emerald-100 text-emerald-700",
  neutral: "bg-slate-100 text-slate-700",
  negative: "bg-red-100 text-red-700",
};

// Shared by HeadlineCard and Story -- one visual language for resolved vs. pending sentiment.
// Collapses skipped/error/pending into one grey "Pending" bucket; the why lives in SentimentStatus, not here.
export function SentimentPill({ enumValue, score, gloss }: SentimentPillProps) {
  if (enumValue === null || score === null) {
    return (
      <span className="inline-block shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-400">
        Pending
      </span>
    );
  }

  return (
    <span className={`inline-block shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${COLOR[enumValue]}`}>
      {gloss ? `${gloss} · ${score}` : `${enumValue} · ${Math.round(score)}`}
    </span>
  );
}
