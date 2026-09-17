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
    ...overrides,
  };
}

function story(overrides: Partial<StoryType> = {}): StoryType {
  return {
    story_id: "11111111-1111-1111-1111-111111111111",
    primary: headline(),
    other_members: [],
    ...overrides,
  };
}

describe("Story", () => {
  it("always renders the primary headline", () => {
    render(<Story story={story({ primary: headline({ title: "The primary" }) })} />);
    expect(screen.getByRole("link", { name: "The primary" })).toBeInTheDocument();
  });

  it("shows no disclosure at all for a Story of one", () => {
    render(<Story story={story({ other_members: [] })} />);
    expect(screen.queryByText(/more source/)).not.toBeInTheDocument();
  });

  it("hides other_members behind a closed disclosure by default", () => {
    render(
      <Story
        story={story({
          other_members: [headline({ title: "A hidden member", url: "https://example.com/b" })],
        })}
      />,
    );
    expect(screen.getByText(/\+1 more source/)).toBeInTheDocument();
    // Present in the DOM (details content is never removed), but not open yet.
    const details = screen.getByText(/\+1 more source/).closest("details")!;
    expect(details).not.toHaveAttribute("open");
  });

  it("reveals other_members when the disclosure is opened", async () => {
    render(
      <Story
        story={story({
          other_members: [headline({ title: "A hidden member", url: "https://example.com/b" })],
        })}
      />,
    );

    const user = userEvent.setup();
    await user.click(screen.getByText(/\+1 more source/));

    expect(screen.getByRole("link", { name: "A hidden member" })).toBeInTheDocument();
  });

  it("pluralizes the coverage count correctly", () => {
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
    expect(screen.getByText("+2 more sources")).toBeInTheDocument();
  });
});
