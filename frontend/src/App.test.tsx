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
    const user = userEvent.setup();
    render(<App />);

    expect(screen.getByRole("heading", { name: /ticker news analysis/i })).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "Search" }));

    expect(screen.getByRole("heading", { name: "Search" })).toBeInTheDocument();
  });

  it("navigates back to Status via the nav link", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("link", { name: "Search" }));
    await user.click(screen.getByRole("link", { name: "Status" }));

    expect(screen.getByRole("heading", { name: /ticker news analysis/i })).toBeInTheDocument();
  });
});
