import type { DayGroup } from "../search";
import { Story } from "./Story";

interface DaySectionProps {
  day: DayGroup;
}

// "YYYY-MM-DD" -> a local Date at midnight, without going through Date's
// own string parsing (which treats "YYYY-MM-DD" as UTC midnight and can
// render as the wrong day in any timezone west of UTC, including Eastern).
function parseIsoDateLocal(isoDate: string): Date {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Date(year, month - 1, day);
}

export function DaySection({ day }: DaySectionProps) {
  const heading = day.is_today
    ? "Today"
    : parseIsoDateLocal(day.date).toLocaleDateString(undefined, { month: "long", day: "numeric" });

  return (
    <section className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">{heading}</h2>
      {day.stories.length === 0 ? (
        <p className="text-sm text-slate-500">No headlines today.</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {day.stories.map((story) => (
            <li key={story.story_id ?? story.primary.url}>
              <Story story={story} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
