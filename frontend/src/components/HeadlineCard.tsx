import type { Headline } from "../search";
import { CategoryBadge } from "./CategoryBadge";

interface HeadlineCardProps {
  headline: Headline;
}

// One headline's full rendering -- shared by Story for both its primary and
// each of its other_members, so the two never drift into different markup.
export function HeadlineCard({ headline }: HeadlineCardProps) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <a
          href={headline.url}
          target="_blank"
          rel="noreferrer"
          className="font-medium text-slate-900 hover:underline"
        >
          {headline.title}
        </a>
        <CategoryBadge category={headline.category} />
      </div>
      <p className="mt-1 text-xs text-slate-500">
        {/* outlet is the original publisher (e.g. "Yahoo"), reported by
            some providers but not others -- EDGAR filings never have
            one (it IS the source), so this whole segment renders as
            nothing rather than an empty "via" when it's null. */}
        {headline.outlet && `via ${headline.outlet} · `}
        {new Date(headline.published_at).toLocaleString()}
      </p>
      {/* summary is a free blurb some providers hand back directly --
          never fetched separately, and just absent when a provider
          doesn't give one (e.g. EDGAR). */}
      {headline.summary && <p className="mt-1 text-sm text-slate-600">{headline.summary}</p>}
    </div>
  );
}
