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
    render(<HeadlineCard headline={headline()} />);
    const link = screen.getByRole("link", { name: "A real headline" });
    expect(link).toHaveAttribute("href", "https://example.com/a");
  });

  it("shows the outlet when present", () => {
    render(<HeadlineCard headline={headline({ outlet: "Yahoo" })} />);
    expect(screen.getByText(/via Yahoo/)).toBeInTheDocument();
  });

  it("omits outlet text when null", () => {
    render(<HeadlineCard headline={headline({ outlet: null })} />);
    expect(screen.queryByText(/via /)).not.toBeInTheDocument();
  });

  it("shows the summary when present", () => {
    render(<HeadlineCard headline={headline({ summary: "A short blurb." })} />);
    expect(screen.getByText("A short blurb.")).toBeInTheDocument();
  });

  it("omits summary when null", () => {
    const { container } = render(<HeadlineCard headline={headline({ summary: null })} />);
    // Only the metadata line should exist -- no second <p> for a missing summary.
    expect(container.querySelectorAll("p")).toHaveLength(1);
  });

  it("renders category via CategoryBadge, not plain text", () => {
    render(<HeadlineCard headline={headline({ category: "filing" })} />);
    expect(screen.getByText("Filing")).toBeInTheDocument();
  });
});
