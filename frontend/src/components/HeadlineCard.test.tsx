import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Headline } from "../search";
import { HeadlineCard } from "./HeadlineCard";

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

describe("HeadlineCard", () => {
  it("renders the title as a link to its real url", () => {
    // Arrange + act: render a headline with a known url.
    render(<HeadlineCard headline={headline()} />);
    // Assert: the title link points at that same url.
    const link = screen.getByRole("link", { name: "A real headline" });
    expect(link).toHaveAttribute("href", "https://example.com/a");
  });

  it("shows the outlet when present", () => {
    // Arrange + act: render a headline with an outlet set.
    render(<HeadlineCard headline={headline({ outlet: "Yahoo" })} />);
    // Assert: the outlet is shown.
    expect(screen.getByText(/via Yahoo/)).toBeInTheDocument();
  });

  it("omits outlet text when null", () => {
    // Arrange + act: render a headline with no outlet.
    render(<HeadlineCard headline={headline({ outlet: null })} />);
    // Assert: no outlet text is rendered.
    expect(screen.queryByText(/via /)).not.toBeInTheDocument();
  });

  it("shows the summary when present", () => {
    // Arrange + act: render a headline with a summary set.
    render(<HeadlineCard headline={headline({ summary: "A short blurb." })} />);
    // Assert: the summary text is shown.
    expect(screen.getByText("A short blurb.")).toBeInTheDocument();
  });

  it("omits summary when null", () => {
    // Arrange + act: render a headline with no summary.
    const { container } = render(<HeadlineCard headline={headline({ summary: null })} />);
    // Assert: only the metadata line should exist -- no second <p> for a missing summary.
    expect(container.querySelectorAll("p")).toHaveLength(1);
  });

  it("renders category via CategoryBadge, not plain text", () => {
    // Arrange + act: render a headline with a "filing" category.
    render(<HeadlineCard headline={headline({ category: "filing" })} />);
    // Assert: the badge's title-cased label is shown.
    expect(screen.getByText("Filing")).toBeInTheDocument();
  });
});
