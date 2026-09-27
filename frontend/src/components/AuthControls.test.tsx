import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthControls } from "./AuthControls";
import type { AuthUser } from "../auth";

// Stubs the fetch boundary for both endpoints AuthControls calls -- same shape as
// search.test.ts's per-URL fetch stub, one level below the module it's testing.
function stubFetch(currentUser: AuthUser | null) {
  const mockFetch = vi.fn((url: string, init?: RequestInit) => {
    if (url.includes("/api/auth/me")) {
      return Promise.resolve({ ok: true, json: async () => ({ user: currentUser }) });
    }
    if (url.includes("/api/auth/logout") && init?.method === "POST") {
      return Promise.resolve({ ok: true, json: async () => ({ ok: true }) });
    }
    throw new Error(`unexpected fetch to ${url}`);
  });
  vi.stubGlobal("fetch", mockFetch);
  return mockFetch;
}

describe("AuthControls", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("does not show a sign-out control while signed out", async () => {
    // Arrange: the initial /api/auth/me check reports signed-out.
    stubFetch(null);

    // Act.
    render(<AuthControls />);

    // Assert: settles into the signed-out view -- window.google isn't defined in jsdom, so
    // GIS's own button never renders either, just an empty container, not a crash.
    await waitFor(() => expect(screen.queryByRole("button", { name: /sign out/i })).not.toBeInTheDocument());
  });

  it("shows the signed-in user's name and a sign-out control", async () => {
    // Arrange: a real signed-in user comes back from /api/auth/me.
    stubFetch({ email: "a@example.com", name: "Ada Lovelace", picture_url: "https://img/a.png" });

    // Act.
    const { container } = render(<AuthControls />);

    // Assert: name and sign-out button both appear. Queried via the container, not
    // getByRole("img") -- alt="" deliberately removes it from the accessibility tree.
    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign out/i })).toBeInTheDocument();
    expect(container.querySelector("img")).toHaveAttribute("src", "https://img/a.png");
  });

  it("omits the profile picture when picture_url is null", async () => {
    // Arrange: a signed-in user with no picture (a real, valid Google response shape).
    stubFetch({ email: "a@example.com", name: "Ada Lovelace", picture_url: null });

    // Act.
    const { container } = render(<AuthControls />);

    // Assert: name still renders, but there's no broken/empty <img>.
    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
    expect(container.querySelector("img")).not.toBeInTheDocument();
  });

  it("returns to the signed-out view after clicking Sign out", async () => {
    // Arrange: starts signed in.
    const mockFetch = stubFetch({ email: "a@example.com", name: "Ada Lovelace", picture_url: null });
    const user = userEvent.setup();
    render(<AuthControls />);
    await screen.findByRole("button", { name: /sign out/i });

    // Act: click Sign out.
    await user.click(screen.getByRole("button", { name: /sign out/i }));

    // Assert: the real logout endpoint was called, and local state flips back to signed-out.
    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining("/api/auth/logout"), expect.objectContaining({ method: "POST" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: /sign out/i })).not.toBeInTheDocument());
  });
});
