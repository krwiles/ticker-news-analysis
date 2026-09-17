import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { DayGroup, Headline } from "../search";
import { DaySection } from "./DaySection";

function headline(overrides: Partial<Headline> = {}): Headline {
  return {
    title: "A real headline",
    url: "https://example.com/a",
    category: "news",
    provider: "finnhub",
    outlet: null,
    summary: null,
    published_at: "2026-09-11T12:00:00Z",
    ...overrides,
  };
}

function day(overrides: Partial<DayGroup> = {}): DayGroup {
  return {
    date: "2026-09-16",
    is_today: false,
    stories: [],
    ...overrides,
  };
}

describe("DaySection", () => {
  it("labels a Today day as 'Today', not its raw date", () => {
    render(<DaySection day={day({ is_today: true, date: "2026-09-17" })} />);
    expect(screen.getByRole("heading", { name: "Today" })).toBeInTheDocument();
  });

  it("labels an earlier day with a formatted date, parsed without a UTC-midnight shift", () => {
    // Regression case: new Date("2026-09-16") is UTC midnight -- in any
    // timezone behind UTC (including Eastern) that formats as September 15.
    render(<DaySection day={day({ is_today: false, date: "2026-09-16" })} />);
    expect(screen.getByRole("heading", { name: "September 16" })).toBeInTheDocument();
  });

  it("shows an empty message when there are no Stories", () => {
    render(<DaySection day={day({ is_today: true, stories: [] })} />);
    expect(screen.getByText("No headlines today.")).toBeInTheDocument();
  });

  it("renders one Story per entry", () => {
    const section = render(
      <DaySection
        day={day({
          stories: [
            { story_id: "s1", primary: headline({ title: "First", url: "https://example.com/1" }), other_members: [] },
            { story_id: "s2", primary: headline({ title: "Second", url: "https://example.com/2" }), other_members: [] },
          ],
        })}
      />,
    );
    expect(within(section.container).getByRole("link", { name: "First" })).toBeInTheDocument();
    expect(within(section.container).getByRole("link", { name: "Second" })).toBeInTheDocument();
  });
});
