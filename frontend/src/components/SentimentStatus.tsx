import type { SentimentStatus as SentimentStatusType } from "../search";

interface SentimentStatusProps {
  sentiment: SentimentStatusType;
}

// "ok" gets a message too, same reasoning as SearchStatus/GroupingStatus's own success case.
const MESSAGE: Record<SentimentStatusType, string> = {
  ok: "Sentiment analysis complete.",
  processing: "Sentiment analysis in progress…",
  skipped: "Sentiment analysis isn't configured — headlines shown without it.",
  error: "Sentiment analysis failed for at least one headline.",
};

// skipped is a deliberate, expected state (no OPENAI_API_KEY configured), same as GroupingStatus's own skipped.
const DOT_COLOR: Record<SentimentStatusType, string> = {
  ok: "bg-emerald-500",
  processing: "bg-amber-500",
  skipped: "bg-slate-400",
  error: "bg-red-500",
};

export function SentimentStatus({ sentiment }: SentimentStatusProps) {
  return (
    <p className="flex items-center gap-2 text-sm text-slate-600">
      <span className={`h-2 w-2 shrink-0 rounded-full ${DOT_COLOR[sentiment]}`} />
      {MESSAGE[sentiment]}
    </p>
  );
}
