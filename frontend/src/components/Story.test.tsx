import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Headline, Story as StoryType } from "../search";
import { Story } from "./Story";

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

function story(overrides: Partial<StoryType> = {}): StoryType {
  return {
    story_id: "11111111-1111-1111-1111-111111111111",
    primary: headline(),
    other_members: [],
    sentiment_average: null,
    sentiment_enum: null,
    ...overrides,
  };
}

describe("Story", () => {
  it("always renders the primary headline", () => {
    // Arrange + act: render a Story with a known primary headline.
    render(<Story story={story({ primary: headline({ title: "The primary" }) })} />);
    // Assert: the primary headline's link is shown.
    expect(screen.getByRole("link", { name: "The primary" })).toBeInTheDocument();
  });

  it("shows no disclosure at all for a Story of one", () => {
    // Arrange + act: render a Story with no other members.
    render(<Story story={story({ other_members: [] })} />);
    // Assert: no "more sources" disclosure is rendered.
    expect(screen.queryByText(/more source/)).not.toBeInTheDocument();
  });

  it("hides other_members behind a closed disclosure by default", () => {
    // Arrange + act: render a Story with one other member.
    render(
      <Story
        story={story({
          other_members: [headline({ title: "A hidden member", url: "https://example.com/b" })],
        })}
      />,
    );
    // Assert: the disclosure summary is shown but starts closed.
    expect(screen.getByText(/\+1 more source/)).toBeInTheDocument();
    // Present in the DOM (details content is never removed), but not open yet.
    const details = screen.getByText(/\+1 more source/).closest("details")!;
    expect(details).not.toHaveAttribute("open");
  });

  it("reveals other_members when the disclosure is opened", async () => {
    // Arrange: render a Story with one other member.
    render(
      <Story
        story={story({
          other_members: [headline({ title: "A hidden member", url: "https://example.com/b" })],
        })}
      />,
    );

    // Act: open the disclosure.
    const user = userEvent.setup();
    await user.click(screen.getByText(/\+1 more source/));

    // Assert: the previously-hidden member is now visible.
    expect(screen.getByRole("link", { name: "A hidden member" })).toBeInTheDocument();
  });

  it("pluralizes the coverage count correctly", () => {
    // Arrange + act: render a Story with two other members.
    render(
      <Story
        story={story({
          other_members: [
            headline({ url: "https://example.com/b" }),
            headline({ url: "https://example.com/c" }),
          ],
        })}
      />,
    );
    // Assert: the count label is pluralized.
    expect(screen.getByText("+2 more sources")).toBeInTheDocument();
  });

  it("shows no Story-level chrome for a Story of one, even if sentiment_average happens to be set", () => {
    // Arrange + act: a lone member, but a real (if trivial) aggregate already present -- see lesson 28/29 planning.
    render(<Story story={story({ other_members: [], sentiment_average: 60, sentiment_enum: "positive" })} />);
    // Assert: no "Story" label pill -- member count, not aggregate presence, gates the wrapper.
    expect(screen.queryByText("Story")).not.toBeInTheDocument();
  });

  it("shows the Story label and a Pending aggregate pill for a multi-member Story with no resolved members yet", () => {
    // Arrange + act: a multi-member Story whose primary already resolved, but whose aggregate hasn't yet
    // (a real, genuine window -- the aggregate only updates once a member actually lands).
    render(
      <Story
        story={story({
          primary: headline({ sentiment_score: 85, sentiment_gloss: "bullish", sentiment_status: "ok", sentiment_enum: "positive" }),
          other_members: [
            headline({
              url: "https://example.com/b",
              sentiment_score: 40,
              sentiment_gloss: "concerning",
              sentiment_status: "ok",
              sentiment_enum: "negative",
            }),
          ],
          sentiment_average: null,
          sentiment_enum: null,
        })}
      />,
    );
    // Assert: the Story wrapper appears, and its aggregate pill (the only Pending one -- both members already resolved) is Pending.
    expect(screen.getByText("Story")).toBeInTheDocument();
    expect(screen.getByText("Pending")).toBeInTheDocument();
  });

  it("shows the resolved aggregate score for a multi-member Story", () => {
    // Arrange + act: a real multi-member Story with a resolved aggregate.
    render(
      <Story
        story={story({
          other_members: [headline({ url: "https://example.com/b" })],
          sentiment_average: 80.67,
          sentiment_enum: "positive",
        })}
      />,
    );
    // Assert: the aggregate pill shows enum + rounded score -- no gloss exists at the Story level.
    expect(screen.getByText("positive · 81")).toBeInTheDocument();
  });
});
