import type { Headline } from "../search";

interface HeadlineListProps {
  headlines: Headline[];
}

// Renders one combined list -- no Today/Recent split, no styled category
// badge yet. Both are deliberately deferred to lesson 14 (see
// docs/plans/0011-react-search-bar-and-first-render.md and NOTES.md) --
// this lesson's job is components/JSX/hooks, not the spec's full
// recency/badge presentation.
export function HeadlineList({ headlines }: HeadlineListProps) {
  if (headlines.length === 0) {
    return <p className="text-sm text-slate-500">No headlines in the past week for this ticker.</p>;
  }

  return (
    <ul className="flex flex-col gap-3">
      {headlines.map((headline) => (
        <li key={headline.url} className="rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
          <a
            href={headline.url}
            target="_blank"
            rel="noreferrer"
            className="font-medium text-slate-900 hover:underline"
          >
            {headline.title}
          </a>
          <p className="mt-1 text-xs text-slate-500">
            {headline.category}
            {headline.outlet && ` · via ${headline.outlet}`}
            {" · "}
            {new Date(headline.published_at).toLocaleString()}
          </p>
          {headline.summary && <p className="mt-1 text-sm text-slate-600">{headline.summary}</p>}
        </li>
      ))}
    </ul>
  );
}
