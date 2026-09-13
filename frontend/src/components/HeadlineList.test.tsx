import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Headline } from "../search";
import { HeadlineList } from "./HeadlineList";

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

describe("HeadlineList", () => {
  it("renders the empty state when there are no headlines", () => {
    render(<HeadlineList headlines={[]} />);
    expect(screen.getByText(/no headlines in the past week/i)).toBeInTheDocument();
  });

  it("renders a headline's title as a link to its real url", () => {
    render(<HeadlineList headlines={[headline()]} />);
    const link = screen.getByRole("link", { name: "A real headline" });
    expect(link).toHaveAttribute("href", "https://example.com/a");
  });

  it("shows the outlet when present", () => {
    render(<HeadlineList headlines={[headline({ outlet: "Yahoo" })]} />);
    expect(screen.getByText(/via Yahoo/)).toBeInTheDocument();
  });

  it("omits outlet text when null", () => {
    render(<HeadlineList headlines={[headline({ outlet: null })]} />);
    expect(screen.queryByText(/via /)).not.toBeInTheDocument();
  });

  it("shows the summary when present", () => {
    render(<HeadlineList headlines={[headline({ summary: "A short blurb." })]} />);
    expect(screen.getByText("A short blurb.")).toBeInTheDocument();
  });

  it("omits summary when null", () => {
    const { container } = render(<HeadlineList headlines={[headline({ summary: null })]} />);
    // Only the title link and the metadata line should exist -- no third <p>.
    expect(container.querySelectorAll("p")).toHaveLength(1);
  });

  it("renders category as plain text, not a styled badge (regression guard for lesson 14)", () => {
    render(<HeadlineList headlines={[headline({ category: "filing" })]} />);
    expect(screen.getByText(/filing/)).toBeInTheDocument();
  });
});
