import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CategoryBadge } from "./CategoryBadge";

describe("CategoryBadge", () => {
  it("renders 'News' for the news category", () => {
    render(<CategoryBadge category="news" />);
    expect(screen.getByText("News")).toBeInTheDocument();
  });

  it("renders 'Filing' for the filing category", () => {
    render(<CategoryBadge category="filing" />);
    expect(screen.getByText("Filing")).toBeInTheDocument();
  });

  it("uses a visibly distinct style per category", () => {
    const { rerender } = render(<CategoryBadge category="news" />);
    const newsClass = screen.getByText("News").className;

    rerender(<CategoryBadge category="filing" />);
    const filingClass = screen.getByText("Filing").className;

    expect(newsClass).not.toBe(filingClass);
  });
});
