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
  it("renders the given emptyMessage when there are no headlines", () => {
    render(<HeadlineList headlines={[]} emptyMessage="Nothing here yet." />);
    expect(screen.getByText("Nothing here yet.")).toBeInTheDocument();
  });

  it("renders a caller-specific emptyMessage, not a fixed string", () => {
    render(<HeadlineList headlines={[]} emptyMessage="No headlines today." />);
    expect(screen.getByText("No headlines today.")).toBeInTheDocument();
  });

  it("renders a headline's title as a link to its real url", () => {
    render(<HeadlineList headlines={[headline()]} emptyMessage="unused" />);
    const link = screen.getByRole("link", { name: "A real headline" });
    expect(link).toHaveAttribute("href", "https://example.com/a");
  });

  it("shows the outlet when present", () => {
    render(<HeadlineList headlines={[headline({ outlet: "Yahoo" })]} emptyMessage="unused" />);
    expect(screen.getByText(/via Yahoo/)).toBeInTheDocument();
  });

  it("omits outlet text when null", () => {
    render(<HeadlineList headlines={[headline({ outlet: null })]} emptyMessage="unused" />);
    expect(screen.queryByText(/via /)).not.toBeInTheDocument();
  });

  it("shows the summary when present", () => {
    render(<HeadlineList headlines={[headline({ summary: "A short blurb." })]} emptyMessage="unused" />);
    expect(screen.getByText("A short blurb.")).toBeInTheDocument();
  });

  it("omits summary when null", () => {
    const { container } = render(
      <HeadlineList headlines={[headline({ summary: null })]} emptyMessage="unused" />,
    );
    // Only the title link's row and the metadata line should exist -- no third <p>.
    expect(container.querySelectorAll("p")).toHaveLength(1);
  });

  it("renders category via CategoryBadge, not plain text (lesson 14 replaces lesson 11's placeholder)", () => {
    render(<HeadlineList headlines={[headline({ category: "filing" })]} emptyMessage="unused" />);
    expect(screen.getByText("Filing")).toBeInTheDocument();
  });
});
