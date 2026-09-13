import type { Headline } from "../search";
import { CategoryBadge } from "./CategoryBadge";

interface HeadlineListProps {
  headlines: Headline[];
  // Caller-specific -- SearchPage's Today section and Recent section each
  // need their own wording, so this isn't a page-wide constant anymore.
  emptyMessage: string;
}

export function HeadlineList({ headlines, emptyMessage }: HeadlineListProps) {
  if (headlines.length === 0) {
    return <p className="text-sm text-slate-500">{emptyMessage}</p>;
  }

  return (
    <ul className="flex flex-col gap-3">
      {headlines.map((headline) => (
        <li key={headline.url} className="rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
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
            {headline.outlet && `via ${headline.outlet} · `}
            {new Date(headline.published_at).toLocaleString()}
          </p>
          {headline.summary && <p className="mt-1 text-sm text-slate-600">{headline.summary}</p>}
        </li>
      ))}
    </ul>
  );
}
