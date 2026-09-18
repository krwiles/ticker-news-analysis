import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SentimentStatus } from "./SentimentStatus";

describe("SentimentStatus", () => {
  it("shows a distinct message for ok -- not just the failure/pending states", () => {
    // Arrange + act: render with the "ok" state.
    render(<SentimentStatus sentiment="ok" />);
    // Assert: the ok-specific message is shown.
    expect(screen.getByText(/analysis complete/i)).toBeInTheDocument();
  });

  it("shows a distinct message for processing", () => {
    // Arrange + act: render with the "processing" state.
    render(<SentimentStatus sentiment="processing" />);
    // Assert: the processing-specific message is shown.
    expect(screen.getByText(/in progress/i)).toBeInTheDocument();
  });

  it("shows a distinct message for skipped", () => {
    // Arrange + act: render with the "skipped" state.
    render(<SentimentStatus sentiment="skipped" />);
    // Assert: the skipped-specific message is shown.
    expect(screen.getByText(/isn't configured/i)).toBeInTheDocument();
  });

  it("shows a distinct message for error", () => {
    // Arrange + act: render with the "error" state.
    render(<SentimentStatus sentiment="error" />);
    // Assert: the error-specific message is shown.
    expect(screen.getByText(/analysis failed/i)).toBeInTheDocument();
  });

  it("never renders the raw sentiment value itself", () => {
    // Arrange + act: render with a raw state value.
    render(<SentimentStatus sentiment="skipped" />);
    // Assert: the raw enum string never leaks into the rendered text.
    expect(screen.queryByText("skipped")).not.toBeInTheDocument();
  });
});
