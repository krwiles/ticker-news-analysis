import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useOutletContext } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as authModule from "../auth";
import * as watchlistModule from "../watchlist";
import { Layout, type WatchlistOutletContext } from "./Layout";

// Module-mocked one layer up, same shape as SearchPage.test.tsx's own search.ts mock.
vi.mock("../auth", async (importOriginal) => {
  const actual = await importOriginal<typeof authModule>();
  return { ...actual, fetchMe: vi.fn() };
});
vi.mock("../watchlist", async (importOriginal) => {
  const actual = await importOriginal<typeof watchlistModule>();
  return { ...actual, fetchWatchlist: vi.fn(), addToWatchlist: vi.fn(), removeFromWatchlist: vi.fn() };
});

const fetchMe = vi.mocked(authModule.fetchMe);
const fetchWatchlist = vi.mocked(watchlistModule.fetchWatchlist);
const addToWatchlist = vi.mocked(watchlistModule.addToWatchlist);
const removeFromWatchlist = vi.mocked(watchlistModule.removeFromWatchlist);

// A minimal stand-in for SearchPage -- exercises the same useOutletContext() consumption
// without pulling in SearchPage's own unrelated fetchSearch/fetchSearchStatus machinery.
function DummyChild() {
  const { entries, add, remove } = useOutletContext<WatchlistOutletContext>();
  return (
    <div>
      <p>entry count: {entries.length}</p>
      <button onClick={() => add("MSFT")}>add MSFT</button>
      <button onClick={() => remove("MSFT")}>remove MSFT</button>
    </div>
  );
}

function renderLayout() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<DummyChild />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

// Toggles jsdom's document.visibilityState and fires the event Layout listens for --
// same technique SearchPage.test.tsx uses for spec 0007's own pause/resume behavior.
function setVisibility(state: "visible" | "hidden") {
  Object.defineProperty(document, "visibilityState", { value: state, configurable: true });
  document.dispatchEvent(new Event("visibilitychange"));
}

describe("Layout", () => {
  afterEach(() => {
    vi.useRealTimers();
    setVisibility("visible");
    vi.clearAllMocks();
  });

  it("never fetches the watchlist while signed out", async () => {
    fetchMe.mockResolvedValue({ user: null });

    renderLayout();
    await waitFor(() => expect(screen.getByText("entry count: 0")).toBeInTheDocument());

    expect(fetchWatchlist).not.toHaveBeenCalled();
  });

  it("fetches the watchlist immediately once signed in, and polls every 20s while visible", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    fetchMe.mockResolvedValue({ user: { email: "a@example.com", name: "Ada", picture_url: null } });
    fetchWatchlist.mockResolvedValue({ entries: [{ ticker: "MSFT", added_at: "2026-09-30T00:00:00Z", new_headlines: 1 }] });

    renderLayout();
    await waitFor(() => expect(screen.getByText("entry count: 1")).toBeInTheDocument());
    expect(fetchWatchlist).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(20000);
    });

    expect(fetchWatchlist).toHaveBeenCalledTimes(2);
  });

  it("pauses polling while hidden and checks immediately again on refocus", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    fetchMe.mockResolvedValue({ user: { email: "a@example.com", name: "Ada", picture_url: null } });
    fetchWatchlist.mockResolvedValue({ entries: [] });

    renderLayout();
    await waitFor(() => expect(fetchWatchlist).toHaveBeenCalledTimes(1));

    // Act: background the tab, then advance well past a normal poll interval.
    setVisibility("hidden");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60000);
    });
    expect(fetchWatchlist).toHaveBeenCalledTimes(1); // no change while hidden

    // Act: refocus -- an immediate check, not waiting for the next scheduled tick.
    setVisibility("visible");
    await waitFor(() => expect(fetchWatchlist).toHaveBeenCalledTimes(2));
  });

  it("clears the watchlist immediately on sign-out, without waiting for a poll tick", async () => {
    fetchMe.mockResolvedValue({ user: { email: "a@example.com", name: "Ada", picture_url: null } });
    fetchWatchlist.mockResolvedValue({ entries: [{ ticker: "MSFT", added_at: "2026-09-30T00:00:00Z", new_headlines: 0 }] });

    renderLayout();
    await waitFor(() => expect(screen.getByText("entry count: 1")).toBeInTheDocument());

    // Act: sign out via AuthControls' own button, rendered by Layout.
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /sign out/i }));

    await waitFor(() => expect(screen.getByText("entry count: 0")).toBeInTheDocument());
  });

  it("updates the shared watchlist state immediately after add/remove, with no extra poll needed", async () => {
    fetchMe.mockResolvedValue({ user: { email: "a@example.com", name: "Ada", picture_url: null } });
    fetchWatchlist
      .mockResolvedValueOnce({ entries: [] })
      .mockResolvedValueOnce({ entries: [{ ticker: "MSFT", added_at: "2026-09-30T00:00:00Z", new_headlines: 0 }] })
      .mockResolvedValueOnce({ entries: [] });
    addToWatchlist.mockResolvedValue({ ticker: "MSFT", added_at: "2026-09-30T00:00:00Z", new_headlines: 0 });
    removeFromWatchlist.mockResolvedValue(undefined);

    renderLayout();
    await waitFor(() => expect(screen.getByText("entry count: 0")).toBeInTheDocument());

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^add msft$/i }));
    expect(addToWatchlist).toHaveBeenCalledWith("MSFT");
    await waitFor(() => expect(screen.getByText("entry count: 1")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /^remove msft$/i }));
    expect(removeFromWatchlist).toHaveBeenCalledWith("MSFT");
    await waitFor(() => expect(screen.getByText("entry count: 0")).toBeInTheDocument());
  });

  it("survives a failed add without an unhandled rejection, leaving the list unchanged", async () => {
    fetchMe.mockResolvedValue({ user: { email: "a@example.com", name: "Ada", picture_url: null } });
    fetchWatchlist.mockResolvedValue({ entries: [] });
    addToWatchlist.mockRejectedValue(new Error("/api/watchlist responded 400"));
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

    renderLayout();
    await waitFor(() => expect(screen.getByText("entry count: 0")).toBeInTheDocument());

    const user = userEvent.setup();
    // The test fails on an unhandled rejection if add() doesn't catch this itself.
    await user.click(screen.getByRole("button", { name: /^add msft$/i }));

    expect(screen.getByText("entry count: 0")).toBeInTheDocument();
    expect(consoleError).toHaveBeenCalled();
    consoleError.mockRestore();
  });

  it("does not render the sidebar while signed out", async () => {
    fetchMe.mockResolvedValue({ user: null });

    renderLayout();
    await waitFor(() => expect(screen.getByText("entry count: 0")).toBeInTheDocument());

    expect(screen.queryByRole("navigation", { name: /watchlist/i })).not.toBeInTheDocument();
  });
});
