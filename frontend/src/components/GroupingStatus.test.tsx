import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { GroupingStatus } from "./GroupingStatus";

describe("GroupingStatus", () => {
  it("shows a distinct message for ok -- not just the failure/skipped states", () => {
    // Arrange + act: render with the "ok" state.
    render(<GroupingStatus grouping="ok" />);
    // Assert: the ok-specific message is shown.
    expect(screen.getByText(/grouped normally/i)).toBeInTheDocument();
  });

  it("shows a distinct message for skipped", () => {
    // Arrange + act: render with the "skipped" state.
    render(<GroupingStatus grouping="skipped" />);
    // Assert: the skipped-specific message is shown.
    expect(screen.getByText(/isn't configured/i)).toBeInTheDocument();
  });

  it("shows a distinct message for error", () => {
    // Arrange + act: render with the "error" state.
    render(<GroupingStatus grouping="error" />);
    // Assert: the error-specific message is shown.
    expect(screen.getByText(/grouping failed/i)).toBeInTheDocument();
  });

  it("shows a distinct message for unknown", () => {
    // Arrange + act: render with the "unknown" state.
    render(<GroupingStatus grouping="unknown" />);
    // Assert: the unknown-specific message is shown.
    expect(screen.getByText(/status unknown/i)).toBeInTheDocument();
  });

  it("never renders the raw grouping value itself", () => {
    // Arrange + act: render with a raw state value.
    render(<GroupingStatus grouping="skipped" />);
    // Assert: the raw enum string never leaks into the rendered text.
    expect(screen.queryByText("skipped")).not.toBeInTheDocument();
  });
});
