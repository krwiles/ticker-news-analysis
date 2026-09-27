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

// Mimics GIS's own window.google.accounts.id -- crucially, renderButton inserts a real DOM
// node into the container directly (like GIS's real iframe), invisible to React's own tree.
function stubGoogleIdentity() {
  let signInCallback: ((response: { credential: string }) => void) | null = null;
  window.google = {
    accounts: {
      id: {
        initialize: (config) => {
          signInCallback = config.callback;
        },
        renderButton: (parent) => {
          const injected = document.createElement("div");
          injected.textContent = "Sign in with Google (fake)";
          parent.appendChild(injected);
        },
      },
    },
  };
  return {
    signIn: (credential: string) => signInCallback?.({ credential }),
  };
}

describe("AuthControls", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    delete window.google;
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

  it("removes GIS's own injected button once signed in, not just React's own markup", async () => {
    // Arrange: starts signed out; signing in flips /api/auth/me's later answer to a real user.
    let signedIn = false;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        if (url.includes("/api/auth/google") && init?.method === "POST") {
          signedIn = true;
          return Promise.resolve({ ok: true, json: async () => ({ email: "a@example.com", name: "Ada Lovelace", picture_url: null }) });
        }
        if (url.includes("/api/auth/me")) {
          const user = signedIn ? { email: "a@example.com", name: "Ada Lovelace", picture_url: null } : null;
          return Promise.resolve({ ok: true, json: async () => ({ user }) });
        }
        throw new Error(`unexpected fetch to ${url}`);
      }),
    );
    const gis = stubGoogleIdentity();
    render(<AuthControls />);
    await screen.findByText("Sign in with Google (fake)");

    // Act: simulate GIS's real button firing its callback with a credential.
    await waitFor(() => gis.signIn("fake-jwt"));

    // Assert: the profile view appears, and GIS's own injected node -- inserted directly into
    // the DOM, outside React's own children -- is actually gone, not left behind underneath it.
    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.queryByText("Sign in with Google (fake)")).not.toBeInTheDocument();
  });
});
