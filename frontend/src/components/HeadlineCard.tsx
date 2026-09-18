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
        {/* Category pill, title, and date stacked on the left -- pill left-aligned above the title,
            not next to the sentiment card anymore. min-w-0 lets this flex child actually shrink/wrap
            instead of forcing the row wider than the card -- its default min-width is the content's
            own intrinsic width, which a long title/URL would otherwise refuse to go below. */}
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
            {/* outlet is the original publisher (e.g. "Yahoo"), reported by
                some providers but not others -- EDGAR filings never have
                one (it IS the source), so this whole segment renders as
                nothing rather than an empty "via" when it's null. */}
            {headline.outlet && `via ${headline.outlet} · `}
            {new Date(headline.published_at).toLocaleString()}
          </p>
        </div>
        {/* Sentiment sub-card on the right -- flex-1, same width as the left column, so the two
            split the row evenly. min-w-0 is what actually stops a long rationale sentence from
            growing this column -- and the rest of the row along with it -- past the card's own edge;
            break-words wraps it inside instead. Always present, even while pending (spec 0005) -- so
            nothing reflows into or out of existence once it resolves, only the pill/rationale inside
            it change. */}
        <div className="min-w-0 flex-1 rounded-md border border-slate-100 bg-slate-50 px-3 py-2">
          <SentimentPill enumValue={headline.sentiment_enum} score={headline.sentiment_score} gloss={headline.sentiment_gloss} />
          {/* rationale is the LLM's own explanation for the score -- distinct from summary, only shown once resolved. */}
          {headline.sentiment_rationale && <p className="mt-1 break-words text-xs text-slate-500">{headline.sentiment_rationale}</p>}
        </div>
      </div>
      {/* summary is a free blurb some providers hand back directly --
          never fetched separately, and just absent when a provider
          doesn't give one (e.g. EDGAR). */}
      {headline.summary && <p className="mt-1 text-sm text-slate-600">{headline.summary}</p>}
    </div>
  );
}
