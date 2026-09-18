import type { Headline } from "../search";
import { CategoryBadge } from "./CategoryBadge";
import { SentimentPill } from "./SentimentPill";

interface HeadlineCardProps {
  headline: Headline;
}

// One headline's full rendering -- shared by Story for both its primary and
// each of its other_members, so the two never drift into different markup.
export function HeadlineCard({ headline }: HeadlineCardProps) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        {/* Category pill above the title, left-aligned (spec 0005 layout) -- min-w-0 lets this column
            actually shrink/wrap instead of a long title forcing the row wider than the card. */}
        <div className="flex min-w-0 flex-1 flex-col items-start gap-1">
          <CategoryBadge category={headline.category} />
          <a
            href={headline.url}
            target="_blank"
            rel="noreferrer"
            className="break-words font-medium text-slate-900 hover:underline"
          >
            {headline.title}
          </a>
          <p className="text-xs text-slate-500">
            {/* outlet is the original publisher -- absent for EDGAR filings (the filing IS the
                source), so this segment renders as nothing rather than an empty "via". */}
            {headline.outlet && `via ${headline.outlet} · `}
            {new Date(headline.published_at).toLocaleString()}
          </p>
        </div>
        {/* Sentiment sub-card, same width as the left column (flex-1) -- min-w-0 stops a long
            rationale from widening the row. Always present, even pending (spec 0005), so nothing
            reflows when it resolves -- only the pill/rationale inside it change. */}
        <div className="min-w-0 flex-1 rounded-md border border-slate-100 bg-slate-50 px-3 py-2">
          <SentimentPill enumValue={headline.sentiment_enum} score={headline.sentiment_score} gloss={headline.sentiment_gloss} />
          {/* rationale is the LLM's own explanation for the score -- distinct from summary, only shown once resolved. */}
          {headline.sentiment_rationale && <p className="mt-1 break-words text-xs text-slate-500">{headline.sentiment_rationale}</p>}
        </div>
      </div>
      {/* summary is a free blurb some providers hand back directly -- absent (not fetched)
          when a provider doesn't give one, e.g. EDGAR. */}
      {headline.summary && <p className="mt-1 text-sm text-slate-600">{headline.summary}</p>}
    </div>
  );
}
