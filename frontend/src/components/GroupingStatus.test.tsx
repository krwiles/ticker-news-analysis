import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { GroupingStatus } from "./GroupingStatus";

describe("GroupingStatus", () => {
  it("shows a distinct message for ok -- not just the failure/skipped states", () => {
    render(<GroupingStatus grouping="ok" />);
    expect(screen.getByText(/grouped normally/i)).toBeInTheDocument();
  });

  it("shows a distinct message for skipped", () => {
    render(<GroupingStatus grouping="skipped" />);
    expect(screen.getByText(/isn't configured/i)).toBeInTheDocument();
  });

  it("shows a distinct message for error", () => {
    render(<GroupingStatus grouping="error" />);
    expect(screen.getByText(/grouping failed/i)).toBeInTheDocument();
  });

  it("shows a distinct message for unknown", () => {
    render(<GroupingStatus grouping="unknown" />);
    expect(screen.getByText(/status unknown/i)).toBeInTheDocument();
  });

  it("never renders the raw grouping value itself", () => {
    render(<GroupingStatus grouping="skipped" />);
    expect(screen.queryByText("skipped")).not.toBeInTheDocument();
  });
});
