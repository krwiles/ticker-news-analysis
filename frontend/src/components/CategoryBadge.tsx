import type { Headline } from "../search";

interface CategoryBadgeProps {
  category: Headline["category"];
}

// "news" and "filing" (the backend's exact category values, see search.py)
// aren't fit for display as-is -- capitalized, human-facing labels.
const LABEL: Record<Headline["category"], string> = {
  news: "News",
  filing: "Filing",
};

// Distinct from SearchStatus's colors on purpose -- two separate visual
// systems (what kind of document vs. how the fetch went) shouldn't blur
// together.
const COLOR: Record<Headline["category"], string> = {
  news: "bg-blue-100 text-blue-700",
  filing: "bg-purple-100 text-purple-700",
};

export function CategoryBadge({ category }: CategoryBadgeProps) {
  return (
    <span
      className={`inline-block shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${COLOR[category]}`}
    >
      {LABEL[category]}
    </span>
  );
}
