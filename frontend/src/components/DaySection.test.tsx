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
    sentiment_score: null,
    sentiment_gloss: null,
    sentiment_rationale: null,
    sentiment_status: null,
    sentiment_enum: null,
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
    // Arrange + act: render a day flagged as today.
    render(<DaySection day={day({ is_today: true, date: "2026-09-17" })} />);
    // Assert: heading reads "Today", not the raw date string.
    expect(screen.getByRole("heading", { name: "Today" })).toBeInTheDocument();
  });

  it("labels an earlier day with a formatted date, parsed without a UTC-midnight shift", () => {
    // Regression case: new Date("2026-09-16") is UTC midnight -- in any
    // timezone behind UTC (including Eastern) that formats as September 15.
    // Arrange + act: render a non-today day.
    render(<DaySection day={day({ is_today: false, date: "2026-09-16" })} />);
    // Assert: heading is the correctly-shifted local date.
    expect(screen.getByRole("heading", { name: "September 16" })).toBeInTheDocument();
  });

  it("shows an empty message when there are no Stories", () => {
    // Arrange + act: render a day with an empty stories list.
    render(<DaySection day={day({ is_today: true, stories: [] })} />);
    // Assert: the empty-state placeholder text appears.
    expect(screen.getByText("No headlines today.")).toBeInTheDocument();
  });

  it("renders one Story per entry", () => {
    // Arrange + act: render a day with two distinct stories.
    const section = render(
      <DaySection
        day={day({
          stories: [
            {
              story_id: "s1",
              primary: headline({ title: "First", url: "https://example.com/1" }),
              other_members: [],
              sentiment_average: null,
              sentiment_enum: null,
            },
            {
              story_id: "s2",
              primary: headline({ title: "Second", url: "https://example.com/2" }),
              other_members: [],
              sentiment_average: null,
              sentiment_enum: null,
            },
          ],
        })}
      />,
    );
    // Assert: both stories' primary headlines are rendered.
    expect(within(section.container).getByRole("link", { name: "First" })).toBeInTheDocument();
    expect(within(section.container).getByRole("link", { name: "Second" })).toBeInTheDocument();
  });
});
