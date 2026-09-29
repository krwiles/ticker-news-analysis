import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RefreshIndicator } from "./RefreshIndicator";

describe("RefreshIndicator", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows 0s right when lastRefreshAt is now", () => {
    // Arrange + act.
    render(<RefreshIndicator lastRefreshAt={Date.now()} />);
    // Assert.
    expect(screen.getByText("last refresh 0s ago")).toBeInTheDocument();
  });

  it("counts up once a second as real time passes", async () => {
    // Arrange
    render(<RefreshIndicator lastRefreshAt={Date.now()} />);

    // Act: three seconds pass.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });

    // Assert.
    expect(screen.getByText("last refresh 3s ago")).toBeInTheDocument();
  });

  it("never shows a negative count, even if lastRefreshAt is fractionally in the future", () => {
    // Arrange: a timestamp a hair after "now" -- guards against clock-skew rounding.
    render(<RefreshIndicator lastRefreshAt={Date.now() + 500} />);
    // Assert: clamped to 0, not -1 or similar.
    expect(screen.getByText("last refresh 0s ago")).toBeInTheDocument();
  });
});
