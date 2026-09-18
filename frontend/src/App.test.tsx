import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

// Rendering App also mounts StatusPage, whose real fetchHealth() call needs stubbing too.
beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        api: { status: "ok" },
        db: { status: "ok" },
        redis: { status: "ok" },
        worker: { status: "ok" },
      }),
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("App navigation", () => {
  it("navigates from Status to Search via the nav link, client-side", async () => {
    // Arrange: mount the whole app, which starts on the Status route.
    const user = userEvent.setup();
    render(<App />);

    // Starts on Status.
    expect(screen.getByRole("heading", { name: /ticker news analysis/i })).toBeInTheDocument();

    // Act: navigate to Search via the nav link.
    await user.click(screen.getByRole("link", { name: "Search" }));

    // Assert: Search page's own heading is now showing.
    expect(screen.getByRole("heading", { name: "Search" })).toBeInTheDocument();
  });

  it("navigates back to Status via the nav link", async () => {
    // Arrange: mount the app and navigate to Search first.
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("link", { name: "Search" }));

    // Act: navigate back to Status via the nav link.
    await user.click(screen.getByRole("link", { name: "Status" }));

    // Assert: back on the Status page.
    expect(screen.getByRole("heading", { name: /ticker news analysis/i })).toBeInTheDocument();
  });
});
