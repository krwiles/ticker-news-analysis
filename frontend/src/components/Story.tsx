import type { Story as StoryType } from "../search";
import { HeadlineCard } from "./HeadlineCard";
import { SentimentPill } from "./SentimentPill";

interface StoryProps {
  story: StoryType;
}

// One Story: its primary headline in full, plus an expandable list of other members (when any)
// behind a native disclosure -- no local state needed, the browser handles open/closed.
export function Story({ story }: StoryProps) {
  // A Story of one gets zero extra chrome -- gated on member count, not on whether
  // sentiment_average is present (backend returns it trivially even for a lone member) -- see CONTEXT.md.
  const isMultiMember = story.other_members.length > 0;

  // Reused below whether or not this Story ends up wrapped -- the primary renders
  // identically either way, no special treatment inside a multi-member Story.
  const primaryCard = <HeadlineCard headline={story.primary} />;

  if (!isMultiMember) {
    return <div>{primaryCard}</div>;
  }

  return (
    <div className="rounded-lg border border-slate-100 bg-slate-50/50 p-2">
      <div className="mb-2 flex items-center gap-1.5 px-1">
        <span className="inline-block shrink-0 rounded-full bg-slate-200 px-2 py-0.5 text-xs font-medium text-slate-600">
          Story
        </span>
        <SentimentPill enumValue={story.sentiment_enum} score={story.sentiment_average} />
      </div>
      {primaryCard}
      <details className="mt-1 ml-1">
        <summary className="cursor-pointer text-xs font-medium text-slate-500 hover:text-slate-700">
          +{story.other_members.length} more source{story.other_members.length === 1 ? "" : "s"}
        </summary>
        <div className="mt-2 flex flex-col gap-2 border-l-2 border-slate-200 pl-3">
          {story.other_members.map((member) => (
            <HeadlineCard key={member.url} headline={member} />
          ))}
        </div>
      </details>
    </div>
  );
}
