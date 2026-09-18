import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SentimentPill } from "./SentimentPill";

describe("SentimentPill", () => {
  it("shows the gloss and score together when resolved", () => {
    // Arrange + act: render a resolved headline-level pill.
    render(<SentimentPill enumValue="positive" score={82} gloss="bullish" />);
    // Assert: gloss and score are both shown, together.
    expect(screen.getByText("bullish · 82")).toBeInTheDocument();
  });

  it("falls back to the enum and a rounded score when there's no gloss (a Story aggregate)", () => {
    // Arrange + act: render a resolved Story-level pill -- no gloss, a non-integer average.
    render(<SentimentPill enumValue="positive" score={80.67} gloss={null} />);
    // Assert: enum + rounded score are shown instead of a gloss.
    expect(screen.getByText("positive · 81")).toBeInTheDocument();
  });

  it("shows a single Pending pill when unresolved, regardless of why", () => {
    // Arrange + act: render an unresolved pill (null enum/score -- covers not-yet-attempted, skipped, and error alike).
    render(<SentimentPill enumValue={null} score={null} />);
    // Assert: a generic Pending pill is shown -- no gloss, no score, no enum-specific color.
    expect(screen.getByText("Pending")).toBeInTheDocument();
  });

  it("uses a visibly distinct style per enum value", () => {
    // Same instance, re-rendered with a different enum, so the classes are directly comparable.
    const { rerender } = render(<SentimentPill enumValue="positive" score={90} gloss="bullish" />);
    const positiveClass = screen.getByText("bullish · 90").className;

    rerender(<SentimentPill enumValue="negative" score={10} gloss="alarming" />);
    const negativeClass = screen.getByText("alarming · 10").className;

    expect(positiveClass).not.toBe(negativeClass);
  });
});
