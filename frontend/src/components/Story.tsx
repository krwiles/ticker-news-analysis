import type { Story as StoryType } from "../search";
import { HeadlineCard } from "./HeadlineCard";
import { SentimentPill } from "./SentimentPill";

interface StoryProps {
  story: StoryType;
}

// One Story: its primary headline in full, plus (only when there are any)
// an expandable list of other members behind a native disclosure -- no
// local state needed, the browser already handles open/closed.
export function Story({ story }: StoryProps) {
  // A Story of one gets zero extra chrome -- gated on member count, not on
  // whether sentiment_average happens to be present (it's returned, if
  // trivially, even for a lone member -- see lesson 28/29 planning and
  // CONTEXT.md's own "more than one member" definition of the aggregate).
  const isMultiMember = story.other_members.length > 0;

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
