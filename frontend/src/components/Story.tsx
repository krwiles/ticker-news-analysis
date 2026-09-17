import type { Story as StoryType } from "../search";
import { HeadlineCard } from "./HeadlineCard";

interface StoryProps {
  story: StoryType;
}

// One Story: its primary headline in full, plus (only when there are any)
// an expandable list of other members behind a native disclosure -- no
// local state needed, the browser already handles open/closed.
export function Story({ story }: StoryProps) {
  return (
    <div>
      <HeadlineCard headline={story.primary} />
      {story.other_members.length > 0 && (
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
      )}
    </div>
  );
}
