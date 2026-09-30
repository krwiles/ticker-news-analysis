import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthControls } from "./AuthControls";
import type { AuthUser } from "../auth";

// Stubs the fetch boundary for endpoints AuthControls calls directly (re-fetching /api/auth/me
// after sign-in, and signOut) -- the initial signed-in/out state is now passed in as a prop.
function stubFetch(meUser: AuthUser | null) {
  const mockFetch = vi.fn((url: string, init?: RequestInit) => {
    if (url.includes("/api/auth/me")) {
      return Promise.resolve({ ok: true, json: async () => ({ user: meUser }) });
    }
    if (url.includes("/api/auth/logout") && init?.method === "POST") {
      return Promise.resolve({ ok: true, json: async () => ({ ok: true }) });
    }
    if (url.includes("/api/auth/google") && init?.method === "POST") {
      return Promise.resolve({ ok: true, json: async () => meUser });
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

  it("does not show a sign-out control while signed out", () => {
    // Act: rendered with user=null, as Layout would once its own check resolves signed-out.
    render(<AuthControls user={null} onSignedIn={vi.fn()} onSignedOut={vi.fn()} />);

    // Assert: window.google isn't defined in jsdom, so GIS's own button never renders
    // either, just an empty container, not a crash.
    expect(screen.queryByRole("button", { name: /sign out/i })).not.toBeInTheDocument();
  });

  it("shows the signed-in user's name and a sign-out control", () => {
    // Arrange: rendered with a real signed-in user, as Layout would pass it down.
    const user: AuthUser = { email: "a@example.com", name: "Ada Lovelace", picture_url: "https://img/a.png" };

    // Act.
    const { container } = render(<AuthControls user={user} onSignedIn={vi.fn()} onSignedOut={vi.fn()} />);

    // Assert: name and sign-out button both appear. Queried via the container, not
    // getByRole("img") -- alt="" deliberately removes it from the accessibility tree.
    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign out/i })).toBeInTheDocument();
    expect(container.querySelector("img")).toHaveAttribute("src", "https://img/a.png");
  });

  it("omits the profile picture when picture_url is null", () => {
    // Arrange: a signed-in user with no picture (a real, valid Google response shape).
    const user: AuthUser = { email: "a@example.com", name: "Ada Lovelace", picture_url: null };

    // Act.
    const { container } = render(<AuthControls user={user} onSignedIn={vi.fn()} onSignedOut={vi.fn()} />);

    // Assert: name still renders, but there's no broken/empty <img>.
    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
    expect(container.querySelector("img")).not.toBeInTheDocument();
  });

  it("calls onSignedOut after a real sign-out request succeeds", async () => {
    // Arrange: starts signed in.
    const mockFetch = stubFetch(null);
    const onSignedOut = vi.fn();
    const user = userEvent.setup();
    const authUser: AuthUser = { email: "a@example.com", name: "Ada Lovelace", picture_url: null };
    render(<AuthControls user={authUser} onSignedIn={vi.fn()} onSignedOut={onSignedOut} />);

    // Act: click Sign out.
    await user.click(screen.getByRole("button", { name: /sign out/i }));

    // Assert: the real logout endpoint was called, and the parent was told to clear its state.
    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining("/api/auth/logout"), expect.objectContaining({ method: "POST" }));
    await waitFor(() => expect(onSignedOut).toHaveBeenCalledTimes(1));
  });

  it("calls onSignedIn with the re-fetched user once GIS's own button fires", async () => {
    // Arrange: rendered signed-out; GIS's button fires a credential once clicked.
    const signedInUser: AuthUser = { email: "a@example.com", name: "Ada Lovelace", picture_url: null };
    stubFetch(signedInUser);
    const onSignedIn = vi.fn();
    const gis = stubGoogleIdentity();
    render(<AuthControls user={null} onSignedIn={onSignedIn} onSignedOut={vi.fn()} />);
    await screen.findByText("Sign in with Google (fake)");

    // Act: simulate GIS's real button firing its callback with a credential.
    await waitFor(() => gis.signIn("fake-jwt"));

    // Assert: the parent is told about the newly signed-in user -- re-fetched from
    // /api/auth/me, not trusted directly from the sign-in response (ADR 0016's own reasoning).
    await waitFor(() => expect(onSignedIn).toHaveBeenCalledWith(signedInUser));
  });

  it("removes GIS's own injected button once the parent re-renders with a signed-in user", () => {
    // Arrange: starts signed out.
    const { rerender } = render(<AuthControls user={null} onSignedIn={vi.fn()} onSignedOut={vi.fn()} />);
    stubGoogleIdentity();
    rerender(<AuthControls user={null} onSignedIn={vi.fn()} onSignedOut={vi.fn()} />);

    // Act: the parent (Layout) learns the user signed in and passes the new prop down --
    // this component itself never causes this transition, it only reacts to it.
    const signedInUser: AuthUser = { email: "a@example.com", name: "Ada Lovelace", picture_url: null };
    rerender(<AuthControls user={signedInUser} onSignedIn={vi.fn()} onSignedOut={vi.fn()} />);

    // Assert: the profile view appears, and GIS's own injected node -- inserted directly into
    // the DOM, outside React's own children -- is actually gone, not left behind underneath it.
    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.queryByText("Sign in with Google (fake)")).not.toBeInTheDocument();
  });
});
